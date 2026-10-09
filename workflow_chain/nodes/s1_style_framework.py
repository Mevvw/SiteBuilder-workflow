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
    p = style.palette
    css = (
        f":root{{--bg:{p.bg};--acc:{p.acc};--accent2:{p.accent2};--txt:{p.txt};--ease:{style.easing}}}\n"
        f"body{{margin:0;background:var(--bg);color:var(--txt);font-family:{style.font_stack}}}\n"
        "header,section{min-height:60vh;padding:56px 24px;border-bottom:1px solid rgba(128,128,128,.25)}\n"
        "h1,h2{margin:0 0 16px;line-height:1.2}"
    )
    hero = f'<header id="hero"><h1>{style.site_type}</h1><p>{style.tone}</p></header>'
    mods = "\n".join(
        f'<section id="{m.lower()}"><h2>{m}</h2><p>{m} 模块(骨架占位,由内容步骤填充)</p></section>'
        for m in style.modules
    )
    return (
        '<!doctype html>\n<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{style.site_type}</title>\n<style>\n{css}\n</style>\n</head>\n"
        f"<body>\n{hero}\n{mods}\n</body>\n</html>\n"
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
