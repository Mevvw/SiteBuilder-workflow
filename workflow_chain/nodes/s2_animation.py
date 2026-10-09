"""s2_animation:② 出入场动画编排(DESIGN.md §2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import AnimationSpec, WorkflowState
from workflow_chain.tools import write_artifact

SYSTEM = """你是动效编排师。基于风格决策与框架方案,产出首屏入场、滚动、悬停三段动画编排。
硬性规则(门禁将逐条校验,违反即回炉):
1. properties 只允许 transform / opacity / clip-path;严禁 blur、bounce、elastic、spring、shake、wobble、drop-shadow 等黑名单词,也严禁 width/height/top/left 等布局属性;
2. 入场编排 entrance 必须包含至少一条 stagger 手法;
3. 滚动编排 scroll 必须包含至少一条 clip-reveal 手法;
4. reduced_motion_fallback 必须给出 prefers-reduced-motion: reduce 的降级说明;
5. 涉及滚动/悬停监听时,listener_throttle_note 必须写明 requestAnimationFrame 节流;
6. duration_ms 取 80~2000,delay_ms 取 0~1500。

编排偏好:首屏入场按视觉主次递进 delay(参考序列 50/120/280/460/580ms,主视觉最后压轴);悬停反馈全站同幅同曲线(统一位移量与统一缓动),克制不炫技。

若存在【上次回炉反馈】,必须逐条修复,严禁重犯。"""


def _rule_md(r) -> str:
    return (
        f"- `{r.target}` · {r.technique} · [{', '.join(r.properties)}] · "
        f"{r.duration_ms}ms / delay {r.delay_ms}ms"
    )


def _render_md(anim: AnimationSpec) -> str:
    entrance_lines = [_rule_md(r) for r in anim.entrance] or ["- (无)"]
    scroll_lines = [_rule_md(r) for r in anim.scroll] or ["- (无)"]
    hover_lines = [_rule_md(r) for r in anim.hover] or ["- (无)"]
    lines = ["# 02 · 动画编排", "",
             "## 入场(entrance)", *entrance_lines,
             "", "## 滚动(scroll)", *scroll_lines,
             "", "## 悬停(hover)", *hover_lines,
             "", f"**reduced-motion 降级**:{anim.reduced_motion_fallback}"]
    if anim.heavy_fx_pause_note:
        lines.append(f"\n**重特效视口暂停**:{anim.heavy_fx_pause_note}")
    if anim.listener_throttle_note:
        lines.append(f"\n**监听节流**:{anim.listener_throttle_note}")
    return "\n".join(lines) + "\n"


def make_s2(runner, config=None):
    def s2_animation(state: WorkflowState) -> dict:
        style, scaffold = state.get("style"), state.get("scaffold")
        fb = (state.get("feedback") or {}).get("s2")
        summary = (
            f"【风格】{style.site_type} · {style.tone} · 缓动 {style.easing}\n"
            f"【框架】{scaffold.stack},模块 {'/'.join(style.modules)},"
            f"文件 {'、'.join(f.path for f in scaffold.files)}"
        )
        user = summary
        if fb:
            user += f"\n\n【上次回炉反馈(必须逐条修复,严禁重犯)】\n{fb}"
        anim = runner.structured(AnimationSpec, SYSTEM, user)
        write_artifact(state["artifacts_dir"], "02-animation-spec.md", _render_md(anim))
        step_log("s2", f"动画编排就绪(入场 {len(anim.entrance)} / 滚动 {len(anim.scroll)} / 悬停 {len(anim.hover)})")
        return {"animation": anim, "feedback": {"s2": None}}

    return s2_animation
