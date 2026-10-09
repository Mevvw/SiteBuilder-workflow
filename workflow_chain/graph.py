"""StateGraph 组装(拓扑唯一事实来源,DESIGN.md §0)+ run_chain 执行入口。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from langgraph.graph import END, StateGraph

from workflow_chain.config import RunConfig
from workflow_chain.gates import (
    g1_style, g2_animation, g3_performance, g4_content,
    route_g1, route_g2, route_g3, route_g4,
)
from workflow_chain.llm import Budget, FatalBudgetError, FatalLLMError, make_runner
from workflow_chain.nodes import (
    make_abort, make_s1, make_s2, make_s3, make_s4, make_finalize, write_crash_abort,
)
from workflow_chain.state import WorkflowState


def build_graph(runner, config: RunConfig, budget: Budget):
    g = StateGraph(WorkflowState)

    # 步骤节点(LLM)
    g.add_node("s1_style_framework", make_s1(runner, config))
    g.add_node("s2_animation", make_s2(runner, config))
    g.add_node("s3_performance", make_s3(runner, config))
    g.add_node("s4_content", make_s4(runner, config))
    # 门禁节点(确定性,永不调 LLM)
    g.add_node("g1_style", g1_style)
    g.add_node("g2_animation", g2_animation)
    g.add_node("g3_performance", g3_performance)
    g.add_node("g4_content", g4_content)
    # 收口节点
    g.add_node("finalize", make_finalize(budget))
    g.add_node("abort", make_abort(budget))

    def _m(*names: str) -> dict:
        return {n: n for n in names}

    g.set_entry_point("s1_style_framework")
    g.add_edge("s1_style_framework", "g1_style")
    g.add_conditional_edges(
        "g1_style", lambda s: route_g1(s, config.max_reworks),
        _m("s1_style_framework", "s2_animation", "abort"),
    )
    g.add_edge("s2_animation", "g2_animation")
    g.add_conditional_edges(
        "g2_animation", lambda s: route_g2(s, config.max_reworks),
        _m("s2_animation", "s3_performance", "abort"),
    )
    g.add_edge("s3_performance", "g3_performance")
    g.add_conditional_edges(
        "g3_performance", lambda s: route_g3(s, config.max_reworks),
        _m("s1_style_framework", "s2_animation", "s4_content", "abort"),
    )
    g.add_edge("s4_content", "g4_content")
    g.add_conditional_edges(
        "g4_content", lambda s: route_g4(s, config.max_reworks),
        _m("s4_content", "finalize", "abort"),
    )
    g.add_edge("finalize", END)
    g.add_edge("abort", END)
    return g.compile()


def run_chain(brief: str, config: RunConfig, chaos: dict | None = None,
              artifacts_root: str = "output") -> dict:
    """跑一次全链。返回最终状态;退出码判定交给 CLI(status: done→0 / aborted→1 / fatal→2)。"""
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    artifacts_dir = str(Path(artifacts_root) / run_id)
    Path(artifacts_dir).mkdir(parents=True, exist_ok=True)

    budget = Budget(config.max_total_tokens, config.max_llm_calls)
    runner = make_runner(config, budget, chaos=chaos)
    graph = build_graph(runner, config, budget)
    init = {
        "brief": brief,
        "run_id": run_id,
        "artifacts_dir": artifacts_dir,
        "config": config.as_dict(),
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        return graph.invoke(init, {"recursion_limit": 80})
    except KeyboardInterrupt:
        raise  # CLI 层统一处理(Ctrl+C 直接退出)
    except (FatalBudgetError, FatalLLMError) as e:
        write_crash_abort(artifacts_dir, run_id, brief,
                          f"{type(e).__name__}: {e}", budget, config)
        return {"status": "aborted", "error": f"{type(e).__name__}: {e}",
                "run_id": run_id, "artifacts_dir": artifacts_dir}
    except Exception as e:  # L3:未预期异常 → 落脱敏报告
        write_crash_abort(artifacts_dir, run_id, brief,
                          f"UnexpectedError: {type(e).__name__}: {e}", budget, config)
        return {"status": "aborted", "error": f"UnexpectedError: {type(e).__name__}: {e}",
                "run_id": run_id, "artifacts_dir": artifacts_dir}
