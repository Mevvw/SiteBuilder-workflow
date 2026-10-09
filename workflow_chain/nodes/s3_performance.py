"""s3_performance:③ 性能验证 —— 先调 perf_audit 确定性工具,LLM 仅解读结果(DESIGN.md §1/§2)。"""
from __future__ import annotations

from workflow_chain.console import step_log
from workflow_chain.state import PerfReport, WorkflowState
from workflow_chain.tools import perf_audit, write_artifact

SYSTEM = """你是性能评审员。用户会给你一份建站性能五项检查的 JSON 结果,
你只负责:① 用两三句话解读结果;② 若有失败项,按 owner(animation/scaffold)给出具体、可执行的修复建议。
不要重新发明检查规则,不要改动 JSON 结构。用中文,简洁。"""


def make_s3(runner, config=None):
    def s3_performance(state: WorkflowState) -> dict:
        anim, scaffold = state.get("animation"), state.get("scaffold")
        if anim is None or scaffold is None:
            raise RuntimeError("s3 前置缺失:animation/scaffold 未就绪(图拓扑错误)")
        audit = perf_audit(anim, scaffold)  # 确定性工具:规则唯一事实来源
        d = state["artifacts_dir"]
        write_artifact(d, "03-perf-raw.json", audit.model_dump_json(indent=2))

        failed = [c for c in audit.checks if not c.passed]
        ask = (
            "五项检查结果(JSON):\n" + audit.model_dump_json(indent=2)
            + ("\n\n请解读失败项并给出修复建议。" if failed else "\n\n全部通过,请给一句简短结论。")
        )
        advice = runner.complete(SYSTEM, ask)
        report = PerfReport(checks=audit.checks, all_pass=audit.all_pass, advice=advice)
        lines = ["# 03 · 性能报告", ""]
        for c in report.checks:
            mark = "✅" if c.passed else "❌"
            lines.append(f"- {mark} **{c.check}**(owner={c.owner}):{c.detail}")
        lines += ["", f"**总判定**:{'全部通过' if report.all_pass else '存在失败项'}",
                  "", f"**评审意见**:{advice}"]
        write_artifact(d, "03-perf-report.md", "\n".join(lines) + "\n")
        step_log("s3", f"性能审计完成:{'全部通过' if report.all_pass else f'{len(failed)} 项未通过'}")
        return {"perf": report}

    return s3_performance
