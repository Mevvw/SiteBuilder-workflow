"""rich 控制台与节点进度输出。"""
from __future__ import annotations

import os

from rich.console import Console

console = Console()

_QUIET = os.environ.get("WORKFLOW_QUIET", "") == "1"


def step_log(node: str, msg: str) -> None:
    """节点进度一行(测试时设 WORKFLOW_QUIET=1 可静音)。"""
    if _QUIET:
        return
    console.print(f"[cyan]{node:<12}[/cyan]{msg}")
