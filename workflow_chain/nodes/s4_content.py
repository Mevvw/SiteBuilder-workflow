"""s4_content:④ 内容替换(DESIGN.md §2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import ContentPlan, WorkflowState
from workflow_chain.tools import write_artifact

SYSTEM = """你是内容策划。基于需求简述与上游产物,产出作品卡内容方案。
硬性规则(门禁将逐条校验,违反即回炉):
1. placeholders_removed 必须为 true(占位内容全部清零);
2. 卡片数量必须在 3~6 张(门禁可配置);展示要有层次感:用 span 字段标注版面跨度 —— 最重要的一张用 "wide"(跨 2 列)或 "full"(横贯全宽),其余留空,避免均质图片网格;
3. 每张卡 desc 至少 8 个字,写具体卖点,不写"待补充/占位";
4. link.href 仅允许 https?:// 开头的真实链接,或不含 .. 的相对路径;严禁虚构不存在的对外网址 —— 不确定就给相对路径;
5. status ∈ LIVE/PLANNED/RESERVED,且 LIVE 卡必须带 link;
6. 联系方式只保留姓名与联系方式(邮箱/电话/链接);严禁输出照片、年龄、所在地、工作年限等个人信息;
7. 严禁虚构项目、经历、客户、奖项或数据;没有依据的内容宁缺毋滥。
若存在【上次回炉反馈】,必须逐条修复,严禁重犯。"""


def _render_md(plan: ContentPlan) -> str:
    lines = ["# 04 · 内容方案", ""]
    for c in plan.cards:
        link = f"[{c.link.label}]({c.link.href})" if c.link else "(无)"
        span = f" · 跨度 `{c.span}`" if getattr(c, "span", "") else ""
        lines.append(f"- **{c.title}** `{c.tag}` · {c.status}{span} · {link}\n  {c.desc}")
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
