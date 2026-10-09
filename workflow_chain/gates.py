"""门禁层(DESIGN.md §1):确定性校验,永不调 LLM、永不抛异常。

「门禁 = 门禁节点 + 路由条件边」两件套(LangGraph 中只有节点能写状态,条件边只读):
- 门禁节点 g1~g4:校验 → 写 gate_logs / rework_counts / feedback,返回状态增量;
- 路由函数 route_g1~g4:纯读状态,返回下游节点名(pass / 回炉 / abort)。

g3 特殊:失败项的责任路由由 g3_owner_step() 统一裁决
(失败项数量多者优先;平局回 rework_counts 较小者),节点写反馈与路由边共用同一纯函数,保证一致。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from workflow_chain.state import GateLog, WorkflowState
from workflow_chain.tools import scan_anim_properties

STEP_OF_GATE = {"g1_style": "s1", "g2_animation": "s2", "g3_performance": "s3", "g4_content": "s4"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _log(gate: str, verdict: str, violations: list[str]) -> GateLog:
    return GateLog(gate=gate, verdict=verdict, violations=violations, ts=_now())


def _finish_gate(state: WorkflowState, gate: str, step: str, violations: list[str]) -> dict:
    """门禁公共收尾:pass 清反馈;fail 计数+1 并把违规清单写入 feedback[step]。"""
    if not violations:
        return {"gate_logs": [_log(gate, "pass", [])], "feedback": {step: None}}
    counts = dict(state.get("rework_counts") or {})
    counts[step] = counts.get(step, 0) + 1
    return {
        "gate_logs": [_log(gate, "fail", violations)],
        "rework_counts": counts,
        "feedback": {step: "; ".join(violations)},
    }


def _last_log(state: WorkflowState, gate: str) -> GateLog | None:
    for log in reversed(state.get("gate_logs") or []):
        if log.gate == gate:
            return log
    return None


# ---------------- gate_1:风格 + 框架 ----------------
def check_style_scaffold(style, scaffold) -> list[str]:
    v: list[str] = []
    if style is None:
        v.append("缺少 style(风格决策)")
    else:
        import re

        for name in ("bg", "acc", "accent2", "txt"):
            val = getattr(style.palette, name, None)
            if not isinstance(val, str) or not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", val or ""):
                v.append(f"色板 {name} 非合法 hex:{val!r}")
        if not (isinstance(style.easing, str) and style.easing.strip().startswith("cubic-bezier(")):
            v.append(f"缓动曲线非 cubic-bezier:{style.easing!r}")
        missing = [m for m in ("Hero", "Works", "Contact") if m not in style.modules]
        if missing:
            v.append(f"模块清单缺少:{','.join(missing)}")
        fs = (style.font_stack or "").lower()
        if any(x in fs for x in ("url(", "http", "@import", "@font-face")):
            v.append("font_stack 疑似引用外链字体(禁网络字体,只允许系统字体栈)")
    if scaffold is None:
        v.append("缺少 scaffold(框架方案)")
    else:
        if len(scaffold.files) < 3:
            v.append(f"框架文件数 < 3(实际 {len(scaffold.files)})")
        for f in scaffold.files:
            if ".." in f.path or f.path.startswith(("/", "\\")) or (len(f.path) > 1 and f.path[1] == ":"):
                v.append(f"文件路径不安全:{f.path!r}")
    return v


def g1_style(state: WorkflowState) -> dict:
    v = check_style_scaffold(state.get("style"), state.get("scaffold"))
    return _finish_gate(state, "g1_style", "s1", v)


def route_g1(state: WorkflowState, max_reworks: int = 2) -> str:
    log = _last_log(state, "g1_style")
    if log is None or log.verdict == "pass":
        return "s2_animation"
    if (state.get("rework_counts") or {}).get("s1", 0) > max_reworks:
        return "abort"
    return "s1_style_framework"


# ---------------- gate_2:动画编排 ----------------
def check_animation(anim) -> list[str]:
    if anim is None:
        return ["缺少 animation(动画编排)"]
    v: list[str] = []
    rules = [*anim.entrance, *anim.scroll, *anim.hover]
    v.extend(scan_anim_properties(rules))  # 白名单/黑名单与 perf_audit 检查① 同源
    if not (anim.reduced_motion_fallback or "").strip():
        v.append("reduced_motion_fallback 为空(必须提供 prefers-reduced-motion 降级说明)")
    if not any(r.technique == "stagger" for r in anim.entrance):
        v.append("入场编排缺少 stagger 手法")
    if not any(r.technique == "clip-reveal" for r in anim.scroll):
        v.append("滚动编排缺少 clip-reveal 手法")
    return v


def g2_animation(state: WorkflowState) -> dict:
    v = check_animation(state.get("animation"))
    return _finish_gate(state, "g2_animation", "s2", v)


def route_g2(state: WorkflowState, max_reworks: int = 2) -> str:
    log = _last_log(state, "g2_animation")
    if log is None or log.verdict == "pass":
        return "s3_performance"
    if (state.get("rework_counts") or {}).get("s2", 0) > max_reworks:
        return "abort"
    return "s2_animation"


# ---------------- gate_3:性能(零规则,只路由) ----------------
def g3_owner_step(perf, rework_counts: dict | None) -> Optional[str]:
    """g3 责任裁决:失败项数量多者优先(owner 计数);平局回 rework_counts 较小者。

    返回 "s1" / "s2";None = 全部通过。owner 映射:animation→s2,scaffold→s1(其他防御性归 s1)。
    """
    failed = [c for c in perf.checks if not c.passed]
    if not failed:
        return None
    tally = {"s1": 0, "s2": 0}
    for c in failed:
        tally["s2" if c.owner == "animation" else "s1"] += 1
    rc = rework_counts or {}

    def key(step: str):
        return (-tally[step], rc.get(step, 0))

    return "s1" if key("s1") <= key("s2") else "s2"


def g3_performance(state: WorkflowState) -> dict:
    perf = state.get("perf")
    if perf is None:
        return _finish_gate(state, "g3_performance", "s3", ["缺少 perf(性能报告)"])
    if perf.all_pass:
        return _finish_gate(state, "g3_performance", "s3", [])
    failed = [c for c in perf.checks if not c.passed]
    counts = dict(state.get("rework_counts") or {})
    target = g3_owner_step(perf, counts) or "s3"
    counts[target] = counts.get(target, 0) + 1
    # 裁决要在计数更新之后重算一次,保证与路由边(读到的就是更新后的计数)一致
    target = g3_owner_step(perf, counts) or target
    violations = [f"{c.check} 未通过(owner={c.owner}):{c.detail}" for c in failed]
    return {
        "gate_logs": [GateLog(gate="g3_performance", verdict="fail", violations=violations, ts=_now())],
        "rework_counts": counts,
        "feedback": {target: "; ".join(violations)},
    }


def route_g3(state: WorkflowState, max_reworks: int = 2) -> str:
    log = _last_log(state, "g3_performance")
    perf = state.get("perf")
    if log is None or log.verdict == "pass":
        return "s4_content"
    if perf is None:
        return "abort"  # 防御:s3 必产 perf;缺失属系统错误
    target = g3_owner_step(perf, state.get("rework_counts") or {}) or "s3"
    if (state.get("rework_counts") or {}).get(target, 0) > max_reworks:
        return "abort"
    return {"s1": "s1_style_framework", "s2": "s2_animation"}[target]


# ---------------- gate_4:内容 ----------------
def check_content(content, min_cards: int = 3, max_cards: int = 6) -> list[str]:
    if content is None:
        return ["缺少 content(内容方案)"]
    v: list[str] = []
    n = len(content.cards)
    if n < min_cards:
        v.append(f"卡片数量 {n} 张少于下限 {min_cards} 张(展示层次不足)")
    elif n > max_cards:
        v.append(f"卡片数量 {n} 张超过上限 {max_cards} 张")
    if not content.placeholders_removed:
        v.append("placeholders_removed=False(占位未清零)")
    for c in content.cards:
        if len((c.desc or "").strip()) < 8:
            v.append(f"卡片 {c.id} desc 少于 8 字:{c.desc!r}")
        if c.status == "LIVE" and c.link is None:
            v.append(f"卡片 {c.id} 为 LIVE 但缺少 link")
        if c.link:
            h = c.link.href or ""
            ok = h.startswith("http://") or h.startswith("https://") or (".." not in h and not h.startswith("/"))
            if not ok:
                v.append(f"卡片 {c.id} link.href 非法:{h!r}(仅允许 http(s) 或不含 .. 的相对路径)")
    return v


def g4_content(state: WorkflowState) -> dict:
    # 数量上下限从 state.config 读取(CLI --min-cards/--max-cards 写入),缺省 3~6
    cfg = state.get("config") or {}
    v = check_content(
        state.get("content"),
        int(cfg.get("min_cards", 3)),
        int(cfg.get("max_cards", 6)),
    )
    return _finish_gate(state, "g4_content", "s4", v)


def route_g4(state: WorkflowState, max_reworks: int = 2) -> str:
    log = _last_log(state, "g4_content")
    if log is None or log.verdict == "pass":
        return "finalize"
    if (state.get("rework_counts") or {}).get("s4", 0) > max_reworks:
        return "abort"
    return "s4_content"
