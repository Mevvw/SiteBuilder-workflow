"""T4:perf_audit 五项检查(规则唯一事实来源)。"""
from workflow_chain.mock_data import good_animation, good_style_scaffold
from workflow_chain.state import AnimRule, ScaffoldPlan
from workflow_chain.tools import perf_audit


def test_blur_detected_with_owner():
    """构造含 filter: blur(6px) 的 spec → 恰好对应项 fail 且 owner=animation。"""
    anim = good_animation()
    anim.entrance[0] = AnimRule(target=".hero", technique="settle",
                                properties=["filter: blur(6px)"], duration_ms=600, delay_ms=0)
    audit = perf_audit(anim, good_style_scaffold().scaffold)
    failed = [c for c in audit.checks if not c.passed]
    assert len(failed) == 1
    assert failed[0].owner == "animation"
    assert "blur" in failed[0].detail
    assert audit.all_pass is False


def test_compliant_spec_all_pass():
    audit = perf_audit(good_animation(), good_style_scaffold().scaffold)
    assert audit.all_pass is True
    assert all(c.passed for c in audit.checks)
    assert len(audit.checks) == 5


def test_heavy_dep_without_note_fails_on_scaffold():
    """重依赖无分包说明 → ④ fail 且 owner=scaffold。"""
    scaffold = ScaffoldPlan(
        stack="static-html",
        files=[{"path": f"f{i}.html", "purpose": "p"} for i in range(3)],
        deps=["three"], bundle_note="",
    )
    audit = perf_audit(good_animation(), scaffold)
    c4 = [c for c in audit.checks if c.check.startswith("④")][0]
    assert c4.passed is False and c4.owner == "scaffold"
    assert audit.all_pass is False


def test_heavy_dep_with_note_passes():
    scaffold = ScaffoldPlan(
        stack="static-html",
        files=[{"path": f"f{i}.html", "purpose": "p"} for i in range(3)],
        deps=["three"], bundle_note="three 走动态 import 分包,进入 Works 视口才加载",
    )
    audit = perf_audit(good_animation(), scaffold)
    c4 = [c for c in audit.checks if c.check.startswith("④")][0]
    assert c4.passed is True


def test_layout_property_fails_check3():
    """布局抖动属性(width)→ ③ fail。"""
    anim = good_animation()
    anim.hover.append(AnimRule(target=".x", technique="translate",
                               properties=["width"], duration_ms=200, delay_ms=0))
    audit = perf_audit(anim, good_style_scaffold().scaffold)
    c3 = [c for c in audit.checks if c.check.startswith("③")][0]
    assert c3.passed is False and c3.owner == "animation"


def test_missing_throttle_note_fails_check3():
    anim = good_animation()
    anim.listener_throttle_note = ""
    audit = perf_audit(anim, good_style_scaffold().scaffold)
    c3 = [c for c in audit.checks if c.check.startswith("③")][0]
    assert c3.passed is False


def test_missing_reduced_motion_fails_check5():
    anim = good_animation()
    anim.reduced_motion_fallback = ""
    audit = perf_audit(anim, good_style_scaffold().scaffold)
    c5 = [c for c in audit.checks if c.check.startswith("⑤")][0]
    assert c5.passed is False
