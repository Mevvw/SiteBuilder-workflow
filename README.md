# 网页搭建工作流链(site-workflow-chain)

把一套四步建站流程(**① 定风格搭框架 → ② 出入场动画 → ③ 性能验证 → ④ 内容替换**)
实现为一条**可执行、可门禁、可回炉**的 LangGraph 工作流链。

- 门禁规则全部来自真实前端项目实战验证过的规则(禁 blur/弹跳、只动 transform/opacity/clip-path、性能五项清单等)
- 设计文档:[DESIGN.md](DESIGN.md)(拓扑 / 节点 IO / 状态字段 / 门禁循环终止 / 工具 / 容错 / 测试用例 / 评审修订记录)

## 快速开始

```bash
# Python 3.11+,安装依赖
pip install langgraph langchain langchain-openai pydantic rich pytest httpx

# 跑测试(T1~T10 离线零 token;T11/T12 需要云端)
python -m pytest -q

# mock 全链(零 token,演示门禁 + 回炉)
python -m workflow_chain run "咖啡品牌官网" --provider mock

# chaos 注入:s2 第 1 次调用输出混入 blur → gate_2 打回 → 自愈
python -m workflow_chain run "咖啡品牌官网" --provider mock --chaos s2:1
```

## 模型接入

| provider | 鉴权 | 结构化输出 | 说明 |
|---|---|---|---|
| `mock` | 无 | 内置样例 | 零 token;支持 `--chaos s2:1` / `s2:0` 注入毒样本 |
| `cloud` | 免密钥(`.cloud-config.json` 的 publicConfig) | json_mode | WorkBuddy 云端 LLM,按官方 JS SDK 线协议直连(`x-wb-webapp-access-key` 头 + 强制流式 SSE) |
| `deepseek` | `DEEPSEEK_API_KEY`(.env) | function_calling | DeepSeek 官方 API(默认模型 deepseek-chat),解析失败自动回退 JSON 修复路径 |
| `glm` / `kimi` / `qwen` / `openai` | 对应厂商 `*_API_KEY`(.env) | function_calling | OpenAI 兼容预设:智谱 / Moonshot / 通义 / OpenAI,`--model` 指定模型 |
| 任意自定义名 | `LLM_BASE_URL` + `LLM_API_KEY`(.env) | function_calling | 接任何 OpenAI 兼容端点(SiliconFlow / 火山方舟 / 自建网关等) |

```bash
# cloud 档:先看可用模型,再跑
python -m workflow_chain models
python -m workflow_chain run "咖啡品牌官网" --provider cloud --model deepseek-v4-flash
```

cloud 档需要项目根目录的 `.cloud-config.json`(WorkBuddy 云服务激活产物),形如:

```json
{ "publicConfig": { "endpoint": "https://…", "publishableKey": "wbpk_…" } }
```

OpenAI 兼容档:复制 `.env.example` 为 `.env` 填入对应厂商 Key,例如 `ZHIPU_API_KEY` 后 `--provider glm --model glm-5.3`。

## 工作流拓扑

```
START → s1_style_framework → g1_style ─pass→ s2_animation → g2_animation ─pass→ s3_performance → g3_performance ─pass→ s4_content → g4_content ─pass→ finalize → END(done)
           ↑  └fail(≤2)→ 回炉      ↑  └fail(≤2)→ 回炉      ↑   └fail→ 责任路由(s1/s2)   ↑  └fail(≤2)→ 回炉        ↑ └fail(≤2)→ 回炉
           └──────────────────── 超限(>2)────────────────────────────→ abort → END(aborted)
```

- **门禁 = 门禁节点 + 路由条件边**两件套(LangGraph 条件边只读,只有节点能写状态)
- 每步回炉上限 `--max-reworks`(默认 2),超限走 abort;反馈写入 `state.feedback`,重跑注入 prompt,成功后显式清除
- 内容门禁:作品卡数量默认 3~6(`--min-cards/--max-cards` 可调);`span` 字段标注层次跨度(wide=跨2列 / full=横贯全宽);联系模块遵守隐私红线(只保留姓名+联系方式,禁照片/年龄/所在地/工作年限)
- 预算硬上限:`max_total_tokens=200_000` / `max_llm_calls=50`,触顶 abort(报告标注 budget_exceeded)
- 所有报告落盘前过 `redact_secrets()` 脱敏

## 产物

每次运行落盘 `output/<run_id>/`:

```
01-style-and-scaffold.md   风格决策 + 框架方案
scaffold/index.html        线框骨架页(演示文案+占位卡片;s2 后注入入场/滚动/悬停动画)
02-animation-spec.md       动画编排(入场/滚动/悬停 + 降级说明)
03-perf-raw.json           perf_audit 五项检查原始输出
03-perf-report.md          性能报告(LLM 解读)
04-content-plan.md         内容方案(作品卡清单)
run-report.json            汇总:门禁日志 / 回炉计数 / token 用量 / 配置(脱敏)
```

## 测试

`python -m pytest -q` —— 55 项:

- T1/T2 门禁校验(色板 hex、缓动、模块、字体栈;属性白/黑名单、stagger/clip-reveal、降级说明)
- T3 gate_3 责任路由(失败项多者优先,平局回 rework_counts 较小者)
- T4 perf_audit 五项规则(规则唯一事实来源)
- T5 回炉上限(连续 3 次 fail → abort)
- T6 write_artifact 路径穿越防护
- T7 mock provider + chaos 语义
- T8 结构化输出自修复(坏 JSON → 修复 → 成功;重试耗尽 → FatalLLMError)
- T9 mock 全链 happy path / T10 chaos 回炉自愈
- T13 内容门禁:卡片数量上下限(3~6,可配置)与 span 层次字段
- T14 provider 工厂:厂商预设(glm/kimi/qwen/openai)与自定义端点解析
- T15 s2 动画注入:编排通过后骨架页携带真实动画(chaos 回炉后注入的是合规版)
- T11/T12 cloud 集成(`RUN_CLOUD_TESTS=1` 启用,需 `.cloud-config.json`)

## 目录

```
workflow_chain/
├── __main__.py     CLI(run / models 子命令,退出码 0=done 1=aborted 2=fatal)
├── config.py       RunConfig + provider 工厂(启动前配置校验)
├── state.py        WorkflowState + Pydantic 产物模型 + reducer
├── llm.py          Budget / 重试退避 / 自修复结构化输出 / Mock·OpenAI兼容·Cloud 三 Runner
├── tools.py        perf_audit(五项)/ write_artifact(防穿越)/ redact_secrets
├── gates.py        g1~g4 门禁节点 + 路由(含 g3 责任裁决)
├── nodes/          s1~s4 + finalize / abort(每节点一文件)
├── graph.py        StateGraph 组装 + run_chain
└── mock_data.py    合规样例 + chaos 毒样本
```
