"""mock 档的内置样例:合规样本 + chaos 毒样本(可解析但门禁不过)。

毒样本设计原则:必须能通过 **Pydantic schema 解析**(否则走的是解析修复路径),
但必须被 **门禁规则** 打回 —— 这样 chaos 测试才能验证"门禁 + 回炉"而非解析器。

样例统一使用中性演示需求(咖啡品牌官网),与具体使用者无关。
"""
from __future__ import annotations

from workflow_chain.state import (
    AnimRule,
    AnimationSpec,
    ContentCard,
    ContentPlan,
    FileSpec,
    LinkSpec,
    Palette,
    ScaffoldPlan,
    StyleDecision,
    StyleScaffoldOut,
)


def good_style_scaffold() -> StyleScaffoldOut:
    """合规的风格+框架(可通过 gate_1)。"""
    return StyleScaffoldOut(
        style=StyleDecision(
            site_type="咖啡品牌官网",
            tone="温暖纸质感 · 手作编辑排版 · 柔和氛围",
            palette=Palette(bg="#F7F3EC", acc="#8C5A3C", accent2="#3E7C59", txt="#2A2622"),
            font_stack="system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif",
            easing="cubic-bezier(0.22, 1, 0.36, 1)",
            modules=["Hero", "Works", "About", "Contact"],
        ),
        scaffold=ScaffoldPlan(
            stack="static-html",
            files=[
                FileSpec(path="index.html", purpose="单页骨架:Hero/Works/About/Contact 四模块"),
                FileSpec(path="css/style.css", purpose="设计令牌与版式"),
                FileSpec(path="js/main.js", purpose="入场与滚动编排入口"),
                FileSpec(path="js/reveal.js", purpose="IntersectionObserver 揭示调度"),
            ],
            deps=[],
        ),
    )


def good_animation() -> AnimationSpec:
    """合规的动画编排(可通过 gate_2 与 perf_audit 五项)。"""
    return AnimationSpec(
        entrance=[
            AnimRule(target=".hero__title", technique="translate", properties=["transform", "opacity"], duration_ms=600, delay_ms=0),
            AnimRule(target=".hero__item", technique="stagger", properties=["transform", "opacity"], duration_ms=500, delay_ms=120),
        ],
        scroll=[
            AnimRule(target=".card", technique="clip-reveal", properties=["clip-path", "opacity"], duration_ms=520, delay_ms=0),
        ],
        hover=[
            AnimRule(target=".card", technique="translate", properties=["transform"], duration_ms=200, delay_ms=0),
        ],
        reduced_motion_fallback="prefers-reduced-motion: reduce 时禁用全部入场/滚动动画,元素直接呈现静态排版",
        heavy_fx_pause_note="如引入 WebGL/重特效,将在视口外自动暂停渲染循环",
        listener_throttle_note="滚动与指针监听统一经 requestAnimationFrame 节流,每帧至多触发一次回调",
    )


def good_content() -> ContentPlan:
    """合规的内容方案(可通过 gate_4)。"""
    return ContentPlan(
        cards=[
            ContentCard(
                id="w01",
                tag="SIGNATURE",
                title="当季招牌",
                desc="手冲单品与季节特调的完整清单:豆种产地、风味描述与价格一目了然。",
                status="LIVE",
                span="wide",
                link=LinkSpec(label="查看", href="https://example.com/menu"),
            ),
            ContentCard(
                id="w02",
                tag="STORE",
                title="门店信息",
                desc="各门店地址、营业时间与预约方式,另含手冲体验课的报名入口。",
                status="LIVE",
                link=LinkSpec(label="前往", href="https://example.com/store"),
            ),
            ContentCard(
                id="w03",
                tag="GUIDE",
                title="手冲指南",
                desc="从研磨度到水温的入门教程:三段式注水手法与常见风味误区解析。",
                status="LIVE",
                link=LinkSpec(label="阅读", href="https://example.com/guide"),
            ),
        ],
        placeholders_removed=True,
    )


def poisoned_sample(node: str):
    """chaos 毒样本:可解析、门禁不过。node ∈ {s1, s2, s4}。"""
    if node == "s1":
        base = good_style_scaffold()
        bad_style = base.style.model_copy(
            update={
                "easing": "ease-in-out",  # 非 cubic-bezier → gate_1 违规
                "palette": base.style.palette.model_copy(update={"accent2": "purple"}),  # 非 hex
            }
        )
        return StyleScaffoldOut(style=bad_style, scaffold=base.scaffold)
    if node == "s2":
        return AnimationSpec(
            entrance=[
                AnimRule(  # 黑名单命中:blur( 且白名单外
                    target=".hero__title",
                    technique="settle",
                    properties=["filter: blur(6px)"],
                    duration_ms=600,
                    delay_ms=0,
                )
            ],
            scroll=[],
            hover=[],
            reduced_motion_fallback="",
        )
    if node == "s4":
        return ContentPlan(
            cards=[
                ContentCard(id="m01", tag="MENU", title="占位卡", desc="待补充", status="LIVE", link=None),
                ContentCard(  # href 含 .. → 路径穿越
                    id="s01", tag="STORE", title="外链卡", desc="描述文本足够长的一段说明。",
                    status="LIVE", link=LinkSpec(label="前往", href="../escape/index.html"),
                ),
            ],
            placeholders_removed=False,
        )
    raise ValueError(f"未知节点: {node}")
