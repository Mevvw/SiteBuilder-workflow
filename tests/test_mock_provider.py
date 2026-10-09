"""T7:mock provider —— 固定输出通过全部 schema 解析;T7b:chaos 第一次毒、第二次好。"""
from workflow_chain.llm import Budget, MockRunner
from workflow_chain.mock_data import good_animation
from workflow_chain.state import AnimationSpec, ContentPlan, StyleScaffoldOut


def test_mock_structured_all_schemas():
    budget = Budget()
    runner = MockRunner(budget)
    s1 = runner.structured(StyleScaffoldOut, "sys", "user")
    assert isinstance(s1.style.palette.bg, str)
    s2 = runner.structured(AnimationSpec, "sys", "user")
    assert isinstance(s2, AnimationSpec)
    s4 = runner.structured(ContentPlan, "sys", "user")
    assert isinstance(s4, ContentPlan)
    assert budget.usage["llm_calls"] == 3


def test_mock_complete_counts_budget():
    budget = Budget()
    runner = MockRunner(budget)
    text = runner.complete("sys", "user")
    assert "[mock]" in text
    assert budget.usage["llm_calls"] == 1


def test_mock_chaos_first_call_poisoned_then_clean():
    runner = MockRunner(Budget(), chaos={"s2": 1})
    a1 = runner.structured(AnimationSpec, "sys", "user")
    props = " ".join(p for r in a1.entrance for p in r.properties)
    assert "blur(" in props  # 第一次:毒样本,可解析但门禁会打回
    a2 = runner.structured(AnimationSpec, "sys", "user")
    props2 = " ".join(p for r in [*a2.entrance, *a2.scroll, *a2.hover] for p in r.properties)
    assert "blur(" not in props2  # 第二次:合规
    assert a2.entrance == good_animation().entrance  # 与内置合规样例一致


def test_mock_chaos_zero_means_always():
    runner = MockRunner(Budget(), chaos={"s2": 0})
    for _ in range(3):
        a = runner.structured(AnimationSpec, "sys", "user")
        assert any("blur(" in p for r in a.entrance for p in r.properties)


def test_mock_respects_call_budget():
    runner = MockRunner(Budget(max_total_tokens=200_000, max_llm_calls=2))
    runner.complete("s", "u")
    runner.complete("s", "u")
    from workflow_chain.llm import FatalBudgetError
    try:
        runner.complete("s", "u")
        raise AssertionError("应当触发 FatalBudgetError")
    except FatalBudgetError:
        pass
