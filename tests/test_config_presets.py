"""T14:provider 工厂多 API 预设(glm/kimi/qwen/openai)与自定义端点通道。"""
import pytest

from workflow_chain.config import ConfigError, make_config


def test_glm_preset():
    cfg = make_config("glm", model="glm-5.3", _env={"ZHIPU_API_KEY": "zk-test"})
    assert cfg.provider == "glm"
    assert cfg.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert cfg.api_key == "zk-test"
    assert cfg.structured_output_mode == "function_calling"


def test_kimi_qwen_openai_presets():
    assert make_config("kimi", model="moonshot-v1-8k", _env={"MOONSHOT_API_KEY": "mk"}).base_url == "https://api.moonshot.cn/v1"
    assert make_config("qwen", model="qwen-plus", _env={"DASHSCOPE_API_KEY": "ds"}).base_url.startswith("https://dashscope")
    assert make_config("openai", model="gpt-4o", _env={"OPENAI_API_KEY": "sk"}).base_url == "https://api.openai.com/v1"


def test_deepseek_preset_default_model():
    cfg = make_config("deepseek", _env={"DEEPSEEK_API_KEY": "sk-ds"})
    assert cfg.model == "deepseek-chat"
    assert cfg.api_key == "sk-ds"


def test_preset_missing_key_raises():
    with pytest.raises(ConfigError, match="ZHIPU_API_KEY"):
        make_config("glm", model="glm-5.3", _env={})


def test_preset_missing_model_raises():
    with pytest.raises(ConfigError, match="--model"):
        make_config("glm", _env={"ZHIPU_API_KEY": "zk-test"})


def test_custom_endpoint():
    cfg = make_config("siliconflow", model="Qwen/Qwen3-32B",
                      _env={"LLM_BASE_URL": "https://llm.example.com/v1", "LLM_API_KEY": "llm-key"})
    assert cfg.base_url == "https://llm.example.com/v1"
    assert cfg.api_key == "llm-key"


def test_custom_endpoint_needs_model():
    with pytest.raises(ConfigError, match="--model"):
        make_config("siliconflow", _env={"LLM_BASE_URL": "https://llm.example.com/v1", "LLM_API_KEY": "k"})
