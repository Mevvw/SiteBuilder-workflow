"""确定性工具:perf_audit(五项审计,规则唯一事实来源)/ write_artifact(防路径穿越)/ redact_secrets(报告脱敏)。"""
from __future__ import annotations

import re
from pathlib import Path

from workflow_chain.state import AnimationSpec, AuditRaw, CheckResult, ScaffoldPlan

# ---- 规则常量(gate_2 与 perf_audit 共用,同源) ----
ALLOWED_PROPERTIES = {"transform", "opacity", "clip-path"}
PROPERTY_BLACKLIST = ["blur(", "bounce", "elastic", "spring(", "shake", "wobble", "drop-shadow("]
LAYOUT_PROPERTIES = {
    "width", "height", "top", "left", "right", "bottom",
    "margin", "padding", "font-size", "background-position",
}
HEAVY_FX_KEYWORDS = ["webgl", "canvas", "filter", "backdrop", "box-shadow", "text-shadow", "particle"]
HEAVY_DEPS = {"three", "gsap", "lottie", "framer-motion", "swiper", "d3", "chart.js"}


def _prop_base(p: str) -> str:
    """取属性基名:'transform: translateX(10px)' -> 'transform'。"""
    return p.strip().lower().split(":")[0].split("(")[0].strip()


def scan_anim_properties(rules) -> list[str]:
    """扫描动画属性白名单/黑名单,返回违规描述列表(gate_2 与 perf_audit 检查① 同源调用)。"""
    violations: list[str] = []
    for r in rules:
        for p in r.properties:
            low = p.lower()
            if _prop_base(p) not in ALLOWED_PROPERTIES:
                violations.append(f"{r.target}: 属性 {p!r} 不在白名单 {{transform, opacity, clip-path}}")
            for w in PROPERTY_BLACKLIST:
                if w in low:
                    violations.append(f"{r.target}: 属性 {p!r} 命中黑名单关键词 {w!r}")
    return violations


# ---------------- perf_audit:五项检查 ----------------
def perf_audit(animation: AnimationSpec, scaffold: ScaffoldPlan) -> AuditRaw:
    """确定性审计(不联网、不调 LLM),五项检查为通用前端性能清单。

    规则唯一事实来源:gate_3 自身零规则,只消费此处的 all_pass 与 owner。
    """
    checks: list[CheckResult] = []
    rules = [*animation.entrance, *animation.scroll, *animation.hover]
    props_text = " ".join(" ".join(r.properties) for r in rules).lower()

    # ① 动画属性白名单/黑名单扫描
    v1 = scan_anim_properties(rules)
    checks.append(CheckResult(
        check="①动画属性白名单/黑名单", passed=not v1, owner="animation",
        detail="; ".join(v1) if v1 else "全部属性在白名单内,未命中黑名单",
    ))

    # ② WebGL/重特效项必须有视口暂停说明
    heavy_hits = [k for k in HEAVY_FX_KEYWORDS if k in props_text]
    ok2 = not heavy_hits or animation.heavy_fx_pause_note.strip() != ""
    checks.append(CheckResult(
        check="②重特效视口暂停说明", passed=ok2, owner="animation",
        detail=(f"检测到重特效关键词 {heavy_hits} 但缺少视口暂停说明" if not ok2
                else (f"重特效 {heavy_hits} 已附视口暂停说明" if heavy_hits else "未使用重特效")),
    ))

    # ③ 滚动/指针监听须含 rAF 节流说明;禁止布局抖动属性
    layout_bad = [p for r in rules for p in r.properties if _prop_base(p) in LAYOUT_PROPERTIES]
    needs_throttle = len(animation.scroll) > 0 or len(animation.hover) > 0
    ok3 = not layout_bad and (not needs_throttle or animation.listener_throttle_note.strip() != "")
    detail3 = []
    if layout_bad:
        detail3.append(f"使用布局抖动属性 {layout_bad}(读写 width/height 等会触发重排)")
    if needs_throttle and animation.listener_throttle_note.strip() == "":
        detail3.append("存在滚动/悬停监听但缺少 rAF 节流说明")
    checks.append(CheckResult(
        check="③监听节流与布局抖动", passed=ok3, owner="animation",
        detail="; ".join(detail3) if detail3 else "无布局抖动属性,监听节流说明完备",
    ))

    # ④ 依赖体积预算:重依赖须有分包/懒加载说明
    heavy_deps = [d for d in scaffold.deps if any(h in d.lower() for h in HEAVY_DEPS)]
    ok4 = not heavy_deps or scaffold.bundle_note.strip() != ""
    checks.append(CheckResult(
        check="④重依赖分包说明", passed=ok4, owner="scaffold",
        detail=(f"检测到重依赖 {heavy_deps} 但 bundle_note 为空(需说明分包/懒加载策略)" if not ok4
                else (f"重依赖 {heavy_deps} 已附分包说明" if heavy_deps else "无重依赖")),
    ))

    # ⑤ reduced-motion 降级覆盖
    ok5 = animation.reduced_motion_fallback.strip() != ""
    checks.append(CheckResult(
        check="⑤reduced-motion降级覆盖", passed=ok5, owner="animation",
        detail="缺少 prefers-reduced-motion 降级说明" if not ok5 else "降级说明已提供",
    ))

    return AuditRaw(checks=checks, all_pass=all(c.passed for c in checks))


# ---------------- write_artifact ----------------
def write_artifact(artifacts_dir: str, filename: str, content: str) -> dict:
    """utf-8 落盘。路径穿越防护:resolve 后必须仍在 artifacts_dir 内,否则 PermissionError。"""
    root = Path(artifacts_dir).resolve()
    target = (root / filename).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError(f"路径穿越被拒绝: {filename!r} → {target}") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data)}


# ---------------- redact_secrets ----------------
_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{8,}"), "sk-***"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(r"(?i)api[_-]?key\s*[=:]\s*[\"']?[A-Za-z0-9._\-]+"), "api_key=***"),
    (re.compile(r"(?i)(publishable[_-]?key\s*[=:]\s*)[\"']?[A-Za-z0-9._\-]+"), r"\1***"),
]


def redact_secrets(text: str) -> str:
    """报告落盘前脱敏:sk-… / Bearer … / api_key=… / publishable_key=… 打码,防 Key 随开源报告泄露。"""
    out = text or ""
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out
