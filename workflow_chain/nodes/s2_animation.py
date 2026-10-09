"""s2_animation:② 出入场动画编排(DESIGN.md §2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.nodes.s1_style_framework import _render_index_html
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


def _anim_css(anim: AnimationSpec) -> str:
    """从编排推导动画 CSS:时长取首条入场规则,stagger 步长取最小非零 delay。"""
    entrance = anim.entrance[0] if anim.entrance else None
    dur = max(80, min(2000, entrance.duration_ms if entrance else 600))
    staggers = [r.delay_ms for r in anim.entrance if r.technique == "stagger" and r.delay_ms > 0]
    step = min(staggers) if staggers else 120
    clip = any(r.technique == "clip-reveal" for r in anim.scroll)
    reveal_kf = "wf-clip-in" if clip else "wf-fade-up"
    return (
        "\n/* ===== s2 动画注入(源自 02-animation-spec 编排) ===== */\n"
        "@keyframes wf-fade-up{from{opacity:0;transform:translateY(24px)}to{opacity:1;transform:none}}\n"
        "@keyframes wf-clip-in{from{clip-path:inset(0 0 100% 0);opacity:.5}to{clip-path:inset(0 0 0 0);opacity:1}}\n"
        f"#hero .wrap>*{{opacity:0;animation:wf-fade-up {dur}ms var(--ease) forwards}}\n"
        f"#hero .wrap>*:nth-child(2){{animation-delay:{step}ms}}\n"
        f"#hero .wrap>*:nth-child(3){{animation-delay:{step * 2}ms}}\n"
        f"#hero .wrap>*:nth-child(4){{animation-delay:{step * 3}ms}}\n"
        f"#hero .wrap>*:nth-child(5){{animation-delay:{step * 4}ms}}\n"
        f"#hero .wrap>*:nth-child(6){{animation-delay:{step * 5}ms}}\n"
        "[data-reveal]{opacity:0}\n"
        f"[data-reveal].is-in{{animation:{reveal_kf} {dur}ms var(--ease) forwards}}\n"
        ".card{transition:transform .3s var(--ease)}\n"
        ".card:hover{transform:translateY(-3px)}\n"
        "@media (prefers-reduced-motion: reduce){\n"
        "  #hero .wrap>*,[data-reveal]{opacity:1!important;animation:none!important}\n"
        "  .card:hover{transform:none}\n"
        "}\n"
    )


def _anim_js(anim: AnimationSpec) -> str:
    """滚动揭示脚本:IntersectionObserver 一次性触发,节奏取编排 stagger 步长。"""
    staggers = [r.delay_ms for r in anim.entrance if r.technique == "stagger" and r.delay_ms > 0]
    step = min(staggers) if staggers else 120
    return (
        "<script>\n"
        "(function(){\n"
        "  var els=[].slice.call(document.querySelectorAll('[data-reveal]'));\n"
        "  var reduce=window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches;\n"
        "  if(reduce||!('IntersectionObserver' in window)){els.forEach(function(e){e.classList.add('is-in')});return}\n"
        "  var io=new IntersectionObserver(function(es){es.forEach(function(en){"
        "if(en.isIntersecting){en.target.classList.add('is-in');io.unobserve(en.target)}})},{threshold:.15});\n"
        f"  els.forEach(function(e,i){{e.style.animationDelay=(i%3)*{step}+'ms';io.observe(e)}});\n"
        "})();\n"
        "</script>"
    )


def _inject_animations(style, anim: AnimationSpec) -> str:
    """在 s1 骨架之上注入动画(DESIGN 第二步:骨架之上统一编排)。

    对占位卡/指标块/信息行打 data-reveal 标记,滚动进入视口时揭示;
    入场序列作用于 Hero 直接子元素;reduced-motion 全量降级。
    """
    base = _render_index_html(style)
    base = base.replace('<div class="card">', '<div class="card" data-reveal>')
    base = base.replace('<div class="stat">', '<div class="stat" data-reveal>')
    base = base.replace('<div class="row">', '<div class="row" data-reveal>')
    base = base.replace("</style>", _anim_css(anim) + "</style>")
    base = base.replace("</body>", _anim_js(anim) + "\n</body>")
    return base


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
        # 编排通过解析后,把动画真正注入骨架页(门禁若打回,回炉重跑会再次覆盖)
        write_artifact(state["artifacts_dir"], "scaffold/index.html", _inject_animations(style, anim))
        step_log("s2", f"动画编排就绪并已注入骨架页(入场 {len(anim.entrance)} / 滚动 {len(anim.scroll)} / 悬停 {len(anim.hover)})")
        return {"animation": anim, "feedback": {"s2": None}}

    return s2_animation
