"""T5:回炉上限 —— 每次都注入毒样本 → 第 3 次 gate_2 fail 路由到 abort。"""
import json
from pathlib import Path

from workflow_chain.config import RunConfig
from workflow_chain.graph import run_chain


def test_three_fails_abort(tmp_path):
    config = RunConfig(provider="mock", model="mock-1", structured_output_mode="mock", max_reworks=2)
    final = run_chain("博客站点", config, chaos={"s2": 0}, artifacts_root=str(tmp_path))

    assert final["status"] == "aborted", final.get("error")
    report = json.loads((Path(final["artifacts_dir"]) / "abort-report.json").read_text("utf-8"))
    assert report["rework_counts"]["s2"] == 3  # 初次 + 2 次回炉,第 3 次 fail 断环
    assert report["status"] == "aborted"
    g2_fails = [g for g in report["gate_logs"] if g["gate"] == "g2_animation" and g["verdict"] == "fail"]
    assert len(g2_fails) == 3
    # s3 及之后不应被执行
    assert not [g for g in report["gate_logs"] if g["gate"].startswith("g3")]
