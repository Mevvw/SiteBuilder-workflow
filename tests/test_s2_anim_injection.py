"""T15:s2 将编排真正注入骨架页(动画不再停留在文档里)。"""
from pathlib import Path

from workflow_chain.config import RunConfig
from workflow_chain.graph import run_chain


def _config() -> RunConfig:
    return RunConfig(provider="mock", model="mock-1", structured_output_mode="mock", max_reworks=2)


def test_skeleton_has_animations_after_run(tmp_path):
    final = run_chain("咖啡品牌官网", _config(), artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")

    html = (Path(final["artifacts_dir"]) / "scaffold" / "index.html").read_text("utf-8")
    assert "<h1>XX 公司</h1>" in html  # 演示标题(非 tone 描述串)
    assert "@keyframes" in html  # 入场/揭示关键帧已注入
    assert "IntersectionObserver" in html  # 滚动揭示脚本
    assert "prefers-reduced-motion" in html  # 降级覆盖
    assert "wf-fade-up" in html and "wf-clip-in" in html  # mock 编排含 stagger+clip-reveal → 两种手法都在


def test_chaos_self_heal_rewrites_clean_animations(tmp_path):
    """chaos s2:1:第一次毒编排(blur)被打回,重跑后骨架页注入的是合规动画。"""
    final = run_chain("咖啡品牌官网", _config(), chaos={"s2": 1}, artifacts_root=str(tmp_path / "out"))
    assert final["status"] == "done", final.get("error")
    html = (Path(final["artifacts_dir"]) / "scaffold" / "index.html").read_text("utf-8")
    assert "blur(6px)" not in html  # 毒样本属性未残留(nav 的 backdrop-filter:blur(10px) 是骨架自带,不算)
    assert "@keyframes" in html
    report = None
    report_path = Path(final["artifacts_dir"]) / "run-report.json"
    import json
    report = json.loads(report_path.read_text("utf-8"))
    assert report["rework_counts"] == {"s2": 1}  # 确认确实经历了一次回炉重写
