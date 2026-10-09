"""abort:回炉超限或致命错误收口,写 abort-report.json,status=aborted(DESIGN.md §1/§6)。"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from workflow_chain.console import step_log
from workflow_chain.llm import Budget
from workflow_chain.tools import redact_secrets, write_artifact


def _report_dict(state: dict, error: str, budget: Budget) -> dict:
    cfg = dict(state.get("config") or {})
    cfg["api_key"] = "***"
    return {
        "run_id": state.get("run_id"),
        "brief": state.get("brief"),
        "status": "aborted",
        "error": error,
        "budget_exceeded": "预算" in error or "budget" in error.lower(),
        "started_at": state.get("started_at"),
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "gate_logs": [g.model_dump() for g in (state.get("gate_logs") or [])],
        "rework_counts": state.get("rework_counts") or {},
        "usage": budget.snapshot(),
        "config": cfg,
    }


def make_abort(budget: Budget):
    def abort(state) -> dict:
        error = state.get("error") or "门禁回炉超限"
        text = json.dumps(_report_dict(state, error, budget), ensure_ascii=False, indent=2, default=str)
        write_artifact(state["artifacts_dir"], "abort-report.json", redact_secrets(text))
        step_log("abort", f"流程中止:{error}")
        return {"status": "aborted", "error": error,
                "ended_at": datetime.now().isoformat(timespec="seconds")}

    return abort


def write_crash_abort(artifacts_dir: str, run_id: str, brief: str, error: str,
                      budget: Budget, config) -> None:
    """图外异常(FatalLLMError / FatalBudgetError / 未预期异常)时无最终 state,直接落报告。"""
    state = {
        "run_id": run_id, "brief": brief, "artifacts_dir": artifacts_dir,
        "config": asdict(config), "started_at": None,
    }
    text = json.dumps(_report_dict(state, error, budget), ensure_ascii=False, indent=2, default=str)
    write_artifact(artifacts_dir, "abort-report.json", redact_secrets(text))
