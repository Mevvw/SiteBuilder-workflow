"""T1:gate_1 合法/非法样本;T2:gate_2 白名单/黑名单。"""
from workflow_chain.gates import (
    check_animation, check_style_scaffold, g1_style, g2_animation, route_g1, route_g2,
)
from workflow_chain.mock_data import good_animation, good_style_scaffold
from workflow_chain.state import AnimRule


def _state(**kw):
    base = {"rework_counts": {}, "gate_logs": [], "feedback": {}}
    base.update(kw)
    return base


def _fail_state(res: dict) -> dict:
    """把门禁节点的返回拼成可路由的最小状态。"""
    return {
        "gate_logs": res["gate_logs"],
        "rework_counts": res["rework_counts"],
        "feedback": res["feedback"],
    }


# ---------------- T1: gate_1 ----------------
def test_g1_valid_pass():
    out = good_style_scaffold()
    res = g1_style(_state(style=out.style, scaffold=out.scaffold))
    log = res["gate_logs"][0]
    assert log.verdict == "pass"
    assert log.violations == []
    assert route_g1(_state(**res), max_reworks=2) == "s2_animation"


def test_g1_missing_easing():
    out = good_style_scaffold()
    style = out.style.model_copy(update={"easing": "ease-in-out"})
    res = g1_style(_state(style=style, scaffold=out.scaffold))
    log = res["gate_logs"][0]
    assert log.verdict == "fail"
    assert any("缓动" in v for v in log.violations)
    assert log.violations[0].count("ease-in-out") == 1  # 违规信息准确


def test_g1_bad_hex():
    out = good_style_scaffold()
    style = out.style.model_copy(
        update={"palette": out.style.palette.model_copy(update={"accent2": "purple"})})
    violations = check_style_scaffold(style, out.scaffold)
    assert any("accent2" in v for v in violations)


def test_g1_missing_module():
    out = good_style_scaffold()
    style = out.style.model_copy(update={"modules": ["Hero", "Works"]})
    violations = check_style_scaffold(style, out.scaffold)
    assert any("Contact" in v for v in violations)


def test_g1_fail_routes_back_and_aborts():
    out = good_style_scaffold()
    style = out.style.model_copy(update={"easing": "ease-in-out"})
    res = g1_style(_state(style=style, scaffold=out.scaffold))
    state = _fail_state(res)
    assert route_g1(state, max_reworks=2) == "s1_style_framework"  # 首次失败 → 回炉
    state["rework_counts"]["s1"] = 3
    assert route_g1(state, max_reworks=2) == "abort"  # 超限 → abort


# ---------------- T2: gate_2 ----------------
def test_g2_valid_pass():
    anim = good_animation()
    res = g2_animation(_state(animation=anim))
    assert res["gate_logs"][0].verdict == "pass"
    assert route_g2(_state(**res), max_reworks=2) == "s3_performance"


def test_g2_blur_fail():
    anim = good_animation()
    anim.entrance[0] = AnimRule(target=".hero", technique="settle",
                                properties=["filter: blur(6px)"], duration_ms=600, delay_ms=0)
    res = g2_animation(_state(animation=anim))
    log = res["gate_logs"][0]
    assert log.verdict == "fail"
    assert any("blur" in v for v in log.violations)


def test_g2_bounce_fail():
    """黑名单只扫 properties 字符串:'transform: bounce(...)' 基名合法但关键词命中。"""
    anim = good_animation()
    anim.hover.append(AnimRule(target=".btn", technique="translate",
                               properties=["transform: bounce(0.4s)"], duration_ms=200, delay_ms=0))
    violations = check_animation(anim)
    assert any("bounce" in v for v in violations)


def test_g2_whitelist_only():
    """纯 transform/opacity/clip-path 全 pass。"""
    anim = good_animation()
    anim.entrance[0] = AnimRule(target=".x", technique="translate",
                                properties=["transform", "opacity", "clip-path"],
                                duration_ms=500, delay_ms=0)
    assert check_animation(anim) == []


def test_g2_missing_stagger_and_reduced_motion():
    anim = good_animation()
    anim.entrance = [AnimRule(target=".x", technique="translate",
                              properties=["transform"], duration_ms=300, delay_ms=0)]
    anim.reduced_motion_fallback = " "
    violations = check_animation(anim)
    assert any("stagger" in v for v in violations)
    assert any("reduced_motion_fallback" in v for v in violations)
