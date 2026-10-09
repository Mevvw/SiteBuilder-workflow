"""T11/T12:cloud 集成测试(需要真实云端;默认跳过,设 RUN_CLOUD_TESTS=1 启用)。

前置:项目根目录存在 .cloud-config.json(WorkBuddy 云服务激活产物)。
"""
import json
import os
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    not os.environ.get("RUN_CLOUD_TESTS"), reason="需要真实云端(RUN_CLOUD_TESTS=1)"
)]

ROOT = Path(__file__).resolve().parents[1]


def _pub() -> dict:
    return (json.loads((ROOT / ".cloud-config.json").read_text("utf-8")) or {}).get("publicConfig", {})


def _model() -> str:
    return os.environ.get("WORKFLOW_MODEL", "")


def test_t11_models_list():
    pub = _pub()
    r = httpx.get(pub["endpoint"].rstrip("/") + "/models",
                  headers={"Authorization": f"Bearer {pub['publishableKey']}"}, timeout=30)
    assert r.status_code == 200
    models = r.json().get("data") or []
    assert models, "模型列表为空"
    chosen = [m for m in models if m.get("id") == _model()]
    assert chosen, f"指定模型 {_model!r} 不在列表中"
    assert chosen[0].get("disabled") is not True


def test_t12_cloud_full_run(tmp_path):
    from workflow_chain.config import RunConfig
    from workflow_chain.graph import run_chain

    pub = _pub()
    config = RunConfig(
        provider="cloud", model=_model(), structured_output_mode="json_mode",
        base_url=pub["endpoint"], api_key=pub["publishableKey"],
    )
    final = run_chain("咖啡品牌官网", config, artifacts_root=str(tmp_path))
    assert final["status"] == "done", final.get("error")
    report = json.loads((Path(final["artifacts_dir"]) / "run-report.json").read_text("utf-8"))
    assert report["usage"]["llm_calls"] >= 5
    assert report["usage"]["prompt_tokens"] > 0  # 真实 token 用量
