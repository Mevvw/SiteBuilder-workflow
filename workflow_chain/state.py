"""WorkflowState、Pydantic 产物模型与 reducer(DESIGN.md §2 / §3)。"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, TypedDict

from pydantic import BaseModel, Field


# ---------------- reducer ----------------
def append_list(left: list | None, right: list | None) -> list:
    """列表追加(gate_logs)。语义同 operator.add,但兼容初始值为缺失(None)。"""
    return list(left or []) + list(right or [])


def merge_dict(left: dict | None, right: dict | None) -> dict:
    """dict 合并;**值为 None 的键 = 删除该键**。

    回炉反馈的清除机制:消费节点重跑成功后返回 ``{"s1": None}``,
    经本 reducer 显式删除该键,杜绝旧反馈残留污染下一轮 prompt(DESIGN.md §3)。
    """
    merged = dict(left or {})
    for k, v in (right or {}).items():
        if v is None:
            merged.pop(k, None)
        else:
            merged[k] = v
    return merged


def add_dict(left: dict | None, right: dict | None) -> dict:
    """数值累加合并(usage 计数);其余类型覆盖。"""
    merged = dict(left or {})
    for k, v in (right or {}).items():
        if isinstance(v, (int, float)) and isinstance(merged.get(k), (int, float)):
            merged[k] = merged[k] + v
        else:
            merged[k] = v
    return merged


# ---------------- Pydantic 产物模型 ----------------
class Palette(BaseModel):
    """四色板。hex 合法性由 gate_1 校验(模型层不拦,让门禁给 LLM 可修复的明确反馈)。"""

    bg: str
    acc: str
    accent2: str
    txt: str


class StyleDecision(BaseModel):
    site_type: str
    tone: str
    palette: Palette
    font_stack: str
    easing: str
    modules: list[str]


class FileSpec(BaseModel):
    path: str
    purpose: str


class ScaffoldPlan(BaseModel):
    stack: Literal["static-html", "react-vite"]
    files: list[FileSpec] = Field(min_length=1)
    deps: list[str] = []
    bundle_note: str = ""  # 分包/懒加载说明;含重依赖时 perf_audit 检查④要求非空


class StyleScaffoldOut(BaseModel):
    """s1 的结构化输出包装。"""

    style: StyleDecision
    scaffold: ScaffoldPlan


class AnimRule(BaseModel):
    target: str
    technique: Literal[
        "mask-reveal", "translate", "settle", "clip-reveal", "parallax", "stagger", "color"
    ]  # 技法由 Literal 枚举在类型层封死,gate_2 无需再扫
    properties: list[str]  # 白名单 transform/opacity/clip-path,由 gate_2 与 perf_audit 检查
    duration_ms: int = Field(ge=80, le=2000)
    delay_ms: int = Field(ge=0, le=1500)


class AnimationSpec(BaseModel):
    entrance: list[AnimRule] = []
    scroll: list[AnimRule] = []
    hover: list[AnimRule] = []
    reduced_motion_fallback: str  # 必须≠空:prefers-reduced-motion 降级说明
    heavy_fx_pause_note: str = ""  # 重特效视口暂停说明(perf_audit 检查②)
    listener_throttle_note: str = ""  # 滚动/指针监听 rAF 节流说明(perf_audit 检查③)


class CheckResult(BaseModel):
    check: str
    passed: bool
    owner: Literal["animation", "scaffold", "content", "system"]
    detail: str


class AuditRaw(BaseModel):
    """perf_audit 工具的原始输出(责任路由的唯一依据)。"""

    checks: list[CheckResult]
    all_pass: bool


class PerfReport(AuditRaw):
    advice: str  # LLM 对审计结果的解读与修复建议(纯文本)


class LinkSpec(BaseModel):
    label: str
    href: str


class ContentCard(BaseModel):
    id: str
    tag: str
    title: str
    desc: str
    status: Literal["LIVE", "PLANNED", "RESERVED"]
    span: Literal["", "wide", "full"] = ""  # 版面跨度:wide=跨2列 full=横贯全宽,空=普通卡(层次感用)
    link: Optional[LinkSpec] = None


class ContentPlan(BaseModel):
    cards: list[ContentCard] = []
    placeholders_removed: bool


class GateLog(BaseModel):
    gate: str
    verdict: Literal["pass", "fail"]
    violations: list[str] = []
    ts: str


# ---------------- 图状态 ----------------
class WorkflowState(TypedDict, total=False):
    brief: str
    run_id: str
    artifacts_dir: str
    config: dict  # RunConfig.as_dict()(报告用;节点经闭包持有 RunConfig 对象)
    style: Optional[StyleDecision]
    scaffold: Optional[ScaffoldPlan]
    animation: Optional[AnimationSpec]
    perf: Optional[PerfReport]
    content: Optional[ContentPlan]
    gate_logs: Annotated[list[GateLog], append_list]
    rework_counts: Annotated[dict, merge_dict]
    feedback: Annotated[dict, merge_dict]  # 值为 None = 删除该键
    usage: Annotated[dict, add_dict]
    status: Literal["running", "done", "aborted"]
    error: Optional[str]
    started_at: str
    ended_at: str
