"""LLM Runner 层:Budget 硬上限 / 指数退避重试 / 结构化输出自修复 / mock 与 OpenAI 兼容两档。

三档 provider(DESIGN.md §0/§5):
- mock         零 token,内置样例 + chaos 毒样本注入;
- cloud        WorkBuddy 云端免密钥 LLM(OpenAI 兼容,**仅支持 stream:true** → 强制流式);
- deepseek     用户自备 Key,function_calling 结构化输出,解析失败回退 JSON 修复路径。
"""
from __future__ import annotations

import json
import re
import time
from typing import Type

from pydantic import BaseModel, ValidationError

from workflow_chain.config import RunConfig


class FatalLLMError(RuntimeError):
    """不可重试错误(鉴权/参数/配额)或重试耗尽 → 图捕获 → abort。"""


class FatalBudgetError(RuntimeError):
    """预算硬上限触发 → abort,报告标注 budget_exceeded。"""


def est_tokens(text: str) -> int:
    """无 usage 元数据时的粗略估算(≈4 字符/token)。"""
    return max(1, len(text or "") // 4)


# ---------------- Budget ----------------
class Budget:
    """token 与调用次数预算计数器(硬上限,max_total_tokens=200_000 / max_llm_calls=50)。"""

    def __init__(self, max_total_tokens: int = 200_000, max_llm_calls: int = 50):
        self.max_total_tokens = max_total_tokens
        self.max_llm_calls = max_llm_calls
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "llm_calls": 0}

    def pre_call(self) -> None:
        if self.usage["llm_calls"] + 1 > self.max_llm_calls:
            raise FatalBudgetError(
                f"LLM 调用次数超限:{self.usage['llm_calls'] + 1} > max_llm_calls={self.max_llm_calls}"
            )

    def add(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.usage["prompt_tokens"] += prompt_tokens
        self.usage["completion_tokens"] += completion_tokens
        self.usage["llm_calls"] += 1
        total = self.usage["prompt_tokens"] + self.usage["completion_tokens"]
        if total > self.max_total_tokens:
            raise FatalBudgetError(
                f"token 预算超限:{total} > max_total_tokens={self.max_total_tokens}"
            )

    def snapshot(self) -> dict:
        return dict(self.usage)


# ---------------- Runner 基类(含自修复结构化输出) ----------------
_JSON_SUFFIX = (
    "\n\n【输出格式(严格遵守)】只输出一个 JSON 对象本身:不要 markdown 代码块、"
    "不要解释文字、不要任何多余文本。对象必须符合以下 JSON Schema:\n{schema_json}"
)


def _extract_json(raw: str) -> tuple[dict | None, str | None]:
    """宽容提取 JSON:剥代码围栏、截取首尾大括号。返回 (obj, None) 或 (None, err)。"""
    if not raw or not raw.strip():
        return None, "空输出"
    text = re.sub(r"^```(?:json)?\s*|\s*```\s*$", "", raw.strip(), flags=re.I | re.S).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None, f"输出中未找到 JSON 对象:{text[:200]!r}"
    try:
        return json.loads(text[start : end + 1]), None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析错误:{e}(片段:{text[start : start + 120]!r}...)"


class BaseRunner:
    """complete() 自由文本 + structured() 结构化输出(带最多 2 次自修复)。"""

    def __init__(self, budget: Budget):
        self.budget = budget
        self.last_repairs = 0

    # -- 子类接口 --
    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError

    def _ask_json(self, system: str, user: str, repair_note: str | None = None) -> str:
        raise NotImplementedError

    # -- 结构化输出主路径 --
    def structured(self, schema: Type[BaseModel], system: str, user: str) -> BaseModel:
        # function_calling 档(deepseek):优先走工具调用,失败回退 JSON 修复路径
        if getattr(self, "structured_mode", "") == "function_calling":
            try:
                return self._structured_fc(schema, system, user)
            except FatalLLMError:
                raise
            except Exception:
                pass  # 回退到通用 JSON 路径

        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        user_full = user + _JSON_SUFFIX.format(schema_json=schema_json)
        raw = self._ask_json(system, user_full)
        self.last_repairs = 0
        last_err = ""
        for _ in range(3):  # 首次 + 最多 2 次修复
            obj, err = _extract_json(raw)
            if obj is None:
                last_err = err
            else:
                try:
                    return schema.model_validate(obj)
                except ValidationError as e:
                    last_err = f"schema 校验失败:{e.errors()[0] if e.errors() else e}"
            if self.last_repairs >= 2:
                break
            self.last_repairs += 1
            # 自修复 prompt 只附「解析错误原文 + 原输出前 2000 字符」,防上下文爆炸(DESIGN.md §5)
            raw = self._ask_json(
                system, user_full,
                repair_note=f"{last_err}\n---上次输出(前 2000 字符)---\n{raw[:2000]}",
            )
        raise FatalLLMError(f"结构化输出解析失败(修复重试 {self.last_repairs} 次后放弃):{last_err}")

    def _structured_fc(self, schema, system, user) -> BaseModel:  # pragma: no cover
        raise NotImplementedError

    # ---- 工具增强的结构化输出(多 Agent:节点内工具循环) ----
    supports_tools = False  # Runner 是否具备 agent 式工具循环能力

    def structured_with_tools(self, schema: Type[BaseModel], system: str, user: str,
                              tools: dict, max_rounds: int = 3) -> BaseModel:
        """带工具取证的结构化输出;不支持工具的 Runner 退化为单轮 structured()。

        tools: {name: (args_pydantic_schema, zero_arg_callable)};callable 返回 JSON 可序列化 dict。
        """
        return self.structured(schema, system, user)

    # ---- 重试退避(可重试:网络/超时/限流/5xx;不可重试即短路) ----
    _FATAL_PATTERNS = (
        "401", "403", "unauthorized", "forbidden", "auth_", "invalid_request",
        "api key", "api_key", "quota", "billing", "insufficient", "permission",
    )

    def _is_fatal(self, e: Exception) -> bool:
        s = str(e).lower()
        return any(p in s for p in self._FATAL_PATTERNS)

    def _with_retry(self, fn):
        last: Exception | None = None
        for attempt in range(4):  # 首次 + 3 次重试(2s/4s/8s)
            try:
                return fn()
            except (FatalBudgetError, KeyboardInterrupt):
                raise
            except Exception as e:  # noqa: BLE001
                last = e
                if self._is_fatal(e):
                    raise FatalLLMError(f"不可重试错误:{e}") from e
                if attempt == 3:
                    raise FatalLLMError(f"重试 3 次后仍失败:{e}") from e
                time.sleep((2, 4, 8)[attempt])
        raise FatalLLMError(f"重试失败:{last}")


# ---------------- Mock Runner ----------------
_NODE_OF_SCHEMA = {"StyleScaffoldOut": "s1", "AnimationSpec": "s2", "ContentPlan": "s4",
                   "ReviewResult": "s5", "AuditAdvice": "s3"}


class MockRunner(BaseRunner):
    """零 token mock:按 schema 返回内置合规样例;chaos 让第 n 次调用返回毒样本。

    chaos 语义:{node: n} → 第 n 次调用注入毒样本;n=0 → 每次都注入(用于回炉超限测试)。
    """

    def __init__(self, budget: Budget, chaos: dict | None = None):
        super().__init__(budget)
        self.chaos = chaos or {}
        self._calls: dict[str, int] = {}

    def _node_of(self, schema: Type[BaseModel]) -> str:
        return _NODE_OF_SCHEMA.get(schema.__name__, schema.__name__)

    def structured(self, schema: Type[BaseModel], system: str, user: str) -> BaseModel:
        from workflow_chain import mock_data

        self.budget.pre_call()
        node = self._node_of(schema)
        n = self._calls[node] = self._calls.get(node, 0) + 1
        poison_at = self.chaos.get(node)
        poisoned = poison_at is not None and (poison_at == 0 or n == poison_at)
        if poisoned:
            sample = mock_data.poisoned_sample(node)
            tag = "chaos 毒样本"
        else:
            sample = self._good(node)
            tag = "合规样例"
        self.budget.add(est_tokens(system + user), est_tokens(f"[mock {node} #{n} {tag}]"))
        return sample if isinstance(sample, schema) else schema.model_validate(sample)

    @staticmethod
    def _good(node: str) -> BaseModel:
        from workflow_chain import mock_data

        return {
            "s1": mock_data.good_style_scaffold,
            "s2": mock_data.good_animation,
            "s4": mock_data.good_content,
            "s5": mock_data.good_review,
        }[node]()

    def complete(self, system: str, user: str) -> str:
        self.budget.pre_call()
        self.budget.add(est_tokens(system + user), est_tokens("[mock 审计结论]"))
        return "[mock] 审计结论:五项检查已逐条核验,失败项已按 owner 标注责任方,建议按明细修复。"

    # ---- 工具循环(mock 脚本化:一次取全部工具证据,组装确定性结论) ----
    supports_tools = True

    def structured_with_tools(self, schema: Type[BaseModel], system: str, user: str,
                              tools: dict, max_rounds: int = 3) -> BaseModel:
        from workflow_chain.state import AuditAdvice

        self.budget.pre_call()
        evidence = [{"tool": name, "result": fn()} for name, (_args, fn) in tools.items()]
        self.budget.add(est_tokens(system + user),
                        est_tokens(json.dumps(evidence, ensure_ascii=False)))
        if schema.__name__ == "AuditAdvice":
            eb = next((e["result"] for e in evidence if e["tool"] == "entrance_budget"), {})
            dw = next((e["result"] for e in evidence if e["tool"] == "deps_weight"), {})
            advice = (
                f"[mock·工具循环] 已自主取证 {len(evidence)} 项:"
                f"首屏入场预算 {eb.get('budget_ms')}ms/{eb.get('entrance_rules')} 条规则({eb.get('verdict')});"
                f"重依赖 {dw.get('heavy_deps') or '无'}({dw.get('verdict')})。"
                "五项检查按 owner 标注,建议按明细修复。"
            )
            return AuditAdvice(advice=advice, evidence=evidence)
        return self.structured(schema, system, user)


# ---------------- OpenAI 兼容 Runner(deepseek) ----------------


class OpenAICompatRunner(BaseRunner):
    """OpenAI 兼容端点。cloud 档端点仅支持 stream:true → force_stream=True 全程流式。"""

    structured_mode = ""  # "" → JSON 修复路径; "function_calling" → 工具调用优先

    def __init__(self, config: RunConfig, budget: Budget):
        super().__init__(budget)
        self.config = config
        self.force_stream = config.provider == "cloud"  # 云端端点仅支持流式(request_stream_required)
        if self.config.structured_output_mode == "function_calling":
            self.structured_mode = "function_calling"
        from langchain_openai import ChatOpenAI

        self._llm = ChatOpenAI(
            model=config.model,
            api_key=config.api_key,  # cloud=publishableKey(免密钥), deepseek=用户 Key
            base_url=config.base_url or None,
            temperature=config.temperature,
            timeout=config.timeout_s,
            max_retries=0,  # 重试由本层退避逻辑接管
        )

    # ---- 基础调用 ----
    def _stream_join(self, messages, model_kwargs: dict | None = None) -> str:
        llm = self._llm.bind(**model_kwargs) if model_kwargs else self._llm
        parts: list[str] = []
        usage_meta = None
        for chunk in llm.stream(messages):
            c = chunk.content
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                parts.extend(x.get("text", "") for x in c if isinstance(x, dict))
            um = getattr(chunk, "usage_metadata", None)
            if um:
                usage_meta = um
        text = "".join(parts)
        if usage_meta:
            self.budget.add(usage_meta.get("input_tokens", 0) or 0, usage_meta.get("output_tokens", 0) or 0)
        else:
            prompt = "".join(m[1] for m in messages) if isinstance(messages[0], tuple) else ""
            self.budget.add(est_tokens(prompt), est_tokens(text))
        return text

    def _invoke_join(self, messages, model_kwargs: dict | None = None) -> str:
        llm = self._llm.bind(**model_kwargs) if model_kwargs else self._llm
        msg = llm.invoke(messages)
        um = getattr(msg, "usage_metadata", None) or {}
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        self.budget.add(um.get("input_tokens", 0) or 0, um.get("output_tokens", 0) or 0)
        return content

    def _ask_raw(self, messages, model_kwargs: dict | None = None) -> str:
        if self.force_stream:
            return self._stream_join(messages, model_kwargs)
        return self._invoke_join(messages, model_kwargs)

    # ---- BaseRunner 接口 ----
    def complete(self, system: str, user: str) -> str:
        self.budget.pre_call()
        messages = [("system", system), ("human", user)]
        return self._with_retry(lambda: self._ask_raw(messages))

    def _ask_json(self, system: str, user: str, repair_note: str | None = None) -> str:
        if repair_note:
            user = user + "\n\n【上次输出无法通过校验,请只输出修复后的 JSON 对象】\n" + repair_note
        self.budget.pre_call()
        messages = [("system", system), ("human", user)]
        model_kwargs = (
            {"response_format": {"type": "json_object"}}
            if self.config.structured_output_mode == "json_mode"
            else None
        )
        return self._with_retry(lambda: self._ask_raw(messages, model_kwargs))

    def _structured_fc(self, schema, system, user) -> BaseModel:
        self.budget.pre_call()
        llm = self._llm.with_structured_output(schema, method="function_calling")
        messages = [("system", system), ("human", user)]
        obj = self._with_retry(lambda: llm.invoke(messages))
        # with_structured_output 丢失 usage → 按输入长度估算(预算硬上限仍生效)
        self.budget.add(est_tokens(system + user), est_tokens(str(obj)[:2000]))
        return obj

    # ---- 工具循环(真 agent 语义:LLM 自主决定调哪些取证工具,收集后给最终 JSON) ----
    supports_tools = True

    def structured_with_tools(self, schema: Type[BaseModel], system: str, user: str,
                              tools: dict, max_rounds: int = 3) -> BaseModel:
        from langchain_core.messages import ToolMessage

        self.budget.pre_call()
        llm = self._llm.bind_tools([args for args, _fn in tools.values()])
        messages: list = [("system", system), ("human", user)]
        evidence: list[dict] = []
        for _ in range(max_rounds):
            resp = self._with_retry(lambda: llm.invoke(messages))
            um = getattr(resp, "usage_metadata", None) or {}
            self.budget.add(um.get("input_tokens", 0) or 0, um.get("output_tokens", 0) or 0)
            tcs = getattr(resp, "tool_calls", None)
            if not tcs:
                content = resp.content if isinstance(resp.content, str) else str(resp.content)
                obj, err = _extract_json(content)
                if obj is None:
                    messages.append(resp)
                    messages.append(("human",
                                     f"输出不是合法 JSON({err}),请只输出符合 schema 的 JSON 对象,不要再调工具。"))
                    continue
                return schema.model_validate(obj)
            messages.append(resp)
            for tc in tcs:
                name = tc.get("name") or ""
                entry = tools.get(name)
                result = entry[1]() if entry else {"error": f"未知工具 {name}"}
                evidence.append({"tool": name, "result": result})
                messages.append(ToolMessage(content=json.dumps(result, ensure_ascii=False),
                                            tool_call_id=tc.get("id") or name))
        raise FatalLLMError(f"工具循环 {max_rounds} 轮耗尽仍未见最终 JSON 结论(已取证:{[e['tool'] for e in evidence]})")


# ---------------- Cloud Runner(WorkBuddy 云端免密钥 LLM) ----------------
class CloudRunner(BaseRunner):
    """WorkBuddy 云端 LLM —— 按官方 JS SDK(@tencent-ai/workbuddy-cloud-sdk)线协议镜像。

    SDK 源码摸底结论(任务 #7,dev 渠道 IIFE 逐段核对):
    - 路径:GET {endpoint}/.cloud/llm/models;POST {endpoint}/.cloud/llm/chat/completions;
    - 免密钥鉴权:自定义头 `x-wb-webapp-access-key: <publishableKey>`(匿名 token provider
      返回 undefined → 不带 Authorization 头;SDK 也不注入 Origin);
    - 端点仅支持流式:stream 必须为 true(否则 request_stream_required);usage 靠
      stream_options.include_usage 的末帧;[DONE] 为正常结束哨兵;
    - conversationId 走 X-Conversation-ID 头(本链一次性任务,不用会话)。
    """

    def __init__(self, config: RunConfig, budget: Budget):
        super().__init__(budget)
        self.config = config
        self.endpoint = (config.base_url or "").rstrip("/")
        self.model = config.model
        if not self.endpoint or not self.model:
            raise FatalLLMError("CloudRunner 需要 endpoint(.cloud-config.json)与 model")

    def _headers(self, accept: str) -> dict:
        return {
            "x-wb-webapp-access-key": self.config.api_key,
            "Accept": accept,
            "Content-Type": "application/json",
        }

    def list_models(self) -> list[dict]:
        """models 列表(兼容裸数组 / {data: [...]}),丢弃无 id 项(与 SDK normalizeModel 一致)。"""
        import httpx

        def call():
            r = httpx.get(f"{self.endpoint}/.cloud/llm/models",
                          headers=self._headers("application/json"), timeout=30)
            if r.status_code != 200:
                raise RuntimeError(f"models HTTP {r.status_code}: {r.text[:300]}")
            return r.json()

        data = self._with_retry(call)
        items = data if isinstance(data, list) else (data or {}).get("data") or []
        return [m for m in items if isinstance(m, dict) and m.get("id")]

    # ---- SSE 流式调用(镜像 SDK 的帧解析:content 累积 / usage 末帧 / [DONE] 哨兵) ----
    def _chat_stream(self, system: str, user: str, json_mode: bool) -> str:
        import httpx

        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": True,  # 端点仅支持流式(缺省即 request_stream_required)
            "stream_options": {"include_usage": True},
            "temperature": self.config.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        def call():
            content_parts: list[str] = []
            usage: dict = {}
            with httpx.stream(
                "POST", f"{self.endpoint}/.cloud/llm/chat/completions",
                headers=self._headers("text/event-stream"),
                json=body, timeout=self.config.timeout_s,
            ) as r:
                if r.status_code != 200:
                    err_body = r.read().decode("utf-8", "replace")[:500]
                    raise RuntimeError(f"chat HTTP {r.status_code}: {err_body}")
                done = False
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].strip()
                    if payload == "[DONE]":
                        done = True
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue  # 与 SDK 一致:坏帧跳过(gateway_invalid_response 交给整体判)
                    if isinstance(chunk.get("error"), dict):
                        e = chunk["error"]
                        raise RuntimeError(f"stream error {e.get('code')}: {e.get('message')}")
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    choices = chunk.get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        if delta.get("content"):
                            content_parts.append(delta["content"])
                if not done:
                    raise RuntimeError("gateway_stream_interrupted: 流式响应中断(未见 [DONE])")
            # usage 记账:优先真实值,缺失则估算
            if usage:
                self.budget.add(usage.get("prompt_tokens", 0) or 0,
                                usage.get("completion_tokens", 0) or 0)
            else:
                self.budget.add(est_tokens(system + user), est_tokens("".join(content_parts)))
            return "".join(content_parts)

        return self._with_retry(call)

    def complete(self, system: str, user: str) -> str:
        self.budget.pre_call()
        return self._chat_stream(system, user, json_mode=False)

    def _ask_json(self, system: str, user: str, repair_note: str | None = None) -> str:
        if repair_note:
            user = user + "\n\n【上次输出无法通过校验,请只输出修复后的 JSON 对象】\n" + repair_note
        self.budget.pre_call()
        return self._chat_stream(system, user, json_mode=self.config.structured_output_mode == "json_mode")


# ---------------- Runner 工厂 ----------------
def make_runner(config: RunConfig, budget: Budget, chaos: dict | None = None) -> BaseRunner:
    if config.provider == "mock":
        return MockRunner(budget, chaos=chaos)
    if config.provider == "cloud":
        return CloudRunner(config, budget)
    return OpenAICompatRunner(config, budget)
