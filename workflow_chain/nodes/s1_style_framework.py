"""s1_style_framework:① 定风格 + 搭框架(DESIGN.md §2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import StyleScaffoldOut, WorkflowState
from workflow_chain.tools import write_artifact

SYSTEM = """你是资深建站架构师。根据需求简述(与回炉反馈)产出风格决策与框架方案。
硬性规则(门禁将逐条校验,违反即回炉):
1. 色板四值 palette.bg/acc/accent2/txt 必须全部为 #RRGGBB 或 #RGB 的 hex 颜色;
2. easing 必须是 cubic-bezier(...) 形式的缓动曲线;
3. modules 必须包含 Hero、Works、Contact;
4. font_stack 只能用系统字体栈,严禁 http/url(/@import/@font-face 等外链字体;
5. scaffold.files 至少 3 项,路径为相对路径且不含 ..;
6. deps 只列真实需要的;若含 three/gsap 等重依赖,必须在 bundle_note 写明分包或懒加载策略。

风格取向(除非需求简述明确要求其他方向,默认遵守):高级、简洁、现代,克制的科技感/未来感,留白充分、层次分明;视觉手法优先细网格、微弱光晕、噪点、细线条等轻量元素,避免大色块堆砌;三条禁忌 —— 不过度赛博朋克、不做普通 SaaS 官网感、不做传统设计师作品集模板感;桌面端优先设计,同时兼顾移动端(模块结构与文案在窄屏下不塌陷)。注意:tone 字段只写 12 字以内的风格关键词(如「温暖纸质感 · 手作编辑排版」),严禁把上述取向说明复述进 tone。

若存在【上次回炉反馈】,必须逐条修复,严禁重犯。"""


def _render_md(style, scaffold) -> str:
    p = style.palette
    lines = [
        "# 01 · 风格决策与框架方案",
        "",
        f"- **网站类型**:{style.site_type}",
        f"- **风格基调**:{style.tone}",
        f"- **色板**:bg `{p.bg}` / acc `{p.acc}` / accent2 `{p.accent2}` / txt `{p.txt}`",
        f"- **字体栈**:`{style.font_stack}`(仅系统字体)",
        f"- **统一缓动**:`{style.easing}`",
        f"- **模块清单**:{' / '.join(style.modules)}",
        "",
        "## 框架文件",
        "",
    ]
    lines += [f"- `{f.path}` —— {f.purpose}" for f in scaffold.files]
    if scaffold.deps:
        lines += ["", f"**依赖**:{', '.join(scaffold.deps)}"]
        if scaffold.bundle_note:
            lines += [f"", f"**分包/懒加载说明**:{scaffold.bundle_note}"]
    return "\n".join(lines) + "\n"


def _render_index_html(style) -> str:
    """线框骨架页:演示文案 + 占位卡片 + 模块结构,色板/字体/缓动实际生效。

    确定性渲染(不依赖 LLM 产出 HTML):所有注入文本经 html.escape,
    占位元素只用 transform/opacity 悬停反馈,与工作流自身的动画规则保持一致。
    """
    import html as _html

    def esc(s: str) -> str:
        return _html.escape(str(s), quote=True)

    p = style.palette
    site = esc(style.site_type)
    mods = [str(m) for m in style.modules]

    css = (
        f":root{{--bg:{p.bg};--acc:{p.acc};--accent2:{p.accent2};--txt:{p.txt};--ease:{style.easing}}}\n"
        "*{box-sizing:border-box}\n"
        f"body{{margin:0;background-color:var(--bg);color:var(--txt);font-family:{style.font_stack};line-height:1.65;"
        "background-image:"
        "radial-gradient(ellipse 62% 46% at 10% -6%,color-mix(in srgb,var(--acc) 10%,transparent),transparent 72%),"
        "radial-gradient(ellipse 56% 42% at 90% -2%,color-mix(in srgb,var(--accent2) 8%,transparent),transparent 72%),"
        "linear-gradient(color-mix(in srgb,var(--txt) 5%,transparent) 1px,transparent 1px),"
        "linear-gradient(90deg,color-mix(in srgb,var(--txt) 5%,transparent) 1px,transparent 1px);"
        "background-size:auto,auto,44px 44px,44px 44px;background-attachment:fixed}\n"
        "a{color:inherit;text-decoration:none}\n"
        ".wrap{max-width:1060px;margin:0 auto;padding:0 28px}\n"
        "nav{position:sticky;top:0;z-index:9;backdrop-filter:blur(10px);border-bottom:1px solid rgba(128,128,128,.18)}\n"
        "nav .wrap{display:flex;align-items:center;justify-content:space-between;height:58px}\n"
        ".brand{font-weight:700}\n"
        "nav .links{display:flex;gap:22px;font-size:14px;opacity:.85;flex-wrap:wrap}\n"
        ".eyebrow{display:inline-block;font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent2);margin-bottom:14px}\n"
        "h1{font-size:clamp(34px,6vw,64px);line-height:1.12;margin:0 0 18px}\n"
        "h2{font-size:clamp(24px,3.4vw,34px);margin:0 0 10px}\n"
        ".lede{max-width:56ch;opacity:.75;margin:0 0 28px}\n"
        ".note{font-size:13px;opacity:.55;margin:0 0 34px}\n"
        ".btn{display:inline-block;padding:11px 26px;border-radius:999px;border:1px solid var(--acc);font-size:15px;transition:transform .3s var(--ease),opacity .3s var(--ease)}\n"
        ".btn:hover{transform:translateY(-2px);opacity:.9}\n"
        ".btn--solid{background:var(--acc);color:var(--bg);margin-right:12px}\n"
        ".btn--ghost{color:var(--acc)}\n"
        "section{padding:84px 0;border-top:1px solid rgba(128,128,128,.16)}\n"
        "#hero{padding-top:96px;padding-bottom:96px}\n"
        ".grid{display:grid;gap:22px}\n"
        ".grid--3{grid-template-columns:repeat(3,1fr)}\n"
        ".grid--2{grid-template-columns:1.1fr .9fr}\n"
        "@media(max-width:860px){.grid--3,.grid--2{grid-template-columns:1fr}}\n"
        ".card{border:1px dashed rgba(128,128,128,.45);border-radius:16px;padding:18px;background:rgba(128,128,128,.06)}\n"
        ".ph{height:150px;border-radius:10px;display:grid;place-items:center;font-size:13px;letter-spacing:.14em;"
        "background:linear-gradient(135deg,color-mix(in srgb,var(--acc) 26%,transparent),color-mix(in srgb,var(--accent2) 20%,transparent));"
        "border:1px solid rgba(128,128,128,.25)}\n"
        ".hero-visual{height:230px;margin-top:44px}\n"
        ".chip{display:inline-block;font-size:11px;letter-spacing:.12em;padding:3px 10px;border:1px solid var(--accent2);border-radius:999px;color:var(--accent2);margin:14px 0 8px}\n"
        ".bar{height:11px;border-radius:6px;background:rgba(128,128,128,.28);margin-top:10px}\n"
        ".bar--w80{width:82%}.bar--w60{width:60%}.bar--w40{width:42%}\n"
        ".stat{text-align:center;padding:22px 10px;border:1px dashed rgba(128,128,128,.45);border-radius:14px}\n"
        ".stat b{display:block;font-size:30px;color:var(--acc)}\n"
        ".stat span{font-size:12px;letter-spacing:.14em;opacity:.6}\n"
        ".row{display:flex;align-items:center;gap:14px;padding:13px 0;border-bottom:1px solid rgba(128,128,128,.16)}\n"
        ".dot{width:9px;height:9px;border-radius:50%;background:var(--accent2);flex:none}\n"
        ".row .bar{flex:1;margin:0}\n"
        ".input{height:46px;border:1px solid rgba(128,128,128,.4);border-radius:10px;display:flex;align-items:center;padding:0 14px;font-size:13px;opacity:.55;margin-bottom:12px}\n"
        ".input--area{height:110px;align-items:flex-start;padding-top:12px}\n"
        "footer{padding:34px 0;font-size:13px;opacity:.55;border-top:1px solid rgba(128,128,128,.16)}\n"
        "footer .wrap{display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}\n"
    )

    def card(n: int) -> str:
        return "".join(
            '<div class="card"><div class="ph">图片占位</div><span class="chip">TAG</span>'
            '<div class="bar bar--w80"></div><div class="bar bar--w60"></div><div class="bar bar--w40"></div></div>'
            for _ in range(n)
        )

    hero = (
        f'<header id="hero"><div class="wrap">\n'
        f'<span class="eyebrow">{site} · 线框骨架</span>\n'
        f"<h1>XX 公司</h1>\n"
        f'<p class="lede">「XX 公司」为临时演示文字,将被真实名称替换;本页由 site-workflow-chain 自动生成,'
        f'色板、字体栈与缓动曲线已实际注入 —— 第四步「内容替换」会用真实内容填充。</p>\n'
        f'<a class="btn btn--solid" href="#works">浏览内容</a>'
        f'<a class="btn btn--ghost" href="#contact">联系我们</a>\n'
        f'<div class="ph hero-visual">首屏视觉区占位(大图 / 光柱 / 插画位)</div>\n'
        f"</div></header>"
    )

    def works_sec() -> str:
        return (
            '<section id="works"><div class="wrap">\n'
            '<span class="eyebrow">Works</span>\n<h2>精选内容</h2>\n'
            '<p class="note">占位卡片 × 3 —— 内容替换后,每张卡为真实条目(标题、描述、链接、状态)。</p>\n'
            f'<div class="grid grid--3">{card(3)}</div>\n'
            "</div></section>"
        )

    def about_sec() -> str:
        return (
            '<section id="about"><div class="wrap">\n'
            '<span class="eyebrow">About</span>\n<h2>关于我们</h2>\n'
            '<p class="note">左栏为介绍文案占位(骨架条),右栏为三项数据指标占位。</p>\n'
            '<div class="grid grid--2">\n<div>\n'
            '<div class="bar bar--w80"></div><div class="bar"></div><div class="bar"></div><div class="bar bar--w60"></div>\n'
            "</div>\n"
            '<div class="grid grid--3">'
            '<div class="stat"><b>00+</b><span>指标占位</span></div>'
            '<div class="stat"><b>00+</b><span>指标占位</span></div>'
            '<div class="stat"><b>00</b><span>指标占位</span></div>'
            "</div>\n</div>\n</div></section>"
        )

    def contact_sec() -> str:
        return (
            '<section id="contact"><div class="wrap">\n'
            '<span class="eyebrow">Contact</span>\n<h2>联系方式</h2>\n'
            '<p class="note">左栏为联系信息占位,右栏为表单占位 —— 内容替换时填入真实邮箱/电话/地址。</p>\n'
            '<div class="grid grid--2">\n<div>\n'
            '<div class="row"><span class="dot"></span><div class="bar bar--w40"></div></div>\n'
            '<div class="row"><span class="dot"></span><div class="bar bar--w60"></div></div>\n'
            '<div class="row"><span class="dot"></span><div class="bar bar--w80"></div></div>\n'
            "</div>\n<div>\n"
            '<div class="input">输入项占位</div>\n<div class="input">输入项占位</div>\n'
            '<div class="input input--area">多行输入占位</div>\n'
            '<a class="btn btn--solid" href="#contact">提交占位</a>\n'
            "</div>\n</div>\n</div></section>"
        )

    def generic_sec(m: str) -> str:
        mid = esc(m.lower())
        return (
            f'<section id="{mid}"><div class="wrap">\n'
            f'<span class="eyebrow">{esc(m)}</span>\n<h2>{esc(m)}</h2>\n'
            f'<p class="note">模块占位:卡片网格为演示结构,内容替换时按需调整。</p>\n'
            f'<div class="grid grid--3">{card(2)}</div>\n'
            f"</div></section>"
        )

    nav = (
        f'<nav><div class="wrap"><span class="brand">XX 公司</span>'
        f'<div class="links">' + "".join(f'<a href="#{esc(m.lower())}">{esc(m)}</a>' for m in mods) + "</div></div></nav>"
    )

    parts = [nav, hero]
    for m in mods:
        key = m.strip().lower()
        if key == "hero":
            continue
        if key == "works":
            parts.append(works_sec())
        elif key == "about":
            parts.append(about_sec())
        elif key == "contact":
            parts.append(contact_sec())
        else:
            parts.append(generic_sec(m))
    parts.append(
        f'<footer><div class="wrap"><span>© XX 公司</span>'
        f"<span>线框骨架 · 由 site-workflow-chain 生成</span></div></footer>"
    )

    body = "\n".join(parts)
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{site}</title>\n<style>\n{css}\n</style>\n</head>\n"
        f"<body>\n{body}\n</body>\n</html>\n"
    )


def make_s1(runner, config=None):
    def s1_style_framework(state: WorkflowState) -> dict:
        fb = (state.get("feedback") or {}).get("s1")
        user = f"【需求简述】\n{state['brief']}"
        if fb:
            user += f"\n\n【上次回炉反馈(必须逐条修复,严禁重犯)】\n{fb}"
        out = runner.structured(StyleScaffoldOut, SYSTEM, user)
        style, scaffold = out.style, out.scaffold
        d = state["artifacts_dir"]
        write_artifact(d, "01-style-and-scaffold.md", _render_md(style, scaffold))
        write_artifact(d, "scaffold/index.html", _render_index_html(style))
        step_log("s1", f"风格+框架就绪({len(scaffold.files)} 个文件,模块:{'/'.join(style.modules)})")
        # 成功后显式清除 s1 回炉反馈(None 值 = 删除该键)
        return {"style": style, "scaffold": scaffold, "feedback": {"s1": None}}

    return s1_style_framework
