"""s4_content:④ 内容替换(DESIGN.md §2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import ContentPlan, WorkflowState
from workflow_chain.tools import write_artifact

SYSTEM = """你是内容策划。基于需求简述与上游产物,产出作品卡内容方案。
硬性规则(门禁将逐条校验,违反即回炉):
1. placeholders_removed 必须为 true(占位内容全部清零);
2. 每张卡 desc 至少 8 个字,写具体卖点,不写"待补充/占位";
3. link.href 仅允许 https?:// 开头的真实链接,或不含 .. 的相对路径;严禁虚构不存在的对外网址 —— 不确定就给相对路径;
4. status ∈ LIVE/PLANNED/RESERVED,且 LIVE 卡必须带 link。
若存在【上次回炉反馈】,必须逐条修复,严禁重犯。"""


def _render_md(plan: ContentPlan) -> str:
    lines = ["# 04 · 内容方案", ""]
    for c in plan.cards:
        link = f"[{c.link.label}]({c.link.href})" if c.link else "(无)"
        lines.append(f"- **{c.title}** `{c.tag}` · {c.status} · {link}\n  {c.desc}")
    lines.append("")
    lines.append(f"**占位清零**:{'是' if plan.placeholders_removed else '否'}")
    return "\n".join(lines) + "\n"


def make_s4(runner, config=None):
    def s4_content(state: WorkflowState) -> dict:
        style, scaffold, anim, perf = (
            state.get("style"), state.get("scaffold"), state.get("animation"), state.get("perf"),
        )
        fb = (state.get("feedback") or {}).get("s4")
        summary = (
            f"【需求】{state['brief']}\n"
            f"【风格】{style.site_type} · {style.tone}\n"
            f"【框架】{scaffold.stack},模块 {'/'.join(style.modules)}\n"
            f"【动效】入场 {len(anim.entrance)} 段 / 滚动 {len(anim.scroll)} 段\n"
            f"【性能】{'五项全过' if perf.all_pass else '存在待修项(见性能报告)'}"
        )
        user = summary
        if fb:
            user += f"\n\n【上次回炉反馈(必须逐条修复,严禁重犯)】\n{fb}"
        plan = runner.structured(ContentPlan, SYSTEM, user)
        write_artifact(state["artifacts_dir"], "04-content-plan.md", _render_md(plan))
        step_log("s4", f"内容方案就绪({len(plan.cards)} 张卡)")
        return {"content": plan, "feedback": {"s4": None}}

    return s4_content
