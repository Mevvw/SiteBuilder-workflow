"""T9:mock 全链 happy path;T10:chaos 注入回炉(核心演示,验证自愈)。"""
import json
from pathlib import Path

from workflow_chain.config import RunConfig
from workflow_chain.graph import run_chain

ARTIFACTS = [
    "01-style-and-scaffold.md",
    "scaffold/index.html",
    "02-animation-spec.md",
    "03-perf-raw.json",
    "03-perf-report.md",
    "04-content-plan.md",
    "run-report.json",
]


def _config() -> RunConfig:
    return RunConfig(provider="mock", model="mock-1", structured_output_mode="mock", max_reworks=2)


def test_t9_happy_path(tmp_path):
    final = run_chain("咖啡品牌官网", _config(), artifacts_root=str(tmp_path / "out"))

    assert final["status"] == "done", final.get("error")
    d = Path(final["artifacts_dir"])
    for f in ARTIFACTS:
        assert (d / f).exists(), f"缺少产物 {f}"

    report = json.loads((d / "run-report.json").read_text("utf-8"))
    assert report["status"] == "done"
    assert len(report["gate_logs"]) == 4
    assert all(g["verdict"] == "pass" for g in report["gate_logs"])
    assert {g["gate"] for g in report["gate_logs"]} == {"g1_style", "g2_animation", "g3_performance", "g4_content"}
    assert report["usage"]["llm_calls"] >= 4  # s1/s2 结构化 + s3 文本解读 + s4 结构化 = 4 次
    assert report["config"]["api_key"] == "***"  # 报告脱敏
    # 反馈字典已清空(消费后显式清除)
    assert not final.get("feedback")


def test_t10_chaos_self_heal(tmp_path):
    """--chaos s2:1:s2 第一次输出混入 blur → gate_2 打回 → 第二次合规 → 终态 done。"""
    final = run_chain("咖啡品牌官网", _config(), chaos={"s2": 1},
                      artifacts_root=str(tmp_path / "out"))

    assert final["status"] == "done", final.get("error")
    report = json.loads((Path(final["artifacts_dir"]) / "run-report.json").read_text("utf-8"))

    g2_logs = [g for g in report["gate_logs"] if g["gate"] == "g2_animation"]
    assert len(g2_logs) == 2
    assert g2_logs[0]["verdict"] == "fail"
    assert any("blur" in v for v in g2_logs[0]["violations"])
    assert g2_logs[1]["verdict"] == "pass"
    assert report["rework_counts"] == {"s2": 1}  # 恰好一次回炉记录
    # 自愈后的动画不再含 blur
    anim = final["animation"]
    assert "blur(" not in " ".join(p for r in [*anim.entrance, *anim.scroll, *anim.hover] for p in r.properties)
