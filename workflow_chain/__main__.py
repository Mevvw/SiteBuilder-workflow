"""CLI 入口:python -m workflow_chain run "<需求简述>" --provider mock|cloud|deepseek

退出码:0=done,1=aborted,2=fatal error。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from workflow_chain.config import ConfigError, CLOUD_CONFIG_FILE, RunConfig, make_config
from workflow_chain.graph import run_chain
from workflow_chain.llm import Budget

console = Console()


def _parse_chaos(spec: str) -> dict:
    """'s2:1' → {'s2': 1};'s2:0' = 每次注入;支持逗号分隔 's2:1,s1:2'。"""
    out: dict[str, int] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        node, _, n = part.partition(":")
        if node not in {"s1", "s2", "s3", "s4"} or not n.isdigit():
            raise ValueError(f"--chaos 格式非法:{part!r}(应为 节点:次数,如 s2:1)")
        out[node] = int(n)
    return out


def _parse_node_models(spec: str) -> dict:
    """'s1=glm-5.3,s4=deepseek-chat' → {'s1': 'glm-5.3', 's4': 'deepseek-chat'}。"""
    out: dict[str, str] = {}
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        k, _, v = part.partition("=")
        if not k.strip() or not v.strip():
            raise ValueError(f"--node-models 格式非法:{part!r}(应为 节点=模型,如 s1=glm-5.3)")
        out[k.strip()] = v.strip()
    return out


def _print_summary(final: dict) -> None:
    d = final.get("artifacts_dir", "")
    console.print(f"\n[bold]运行结果:[/bold]{final.get('status')}  [dim]{d}[/dim]")
    if final.get("error"):
        console.print(f"[red]error:[/red] {final['error']}")
    logs = final.get("gate_logs") or []
    if logs:
        t = Table(title="门禁日志", show_lines=False)
        t.add_column("门禁"); t.add_column("判定"); t.add_column("违规")
        for log in logs:
            color = "green" if log.verdict == "pass" else "red"
            t.add_row(log.gate, f"[{color}]{log.verdict}[/{color}]",
                      "\n".join(log.violations[:3]) or "-")
        console.print(t)
    usage = final.get("usage") or {}
    if usage:
        console.print(
            f"[dim]用量:llm_calls={usage.get('llm_calls', 0)} "
            f"prompt={usage.get('prompt_tokens', 0)} completion={usage.get('completion_tokens', 0)}[/dim]"
        )


def _cmd_models(config_path: str) -> int:
    """列出云端可用模型(cloud 档)。GET {endpoint}/.cloud/llm/models,鉴权头与官方 SDK 一致。"""
    from workflow_chain.llm import CloudRunner, FatalLLMError

    p = Path(config_path)
    if not p.exists():
        console.print(f"[red]缺少 {config_path}(先激活 WorkBuddy 云服务)[/red]")
        return 2
    pub = (json.loads(p.read_text("utf-8")) or {}).get("publicConfig", {})
    if not pub.get("endpoint") or not pub.get("publishableKey"):
        console.print("[red]publicConfig 缺 endpoint / publishableKey[/red]")
        return 2
    probe = RunConfig(provider="cloud", model="probe",
                      base_url=pub["endpoint"], api_key=pub["publishableKey"])
    try:
        models = CloudRunner(probe, Budget()).list_models()
    except Exception as e:  # noqa: BLE001
        console.print(f"[red]模型列表获取失败:[/red]{e}")
        return 1
    if not models:
        console.print("[yellow]模型列表为空(合法结果,需在云端目录启用模型)[/yellow]")
        return 1
    t = Table(title="可用模型")
    t.add_column("id"); t.add_column("name"); t.add_column("disabled")
    for m in models:
        t.add_row(str(m.get("id")), str(m.get("name") or m.get("id")),
                  str(m.get("disabled", "-")))
    console.print(t)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="workflow_chain", description="网页搭建工作流链(LangGraph,四步建站 + 门禁回炉)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="跑一次全链")
    run_p.add_argument("brief", help="需求简述")
    run_p.add_argument("--provider", default="mock",
                       help="mock / cloud / deepseek / glm / kimi / qwen / openai / 自定义名(需 LLM_BASE_URL+LLM_API_KEY)")
    run_p.add_argument("--model", default="", help="模型名(cloud 档必填,可用 models 子命令查询)")
    run_p.add_argument("--max-reworks", type=int, default=2, help="每步回炉上限(默认 2)")
    run_p.add_argument("--chaos", default="", help="注入毒样本,如 s2:1(第 1 次调用)或 s2:0(每次)")
    run_p.add_argument("--out", default="output", help="产物根目录(默认 ./output)")
    run_p.add_argument("--min-cards", type=int, default=3, help="内容卡数量下限(默认 3)")
    run_p.add_argument("--max-cards", type=int, default=6, help="内容卡数量上限(默认 6)")
    run_p.add_argument("--node-models", default="",
                       help="按节点覆盖模型,如 s1=glm-5.3,s4=deepseek-chat(与 --provider 同族端点)")
    run_p.add_argument("--no-review", action="store_true", help="跳过 s5 对抗评审 agent")

    models_p = sub.add_parser("models", help="列出云端可用模型(cloud 档)")
    models_p.add_argument("--config", default=CLOUD_CONFIG_FILE)

    args = parser.parse_args(argv)

    if args.cmd == "models":
        return _cmd_models(args.config)

    try:
        chaos = _parse_chaos(getattr(args, "chaos", ""))
        node_models = _parse_node_models(getattr(args, "node_models", ""))
        config = make_config(args.provider, model=args.model,
                             max_reworks=args.max_reworks,
                             min_cards=args.min_cards, max_cards=args.max_cards,
                             node_models=node_models,
                             enable_review=not args.no_review)
    except (ConfigError, ValueError) as e:
        console.print(f"[red]配置错误:[/red]{e}")
        return 2

    console.print(f"[bold]provider[/bold]={config.provider}  model={config.model or '-'}  "
                  f"mode={config.structured_output_mode}  max_reworks={config.max_reworks}"
                  + (f"  node_models={config.node_models}" if config.node_models else "")
                  + ("" if config.enable_review else "  review=off")
                  + (f"  chaos={chaos}" if chaos else ""))
    try:
        final = run_chain(args.brief, config, chaos=chaos, artifacts_root=args.out)
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断(Ctrl+C)[/yellow]")
        return 2
    _print_summary(final)
    return {"done": 0, "aborted": 1}.get(final.get("status"), 2)


if __name__ == "__main__":
    sys.exit(main())
