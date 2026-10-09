"""RunConfig 与 provider 工厂(mock / cloud / deepseek)。启动前配置校验(L3,DESIGN.md §6)。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

CLOUD_CONFIG_FILE = ".cloud-config.json"

# OpenAI 兼容厂商预设:别名 → (base_url, .env 中的 Key 名, 默认模型)。
# 这些厂商都暴露 OpenAI 兼容的 chat/completions 端点,共用 OpenAICompatRunner。
OPENAI_COMPAT_PRESETS: dict[str, tuple[str, str, str]] = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY", "deepseek-chat"),
    "glm": ("https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY", ""),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "ZHIPU_API_KEY", ""),
    "kimi": ("https://api.moonshot.cn/v1", "MOONSHOT_API_KEY", ""),
    "moonshot": ("https://api.moonshot.cn/v1", "MOONSHOT_API_KEY", ""),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", ""),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY", ""),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", ""),
}


class ConfigError(RuntimeError):
    """配置错误:进图前短路,不消耗任何 token。"""


@dataclass
class RunConfig:
    provider: str = "mock"  # mock | cloud | deepseek
    model: str = ""
    structured_output_mode: str = "mock"  # mock | json_mode | function_calling
    max_reworks: int = 2
    min_cards: int = 3  # 内容卡数量门禁下限(种子提示词规则:作品卡 3~6 张)
    max_cards: int = 6  # 内容卡数量门禁上限
    max_total_tokens: int = 200_000  # 预算硬上限
    max_llm_calls: int = 50
    temperature: float = 0.3
    timeout_s: int = 120
    base_url: str = ""
    api_key: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _read_dotenv(path: str = ".env") -> dict:
    """极简 .env 解析(避免引入 python-dotenv 依赖)。"""
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip("'\"")
    return out


def make_config(
    provider: str,
    model: str = "",
    max_reworks: int = 2,
    structured_output_mode: str | None = None,
    artifacts_dir: str | None = None,
    min_cards: int = 3,
    max_cards: int = 6,
    _env: dict[str, str] | None = None,
) -> RunConfig:
    """provider 工厂:mock 零依赖;cloud 读 .cloud-config.json;OpenAI 兼容预设/自定义端点读 .env。

    任何配置错误在此抛 ConfigError —— 启动前校验,不进图(DESIGN.md §6 L3)。
    _env 仅供测试注入,默认从 .env + 环境变量合并读取(环境变量优先)。
    """
    provider = (provider or "mock").lower()
    if min_cards < 1 or max_cards < min_cards:
        raise ConfigError(
            f"内容卡数量门禁非法:min_cards={min_cards}, max_cards={max_cards}(需 1 ≤ min ≤ max)"
        )
    common = dict(max_reworks=max_reworks, min_cards=min_cards, max_cards=max_cards)

    if provider == "mock":
        return RunConfig(
            provider="mock", model="mock-1", structured_output_mode="mock", **common
        )

    env = dict(_env) if _env is not None else {
        **_read_dotenv(),
        **{k: v for k, v in os.environ.items() if v},
    }

    if provider in OPENAI_COMPAT_PRESETS:
        base_url, env_key, default_model = OPENAI_COMPAT_PRESETS[provider]
        key = env.get(env_key) or env.get("LLM_API_KEY", "")
        if not key:
            raise ConfigError(
                f"{provider} 档需要 {env_key}(或通用 LLM_API_KEY),写入 .env 或环境变量,.env.example 有示例"
            )
        use_model = model or env.get("WORKFLOW_MODEL", "") or default_model
        if not use_model:
            raise ConfigError(f"{provider} 档需要 --model 指定模型名(如 glm-5.3 / moonshot-v1-8k)")
        return RunConfig(
            provider=provider,
            model=use_model,
            structured_output_mode=structured_output_mode or "function_calling",
            base_url=env.get("LLM_BASE_URL") or base_url,
            api_key=key,
            **common,
        )

    # 任意自定义 OpenAI 兼容端点(LLM_BASE_URL + LLM_API_KEY + --model),provider 名随意
    if provider != "cloud" and env.get("LLM_BASE_URL") and env.get("LLM_API_KEY"):
        use_model = model or env.get("WORKFLOW_MODEL", "")
        if not use_model:
            raise ConfigError("自定义端点需要 --model 指定模型名")
        return RunConfig(
            provider=provider,
            model=use_model,
            structured_output_mode=structured_output_mode or "function_calling",
            base_url=env["LLM_BASE_URL"],
            api_key=env["LLM_API_KEY"],
            **common,
        )

    if provider == "cloud":
        cfg_path = Path(artifacts_dir or ".") .parent / CLOUD_CONFIG_FILE if False else Path(CLOUD_CONFIG_FILE)
        if not cfg_path.exists():
            raise ConfigError(
                f"cloud 档需要 {CLOUD_CONFIG_FILE}(先激活 WorkBuddy 云服务生成 publicConfig)"
            )
        pub = (json.loads(cfg_path.read_text("utf-8")) or {}).get("publicConfig", {})
        endpoint, key = pub.get("endpoint", ""), pub.get("publishableKey", "")
        if not endpoint or not key:
            raise ConfigError(f"{CLOUD_CONFIG_FILE} 缺 publicConfig.endpoint / publishableKey")
        if not model:
            raise ConfigError("cloud 档需要 --model(可用 `python -m workflow_chain models` 查看可用模型)")
        return RunConfig(
            provider="cloud",
            model=model,
            structured_output_mode=structured_output_mode or "json_mode",
            base_url=endpoint,
            api_key=key,
            **common,
        )

    raise ConfigError(
        f"未知 provider: {provider!r}"
        "(可选 mock / cloud / deepseek / glm / kimi / qwen / openai;或设 LLM_BASE_URL + LLM_API_KEY 接任意 OpenAI 兼容端点)"
    )
