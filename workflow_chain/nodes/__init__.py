"""节点包:s1~s4 四个步骤节点 + finalize / abort 收口节点(DESIGN.md §1/§2)。"""
from workflow_chain.nodes.abort import make_abort, write_crash_abort
from workflow_chain.nodes.finalize import make_finalize
from workflow_chain.nodes.s1_style_framework import make_s1
from workflow_chain.nodes.s2_animation import make_s2
from workflow_chain.nodes.s3_performance import make_s3
from workflow_chain.nodes.s4_content import make_s4

__all__ = [
    "make_s1", "make_s2", "make_s3", "make_s4", "make_finalize", "make_abort", "write_crash_abort",
]
