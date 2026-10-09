"""T13:gate_4 内容卡数量门禁(3~6,可配置)与 span 层次字段。"""
from workflow_chain.gates import check_content, g4_content
from workflow_chain.mock_data import good_content
from workflow_chain.state import ContentCard


def test_count_below_min_fails():
    plan = good_content()
    plan.cards = plan.cards[:2]  # 3 → 2,内容本身合法,只缺数量
    v = check_content(plan, min_cards=3, max_cards=6)
    assert len(v) == 1 and "少于下限 3" in v[0]


def test_count_above_max_fails():
    plan = good_content()
    extra = [plan.cards[0].model_copy(update={"id": f"x{i:02d}"}) for i in range(4)]
    plan.cards = plan.cards + extra  # 3 + 4 = 7 张
    v = check_content(plan, min_cards=3, max_cards=6)
    assert len(v) == 1 and "超过上限 6" in v[0]


def test_count_within_range_passes():
    assert check_content(good_content(), min_cards=3, max_cards=6) == []


def test_count_reads_state_config():
    """g4_content 从 state.config 读取上下限:放宽到 1 后 2 张卡放行。"""
    plan = good_content()
    plan.cards = plan.cards[:2]
    state = {
        "content": plan,
        "config": {"min_cards": 1, "max_cards": 6},
        "rework_counts": {}, "gate_logs": [], "feedback": {},
    }
    res = g4_content(state)
    assert res["gate_logs"][0].verdict == "pass"


def test_span_field_default_and_values():
    card = ContentCard(id="a", tag="T", title="t", desc="足够长的描述文本。", status="LIVE",
                       span="wide")
    assert card.span == "wide"
    assert ContentCard(id="b", tag="T", title="t", desc="足够长的描述文本。", status="LIVE").span == ""
