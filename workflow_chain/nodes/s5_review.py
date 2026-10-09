"""s5_review:对抗式评审 agent —— 主观质量把关,与确定性门禁互补(DESIGN.md §1/§2)。

门禁查「确定性规则」(链接合法/字数/数量),s5 挑「门禁查不出来但会让人皱眉」的问题
(文案力度/叙事层次/风格契合)。revise → 写 s4 反馈走回炉复用机制(≤max_reworks,超限 abort)。
"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import ReviewResult, WorkflowState
from workflow_chain.tools import write_artifact

SYSTEM = """你是苛刻但专业的创意总监,对内容方案做主观质量评审(红蓝对抗的挑刺方):
① 文案力度 —— 是否空洞、套话、形容词堆砌;
② 叙事层次 —— wide/full 跨度是否讲出了重点故事,还是均质罗列;
③ 风格契合 —— 是否贴合需求简述的基调与网站类型。
确定性规则(链接合法性/字数/卡片数量)由门禁负责,你不要重复检查,只挑上面三类问题。
输出 verdict:pass(可交付)或 revise(需返工);revise 时 notes 必须给出 ≤3 条可执行的具体修改指令。
若用户消息注明上次反馈应已修正,请基于新版重新评判,不要为了挑刺而挑刺。"""


def make_s5(runner, config=None):
    def s5_review(state: WorkflowState) -> dict:
        brief, style, content = state.get("brief"), state.get("style"), state.get("content")
        fb = (state.get("feedback") or {}).get("s4")  # 上轮评审/门禁给 s4 的反馈
        user = (
            f"【需求】{brief}\n【基调】{style.site_type} · {style.tone}\n"
            f"【内容方案】{content.model_dump_json(indent=2)}"
        )
        if fb:
            user += f"\n\n【上次评审反馈(应已修正,请基于新版重新评判)】\n{fb}"

        review: ReviewResult = runner.structured(ReviewResult, SYSTEM, user)
        d = state["artifacts_dir"]
        lines = [
            "# 05 · 对抗评审(主观质量)",
            "",
            f"- **结论**:{'通过 ✓' if review.verdict == 'pass' else '需返工 ✗'}(评分 {review.score}/10)",
        ]
        lines += [f"- {n}" for n in review.notes] or ["- (无备注)"]
        write_artifact(d, "05-review.md", "\n".join(lines) + "\n")
        step_log("s5", f"对抗评审:{review.verdict}({review.score}/10,{len(review.notes)} 条备注)")

        if review.verdict == "revise":
            counts = dict(state.get("rework_counts") or {})
            counts["s4"] = counts.get("s4", 0) + 1
            feedback = {"s4": "; ".join(review.notes)} if review.notes else {}
            return {"review": review, "rework_counts": counts, "feedback": feedback}
        return {"review": review}

    return s5_review
