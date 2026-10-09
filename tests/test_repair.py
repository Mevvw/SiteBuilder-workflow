"""T8:解析失败自修复 —— 第一次坏 JSON、第二次好 JSON → 成功,重试计数 = 1。"""
import json

import pytest

from workflow_chain.llm import BaseRunner, Budget, FatalLLMError
from workflow_chain.mock_data import good_animation
from workflow_chain.state import AnimationSpec


class StubRunner(BaseRunner):
    """_ask_json 按预设队列回复,用于纯离线验证修复循环。"""

    def __init__(self, replies: list[str]):
        super().__init__(Budget())
        self.replies = list(replies)
        self.notes: list[str | None] = []

    def _ask_json(self, system, user, repair_note=None):
        self.notes.append(repair_note)
        return self.replies.pop(0) if self.replies else "still bad"


def test_repair_once():
    good = json.dumps(good_animation().model_dump())
    runner = StubRunner(["这不是 JSON {{", good])
    out = runner.structured(AnimationSpec, "sys", "user")
    assert isinstance(out, AnimationSpec)
    assert runner.last_repairs == 1
    # 修复 prompt 只附「解析错误 + 原输出前 2000 字符」
    assert runner.notes[1] is not None
    assert "上次输出(前 2000 字符)" in runner.notes[1]
    assert "这不是 JSON {{" in runner.notes[1]


def test_repair_exhausted_raises_fatal():
    runner = StubRunner(["bad1", "bad2", "bad3"])
    with pytest.raises(FatalLLMError):
        runner.structured(AnimationSpec, "sys", "user")
    assert runner.last_repairs == 2  # 最多 2 次修复


def test_repair_recovers_from_schema_violation():
    """JSON 可解析但缺字段 → schema 校验失败 → 修复成功。"""
    bad = json.dumps({"entrance": []})  # 缺 reduced_motion_fallback
    good = json.dumps(good_animation().model_dump())
    runner = StubRunner([bad, good])
    out = runner.structured(AnimationSpec, "sys", "user")
    assert isinstance(out, AnimationSpec)
    assert runner.last_repairs == 1


def test_extract_json_strips_code_fence():
    from workflow_chain.llm import _extract_json
    obj, err = _extract_json('```json\n{"a": 1}\n```')
    assert obj == {"a": 1} and err is None
    obj2, err2 = _extract_json('前言 {"a": {"b": 2}} 后记')
    assert obj2 == {"a": {"b": 2}} and err2 is None
    obj3, err3 = _extract_json("完全没有对象")
    assert obj3 is None and err3
