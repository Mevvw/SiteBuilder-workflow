"""T16~T18:多 Agent 能力 —— 按节点模型 / s3 工具循环取证 / 对抗评审。"""
import json
from pathlib import Path

import pytest

from workflow_chain.config import ConfigError, RunConfig, make_config
from workflow_chain.graph import run_chain


def _config(**kw) -> RunConfig:
    base = dict(provider="mock", model="mock-1", structured_output_mode="mock", max_reworks=2)
    base.update(kw)
    return RunConfig(**base)


# ---------------- T16:按节点覆盖模型 ----------------
def test_t16_node_models_parsed_into_config():
    cfg = make_config("mock", node_models={"s1": "mock-a", "s4": "mock-b"})
    assert cfg.node_models == {"s1": "mock-a", "s4": "mock-b"}
    assert "node_models" in cfg.as_dict()  # 报告可见


def test_t16_invalid_node_key_raises():
    with pytest.raises(ConfigError, match="node_models"):
        make_config("mock", node_models={"s9": "x"})


def test_t16_per_node_runners_in_report(tmp_path):
    """node_models 走完整链:配置进报告,门禁行为不变。"""
    cfg = make_config("mock", node_models={"s1": "any", "s2": "any"},
                      structured_output_mode="mock")
    final = run_chain("咖啡品牌官网", cfg, artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    report = json.loads((Path(final["artifacts_dir"]) / "run-report.json").read_text("utf-8"))
    assert report["config"]["node_models"] == {"s1": "any", "s2": "any"}


# ---------------- T17:s3 工具循环取证 ----------------
def test_t17_tool_loop_evidence_in_mock_run(tmp_path):
    final = run_chain("咖啡品牌官网", _config(), artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    d = Path(final["artifacts_dir"])
    md = (d / "03-perf-report.md").read_text("utf-8")
    assert "工具循环" in md and "首屏入场预算" in md  # mock 脚本化取证落到报告
    assert "## 工具取证" in md
    raw = json.loads((d / "03-perf-raw.json").read_text("utf-8"))
    assert [e["tool"] for e in raw["tool_evidence"]] == ["entrance_budget", "deps_weight"]
    assert raw["tool_evidence"][0]["result"]["entrance_rules"] == 2  # mock 编排入场 2 条


# ---------------- T18:对抗评审 ----------------
def test_t18_review_pass_by_default(tmp_path):
    final = run_chain("咖啡品牌官网", _config(), artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    d = Path(final["artifacts_dir"])
    assert (d / "05-review.md").exists()
    report = json.loads((d / "run-report.json").read_text("utf-8"))
    assert report["review"]["verdict"] == "pass"
    assert report["review"]["score"] == 8


def test_t18_review_revise_then_pass(tmp_path):
    """chaos s5:1:首轮评审判 revise → 打回 s4 重写 → 二轮通过(对抗自愈)。"""
    final = run_chain("咖啡品牌官网", _config(), chaos={"s5": 1},
                      artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    report = json.loads((Path(final["artifacts_dir"]) / "run-report.json").read_text("utf-8"))
    assert report["rework_counts"] == {"s4": 1}
    assert report["review"]["verdict"] == "pass"
    assert report["review"]["score"] == 8


def test_t18_no_review_skips_node(tmp_path):
    final = run_chain("咖啡品牌官网", _config(enable_review=False),
                      artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    d = Path(final["artifacts_dir"])
    assert not (d / "05-review.md").exists()
    report = json.loads((d / "run-report.json").read_text("utf-8"))
    assert report["review"] is None
    assert report["config"]["enable_review"] is False
