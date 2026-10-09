"""s3_performance:③ 性能验证 —— perf_audit 确定审计 + agent 工具循环取证(DESIGN.md §1/§2)。

双路径:Runner 支持工具(bind_tools)时走「自主取证 → 最终结论」的 agent 循环;
不支持时退化为单轮解读。规则唯一事实来源始终是 perf_audit,LLM 不发明规则。
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field

from workflow_chain.console import step_log
from workflow_chain.state import AuditAdvice, PerfReport, WorkflowState
from workflow_chain.tools import HEAVY_DEPS, perf_audit, write_artifact

SYSTEM = """你是性能评审员。用户会给你一份建站性能五项检查的 JSON 结果,
你只负责:① 用两三句话解读结果;② 若有失败项,按 owner(animation/scaffold)给出具体、可执行的修复建议。
不要重新发明检查规则,不要改动 JSON 结构。用中文,简洁。"""

SYSTEM_TOOLS = SYSTEM + """
你可以调用工具获取量化证据(首屏入场动画预算 / 重依赖重量),先取证、再下结论;
证据收集足够后,输出最终 JSON 结论:{"advice": "你的解读与建议"}。"""


class EntranceBudgetArgs(BaseModel):
    """查询首屏入场动画的时长预算与规则数(无需参数)。"""

    reason: str = Field("", description="调用理由(可空)")


class DepsWeightArgs(BaseModel):
    """查询框架依赖中的重依赖与分包说明(无需参数)。"""

    reason: str = Field("", description="调用理由(可空)")


def _entrance_budget(anim) -> dict:
    rules = anim.entrance
    total = max((r.delay_ms + r.duration_ms for r in rules), default=0)
    return {
        "entrance_rules": len(rules),
        "budget_ms": total,
        "verdict": "偏重,建议压缩时长或合并序列" if total > 2000 else "合理(≤2000ms)",
    }


def _deps_weight(scaffold) -> dict:
    heavy = [d for d in scaffold.deps if d.lower() in HEAVY_DEPS]
    noted = bool(scaffold.bundle_note.strip())
    return {
        "heavy_deps": heavy,
        "bundle_note_present": noted,
        "verdict": "需补分包/懒加载说明" if heavy and not noted else "已说明或无重依赖",
    }


def make_s3(runner, config=None):
    def s3_performance(state: WorkflowState) -> dict:
        anim, scaffold = state.get("animation"), state.get("scaffold")
        if anim is None or scaffold is None:
            raise RuntimeError("s3 前置缺失:animation/scaffold 未就绪(图拓扑错误)")
        audit = perf_audit(anim, scaffold)  # 确定性工具:规则唯一事实来源
        d = state["artifacts_dir"]

        failed = [c for c in audit.checks if not c.passed]
        ask = (
            "五项检查结果(JSON):\n" + audit.model_dump_json(indent=2)
            + ("\n\n请解读失败项并给出修复建议。" if failed else "\n\n全部通过,请给一句简短结论。")
        )
        evidence: list[dict] = []
        if getattr(runner, "supports_tools", False):
            tools = {
                "entrance_budget": (EntranceBudgetArgs, lambda: _entrance_budget(anim)),
                "deps_weight": (DepsWeightArgs, lambda: _deps_weight(scaffold)),
            }
            advice_obj: AuditAdvice = runner.structured_with_tools(
                AuditAdvice, SYSTEM_TOOLS, ask, tools, max_rounds=3
            )
            advice, evidence = advice_obj.advice, advice_obj.evidence
        else:
            advice = runner.complete(SYSTEM, ask)
        report = PerfReport(checks=audit.checks, all_pass=audit.all_pass, advice=advice)
        write_artifact(d, "03-perf-raw.json", (
            '{"audit": ' + audit.model_dump_json(indent=2)
            + ', "tool_evidence": '
            + json.dumps(evidence, ensure_ascii=False, indent=2)
            + "}"
        ))

        lines = ["# 03 · 性能报告", ""]
        for c in report.checks:
            mark = "✅" if c.passed else "❌"
            lines.append(f"- {mark} **{c.check}**(owner={c.owner}):{c.detail}")
        lines += ["", f"**总判定**:{'全部通过' if report.all_pass else '存在失败项'}",
                  "", f"**评审意见**:{advice}"]
        if evidence:
            lines += ["", "## 工具取证", ""]
            lines += [f"- `{e['tool']}` → {e['result']}" for e in evidence]
        write_artifact(d, "03-perf-report.md", "\n".join(lines) + "\n")
        step_log("s3", f"性能审计完成:{'全部通过' if report.all_pass else f'{len(failed)} 项未通过'}"
                       + (f"(工具取证 {len(evidence)} 项)" if evidence else ""))
        return {"perf": report}

    return s3_performance
