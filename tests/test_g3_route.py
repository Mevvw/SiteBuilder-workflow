"""T3:gate_3 责任路由(只测路由;规则本身在 T4 测 perf_audit)。"""
from workflow_chain.gates import _log, g3_owner_step, g3_performance, route_g3
from workflow_chain.state import CheckResult, PerfReport


def _perf(owners: list[str]) -> PerfReport:
    return PerfReport(
        checks=[CheckResult(check=f"c{i}", passed=False, owner=o, detail="x")
                for i, o in enumerate(owners)],
        all_pass=False, advice="",
    )


def test_majority_wins():
    """失败项 owners=[animation, animation, scaffold] → 回 s2(多数)。"""
    assert g3_owner_step(_perf(["animation", "animation", "scaffold"]), {}) == "s2"


def test_tie_goes_to_smaller_rework_count():
    """平局 → 回 rework_counts 较小者(s1=0 < s2=2)。"""
    assert g3_owner_step(_perf(["animation", "scaffold"]), {"s2": 2, "s1": 0}) == "s1"


def test_only_scaffold_goes_to_s1():
    assert g3_owner_step(_perf(["scaffold"]), {}) == "s1"


def test_all_pass_returns_none():
    perf = PerfReport(checks=[CheckResult(check="c", passed=True, owner="animation", detail="ok")],
                      all_pass=True, advice="")
    assert g3_owner_step(perf, {}) is None


def test_route_pass_to_s4():
    perf = PerfReport(checks=[CheckResult(check="c", passed=True, owner="animation", detail="ok")],
                      all_pass=True, advice="")
    state = {"perf": perf, "rework_counts": {},
             "gate_logs": [_log("g3_performance", "pass", [])]}
    assert route_g3(state, max_reworks=2) == "s4_content"


def test_route_responsibility():
    state = {
        "perf": _perf(["animation", "scaffold"]),
        "rework_counts": {"s2": 2, "s1": 0},
        "gate_logs": [_log("g3_performance", "fail", ["x"])],
    }
    assert route_g3(state, max_reworks=2) == "s1_style_framework"


def test_route_abort_on_limit():
    state = {
        "perf": _perf(["animation"]),
        "rework_counts": {"s2": 3},
        "gate_logs": [_log("g3_performance", "fail", ["x"])],
    }
    assert route_g3(state, max_reworks=2) == "abort"


def test_g3_node_writes_feedback_to_responsible_step():
    """门禁节点把失败明细写进责任步的 feedback(与路由同函数裁决)。"""
    state = {"perf": _perf(["scaffold"]), "rework_counts": {}, "gate_logs": []}
    res = g3_performance(state)
    assert "s1" in res["feedback"] and "s2" not in res["feedback"]
    assert res["rework_counts"] == {"s1": 1}
