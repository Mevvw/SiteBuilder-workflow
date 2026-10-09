"""finalize:汇总产物 + 门禁日志 + 用量,写 run-report.json,status=done(DESIGN.md §1)。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from workflow_chain.console import step_log
from workflow_chain.llm import Budget
from workflow_chain.tools import redact_secrets, write_artifact


def make_finalize(budget: Budget):
    def finalize(state) -> dict:
        d = state["artifacts_dir"]
        files = sorted(
            str(p.relative_to(Path(d))) for p in Path(d).rglob("*") if p.is_file()
        )
        cfg = dict(state.get("config") or {})
        cfg["api_key"] = "***"  # 双保险(落盘前还有 redact_secrets)
        ended = datetime.now().isoformat(timespec="seconds")
        report = {
            "run_id": state.get("run_id"),
            "brief": state.get("brief"),
            "status": "done",
            "started_at": state.get("started_at"),
            "ended_at": ended,
            "artifacts": files,
            "gate_logs": [g.model_dump() for g in (state.get("gate_logs") or [])],
            "rework_counts": state.get("rework_counts") or {},
            "usage": budget.snapshot(),
            "config": cfg,
        }
        text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        write_artifact(d, "run-report.json", redact_secrets(text))
        step_log("finalize", f"全部完成:{len(files)} 个产物,报告 run-report.json")
        return {"status": "done", "ended_at": ended, "usage": budget.snapshot()}

    return finalize
