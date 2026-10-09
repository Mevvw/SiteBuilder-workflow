# 网页搭建工作流链(site-workflow-chain)· LangGraph 设计文档

> 把一套四步建站流程(①定风格搭框架 → ②出入场动画 → ③性能验证 → ④内容替换)
> 实现为一条**可执行、可门禁、可回炉**的 LangGraph 工作流链。
> 门禁规则不是拍脑袋 —— 它们全部来自真实前端项目实战中验证过的规则
> (禁 blur/弹跳、只动 transform/opacity/clip-path、性能五项清单等)。

- 技术栈:Python 3.11+ / LangGraph(骨架)+ LangChain(组件,`langchain-openai` 兼容端点)+ Pydantic v2 + rich(CLI)
- 模型接入:`mock` / `cloud`(WorkBuddy 云端免密钥 LLM,OpenAI 兼容 SSE)/ OpenAI 兼容族(`deepseek`、`glm`、`kimi`、`qwen`、`openai` 预设 + `LLM_BASE_URL` 自定义端点,用户自己的 Key)
- 交付形态:CLI(`python -m workflow_chain run "<需求简述>"`),产物落盘 `output/<run_id>/`

---

## 0. 拓扑总览

```
START
  └→ s1_style_framework ── gate_1 ──pass──→ s2_animation ── gate_2 ──pass──→ s3_performance ── gate_3 ──pass──→ s4_content ── gate_4 ──pass──→ finalize ──→ END(done)
        ↑        └─fail(≤2)─┘(回炉)         ↑        └─fail(≤2)─┘            ↑  │       └─fail(≤2)─┘           ↑        └─fail(≤2)─┘          ↑
        └──────────────(责任回炉:gate_3 判定失败项属于 ① 结构/依赖 → 回 s1;② 动画属性 → 回 s2)──────┘  │                              │
                                                                                                        └── 超限(>2)→ abort ──→ END(aborted)
```

- **门禁 = 门禁节点 + 路由条件边**两件套:门禁节点(确定性校验,负责写 gate_logs/回炉计数/反馈 —— LangGraph 中只有节点能写状态),紧跟的条件边只做路由。
- **回炉 = 路由边返回上游节点名**,反馈写进 `state.feedback[step]`,重跑时注入 prompt,消费后以 `None` 值清除(见 §3)。
- 每步回炉上限 `max_reworks`(默认 2),超限走 `abort`。

---

## 1. 节点列表

| # | 节点名 | 类型 | 职责 | 是否调 LLM |
|---|--------|------|------|-----------|
| 1 | `s1_style_framework` | LLM 节点 | ① 定风格 + 搭框架:读需求简述(与回炉反馈),产出风格决策与框架方案,写出骨架文件 | ✅ 结构化输出 |
| 2 | `s2_animation` | LLM 节点 | ② 出入场动画:基于风格与框架产出动画编排(首屏编排/滚动编排/悬停),写 spec 文件 | ✅ 结构化输出 |
| 3 | `s3_performance` | 工具 + LLM 节点 | ③ 性能验证:**先调 `perf_audit` 工具做确定性检查**,LLM 只负责解读结果、给修复建议 | ✅(解读)+ 🔧 |
| 4 | `s4_content` | LLM 节点 | ④ 内容替换:产出真实内容方案(卡片清单/文案/资产映射),写 content-plan.md | ✅ 结构化输出 |
| 5 | `finalize` | 工具节点 | 汇总所有产物 + 门禁日志 + token 用量/耗时,写 `run-report.json`,`status=done` | ❌ |
| 6 | `abort` | 工具节点 | 回炉超限或致命错误的收口:写 `abort-report.json`,`status=aborted` | ❌ |

门禁是「**门禁节点 + 路由条件边**」两件套(LangGraph 中只有节点能写状态,条件边只读):
`g1_style` ~ `g4_content` 四个**门禁节点**(确定性校验,写 gate_logs/回炉计数/反馈,不调 LLM),
每个门禁节点后挂一条**路由条件边**(纯路由,决定 pass / 回炉 / abort)。

| 门禁节点 | 校验对象 | 通过条件(全部满足) | 失败路由(由路由边决定) |
|------|--------|----------------------|----------|
| `g1_style` | `style` + `scaffold` | 色板 4 值均为合法 hex;`easing` 为 cubic-bezier;`modules` ⊇ {Hero, Works, Contact};`font_stack` 不含 http/外链字体;`files` ≥ 3 且路径无 `..` | 回 `s1`(计数+1,反馈=违规列表);超限 → `abort` |
| `g2_animation` | `animation` | 所有 `properties` ⊆ {transform, opacity, clip-path};**黑名单只扫描 properties 字符串**(如 `blur(`、`bounce`、`elastic`、`spring(`、`shake`),`technique` 已由 Literal 枚举在类型层封死,**自然语言字段(reduced_motion_fallback 等)一律不扫**,防误杀;`reduced_motion_fallback` 非空;入场含 stagger、滚动含 clip-reveal | 回 `s2`;超限 → `abort` |
| `g3_performance` | `perf`(即 s3 里 `perf_audit` 的 AuditRaw) | `all_pass=True`。**gate_3 自身零规则**(规则全部活在 perf_audit 里,避免两处维护):只读 `all_pass` 与失败项 owner。**责任路由:失败项数量多者优先(owner 计数);平局回 rework_counts 较小者** —— 兼顾责任归属与公平性,防止某步被反复回炉而另一步从未触发 | 失败项 owner=animation → 回 `s2`;owner=scaffold → 回 `s1`;超限 → `abort` |
| `g4_content` | `content` | `placeholders_removed=True`;每张卡 `desc` 非空且 ≥ 8 字;**卡片数量 ∈ [min_cards, max_cards]**(默认 3~6,CLI `--min-cards/--max-cards` 可调,从 state.config 读取);`link.href` 仅允许 `https?://` 或不含 `..` 的相对路径;`status` ∈ {LIVE, PLANNED, RESERVED} 且 LIVE 卡有 link | 回 `s4`;超限 → `abort` |

---

## 2. 节点输入 / 输出

| 节点 | 读取(state) | 写入(state) | 落盘产物 | LLM 调用形态 |
|------|--------------|--------------|----------|--------------|
| `s1_style_framework` | `brief`、`feedback["s1"]`(可空) | `style: StyleDecision`、`scaffold: ScaffoldPlan`、`feedback.pop("s1")` | `01-style-and-scaffold.md` + `scaffold/index.html`(线框骨架:演示文案+占位卡片,确定性渲染) | system=资深建站架构师规则;user=brief+反馈;`with_structured_output(StyleScaffoldOut)` |
| `s2_animation` | `style`、`scaffold`、`feedback["s2"]`(可空) | `animation: AnimationSpec`、`feedback.pop("s2")` | `02-animation-spec.md` + **重写 `scaffold/index.html`(把编排注入骨架页:入场 stagger/滚动揭示/悬停/reduced-motion 降级)** | system=动效编排师规则(三手法白名单);user=style/scaffold 摘要+反馈;结构化输出 |
| `s3_performance` | `style`、`scaffold`、`animation` | `perf: PerfReport` | `03-perf-report.md`、`03-perf-raw.json`(工具原始输出) | 先 `perf_audit(animation, scaffold)` 得 JSON → LLM 仅做解读与修复建议(文本输出) |
| `s4_content` | `brief`、`style`、`scaffold`、`animation`、`perf` | `content: ContentPlan` | `04-content-plan.md` | system=内容策划规则(禁虚构);user=全部上游摘要;结构化输出 |
| `finalize` | 全部产物字段、`gate_logs`、`usage` | `status="done"` | `run-report.json` | ❌ |
| `abort` | `error` / `gate_logs`、`rework_counts` | `status="aborted"` | `abort-report.json` | ❌ |

**Pydantic 产物模型(摘要)**:

```python
class StyleDecision(BaseModel):
    site_type: str                  # 网站类型
    tone: str                       # 风格关键词
    palette: Palette                # bg/acc/accent2/txt(全部 hex 校验)
    font_stack: str                 # 仅系统字体栈(禁网络字体)
    easing: str                     # 全站统一缓动(须为 cubic-bezier)
    modules: list[str]              # 模块清单(必须含 Hero/Works/Contact)

class ScaffoldPlan(BaseModel):
    stack: Literal["static-html", "react-vite"]
    files: list[FileSpec]           # 路径 + 用途(≥3 项)
    deps: list[str]                 # 依赖清单(体积敏感项须标注)

class AnimationSpec(BaseModel):
    entrance: list[AnimRule]        # 首屏编排(含 delay 序列)
    scroll: list[AnimRule]          # 滚动编排(stagger/clip 揭示/视差)
    hover: list[AnimRule]
    reduced_motion_fallback: str    # 必须≠空:降级说明

class AnimRule(BaseModel):
    target: str                     # 选择器/元素
    technique: Literal["mask-reveal", "translate", "settle", "clip-reveal", "parallax", "stagger", "color"]
    properties: list[str]           # 仅允许 transform/opacity/clip-path
    duration_ms: int = Field(ge=80, le=2000)
    delay_ms: int = Field(ge=0, le=1500)

class PerfReport(BaseModel):
    checks: list[CheckResult]       # 五项检查(见 §5 工具)
    all_pass: bool
    advice: str                     # LLM 解读与修复建议

class ContentPlan(BaseModel):
    cards: list[ContentCard]        # 每张卡:id/tag/title/desc/status/link?
    placeholders_removed: bool
```

---

## 3. 状态字段(`WorkflowState`,TypedDict)

| 字段 | 类型 | 写入者 | Reducer | 说明 |
|------|------|--------|---------|------|
| `brief` | `str` | CLI | 覆盖 | 用户需求简述 |
| `run_id` / `artifacts_dir` | `str` | CLI | 覆盖 | 本次运行标识与产物目录 |
| `provider` / `model` / `max_reworks` | `RunConfig` | CLI | 覆盖 | 运行配置(不可变);另含 `structured_output_mode`(function_calling / json_mode / prompt_only,按 provider 显式配置默认值)、`max_total_tokens=200_000`、`max_llm_calls=50` 预算硬上限、`min_cards=3` / `max_cards=6`(内容卡数量门禁,gate_4 从 state.config 读取) |
| `style` | `StyleDecision \| None` | s1 | 覆盖 | ① 风格决策 |
| `scaffold` | `ScaffoldPlan \| None` | s1 | 覆盖 | ① 框架方案 |
| `animation` | `AnimationSpec \| None` | s2 | 覆盖 | ② 动画编排 |
| `perf` | `PerfReport \| None` | s3 | 覆盖 | ③ 性能报告 |
| `content` | `ContentPlan \| None` | s4 | 覆盖 | ④ 内容方案 |
| `gate_logs` | `list[GateLog]` | 各门禁 | **`operator.add`(追加)** | 每次判定:{gate, verdict, violations[], ts} |
| `rework_counts` | `dict[step, int]` | 各门禁 | **dict 合并** | 每步回炉计数 |
| `feedback` | `dict[step, str]` | 各门禁 | **dict 合并,值为 `None` 表示删除该键** | 回炉反馈;消费节点重跑成功后返回 `{step: None}` 显式清除,杜绝旧反馈残留污染下一轮 prompt |
| `usage` | `dict` | 各 LLM 节点 | dict 合并 | prompt/completion token 累计 |
| `status` | `Literal["running","done","aborted"]` | finalize/abort | 覆盖 | 终态 |
| `error` | `str \| None` | abort | 覆盖 | 致命错误信息 |

---

## 4. 条件边(门禁)、循环、终止条件

### 4.1 门禁

四道门禁的完整校验规则与路由见 **§1 门禁节点表格**(单一事实来源,此处不重复)。

### 4.2 循环

- 唯一的循环机制 = 门禁失败回炉(条件边返回上游节点名形成环)。
- 每步回炉上限 `max_reworks=2`(CLI 可调);`rework_counts[step] > max_reworks` 即断环走 `abort`。
- 回炉时:门禁把违规清单写入 `feedback[step]`,该步节点重跑时拼进 prompt(「上次输出存在以下问题,必须逐条修复」),成功后 pop 掉。

### 4.3 终止条件(五种)

| 条件 | 出路 | 终态 |
|------|------|------|
| `g4` 路由通过 | finalize → END | `done` |
| 任一门禁失败且该责任步回炉超限 | abort → END | `aborted`(报告含失败历史) |
| LLM 节点重试耗尽 / 不可重试错误(见 §6) | abort → END | `aborted`(`error` 字段) |
| **预算超限**:`max_total_tokens` / `max_llm_calls` 触顶 | abort → END | `aborted`(报告标注 `budget_exceeded`) |
| CLI Ctrl+C / 图外异常 | 键盘中断直接退出 | 进程退出码区分 |

CLI 退出码:`0=done`,`1=aborted`,`2=fatal error`。

> **Checkpointer 说明**:本版本**不做跨进程断点续跑**(一次 invoke 跑完,失败即 abort 落报告),
> 不接 SqliteSaver;`run_id` 仅用于产物归档目录。checkpointer + thread_id 的崩溃恢复留作后续扩展,
> 请勿误以为当前版本能断点续跑。

---

## 5. 工具调用

| 工具 | 签名 | 性质 | 说明 |
|------|------|------|------|
| `perf_audit` | `(animation: AnimationSpec, scaffold: ScaffoldPlan) -> AuditRaw` | **确定性 Python**,**规则唯一事实来源** | 五项检查(通用前端性能清单):① 动画属性白名单/黑名单扫描(owner=animation)② WebGL/重特效项必须有视口暂停说明(owner=animation)③ 滚动/指针监听须含 rAF 节流说明、禁止布局抖动属性(owner=animation)④ 依赖体积预算:`deps` 含 three/gsap 等重依赖时须有分包/懒加载说明(owner=scaffold)⑤ `reduced_motion_fallback` 覆盖(owner=animation)。每项产出 `{check, passed, owner, detail}`。**gate_3 只消费其结果(all_pass + owner),自身零规则**;T4 单测直接测 perf_audit 的规则,gate 层单测只测路由 |
| `write_artifact` | `(artifacts_dir, filename, content) -> {path, bytes}` | 确定性 | **路径穿越防护**:resolve 后必须仍在 artifacts_dir 内,否则拒绝;utf-8 落盘 |
| 结构化输出 | `runner.structured(...)` | LangChain 能力 | **按 provider 显式配置 `structured_output_mode`**:cloud → `json_mode`(端点文档明确支持 response_format),OpenAI 兼容档(deepseek/glm/kimi/qwen/openai/自定义)→ `function_calling`,mock → 直接返回对象。解析失败自修复重试时,**修复 prompt 只附解析错误 + 原输出前 2000 字符**,不整段塞回,防上下文爆炸 |

> 演示版刻意保持工具面窄(IO 只进不出、审计不联网),把复杂度留给"链 + 门禁 + 回炉"本身;
> 后续可平滑挂文件系统/网页抓取工具。

---

## 6. 重试 / 超时 / 错误处理(三层)

### L1 LLM 调用层(节点内,不进图环)
- 每次调用超时 120s;可重试错误(网络/5xx/限流)指数退避重试 3 次(2s/4s/8s)。
- **结构化输出解析失败 = 可重试**:修复 prompt 只附「解析错误原文 + 原输出前 2000 字符」(自修复),最多 2 次。
- **预算硬上限**:`max_total_tokens`(默认 200_000)与 `max_llm_calls`(默认 50)由 Budget 计数器强制;触顶抛 `FatalBudgetError` → abort,报告标注 `budget_exceeded`。开源项目必备,防止第一次跑就把额度烧光。
- **不可重试即短路**:鉴权失败(`auth_*`)、参数错误(`request_*`)、余额/配额硬拒绝 —— 直接抛 `FatalLLMError` → 图捕获 → `abort`。

### L2 门禁层
- 门禁节点永不抛异常:任何输入不合法都折算为「fail + 违规明细」;回炉计数超限由路由边导向 `abort`。

### L3 图执行层
- `graph.invoke()` 外层 try/except:未预期异常写 `abort-report.json`。
- **脱敏**:报告落盘前必须过 `redact_secrets()` —— 对 `sk-…`、`Bearer …`、`api_key=…`、`api_key: …` 等模式打码,防止 traceback 里的 Key 随开源报告泄露。
- 配置错误(provider 名非法、OpenAI 兼容档缺 Key、cloud 档缺 .cloud-config.json)**启动前**校验,不进图。
- LLM 中断/流截断:保留已生成文本摘要进报告,标记 `interrupted`。

---

## 7. 测试用例(pytest;mock/chaos 档零 token)

### 单元测试
| # | 用例 | 断言 |
|---|------|------|
| T1 | gate_1 合法/非法样本 | 缺缓动曲线、色板非 hex、模块缺失 → 各自 fail 且违规信息准确;合法样本 pass |
| T2 | gate_2 白名单/黑名单 | properties 含 `filter:blur` → fail;含 "bounce" 关键词 → fail;纯 transform/opacity/clip-path → pass |
| T3 | gate_3 责任路由 | 失败项 owners=[animation,animation,scaffold] → 回 `s2`(多数);平局 → 回 rework_counts 较小者;仅 scaffold → 回 `s1`。**只测路由,规则在 T4** |
| T4 | perf_audit 五项(规则唯一来源) | 构造含 `filter: blur(6px)` 的 spec → 恰好对应项 fail 且 owner=animation;合规 spec → 全 pass;重依赖无分包说明 → ④ fail owner=scaffold |
| T5 | 回炉上限 | 连续 3 次 gate_2 fail → 第 3 次路由到 abort |
| T6 | write_artifact 安全 | `../evil.txt`、绝对路径 → 抛 PermissionError;正常相对路径 → 落盘 |
| T7 | mock provider | 固定输出通过全部 schema 解析 |
| T8 | 解析失败自修复 | 第一次坏 JSON、第二次好 JSON → 成功,重试计数 = 1 |

### 集成测试
| # | 用例 | 断言 |
|---|------|------|
| T9 | mock 全链 happy path | 终态 done;`01~04` 产物文件存在;`run-report.json` 含 4 条 pass 门禁日志 |
| T10 | chaos 注入回炉(核心演示) | `--chaos s2:1` 让 s2 第一次输出混入 blur → gate_2 打回 → 第二次输出合规 → 终态 done 且 gate_logs 恰含一次 rework 记录(验证自愈) |
| T11 | cloud 模型列表 | models 接口 200 且非空,选中模型 disabled≠true |
| T12 | cloud 真跑 | brief=「咖啡品牌官网」全链 done,run-report.json 有真实 token 用量 |

---

## 8. 目录结构(预览)

```
langchain-workflow/
├── DESIGN.md                  # 本文档
├── README.md                  # 运行说明(交付时写)
├── pyproject.toml             # 依赖:langgraph / langchain / langchain-openai / pydantic / rich / pytest
├── .env.example               # DEEPSEEK_API_KEY= 等配置位(cloud/mock 档不需要)
├── workflow_chain/
│   ├── __main__.py            # CLI 入口(rich 进度输出)
│   ├── config.py              # RunConfig + provider 工厂(mock/cloud/deepseek)
│   ├── state.py               # WorkflowState + Pydantic 产物模型 + reducer
│   ├── nodes/                 # s1~s4 + finalize/abort(每节点一个文件)
│   ├── gates.py               # gate_1~4 条件边(与 perf_audit 同源规则)
│   ├── tools.py               # perf_audit / write_artifact
│   └── graph.py               # StateGraph 组装(拓扑唯一事实来源)
└── tests/                     # T1~T10(mock 档可离线跑);T11/T12 标记为 integration
```

> 运行示例:
> `python -m workflow_chain run "咖啡品牌官网" --provider cloud`
> `python -m workflow_chain run "博客站点" --provider mock --chaos s2:1 --max-reworks 2`

---

## 9. 评审修订记录(v1.0 → v1.1)

外部评审 8 条意见全部采纳,另自查修正 1 处架构问题:

| # | 评审意见 | 裁定 | 落点 |
|---|---------|------|------|
| 1 | gate_3 混合路由(既回 s1 又回 s2)存在内部矛盾 | 采纳:统一为「失败项数量多者优先;平局回 rework_counts 较小者」的单一裁决规则,节点与路由边共用同一纯函数 `g3_owner_step` 保证一致 | §1 门禁表 |
| 2 | feedback 用 pop 与 dict 合并 reducer 语义冲突 | 采纳:reducer 约定**值为 None = 删除该键**,消费节点重跑成功后返回 `{step: None}` 显式清除 | §3 |
| 3 | `with_structured_output` 在非 OpenAI 端点不可靠 | 采纳:按 provider 显式配置 `structured_output_mode`(cloud→json_mode,deepseek→function_calling,失败回退 JSON 修复路径);修复 prompt 只附解析错误 + 原输出前 2000 字符 | §5 |
| 4 | 缺 Token/成本预算硬上限 | 采纳:`Budget` 计数器,`max_total_tokens=200_000` / `max_llm_calls=50`,触顶抛 `FatalBudgetError` → abort(报告标注 budget_exceeded) | §6 L1 |
| 5 | 没提 LangGraph Checkpointer | 采纳:明确本版不做断点续跑,checkpointer + thread_id 留作扩展,防止误解 | §4.3 |
| 6 | gate_2 黑名单词匹配误杀自然语言字段 | 采纳:黑名单只扫描 properties 字符串;technique 由 Literal 枚举在类型层封死;reduced_motion_fallback 等自然语言字段一律不扫 | §1 门禁表 |
| 7 | perf_audit 与门禁"同源"要小心两处维护 | 采纳:perf_audit 为规则唯一事实来源,gate_3 自身零规则只消费 all_pass + owner;T4 直接测 perf_audit,gate 层单测只测路由;gate_2 与检查①共用 `scan_anim_properties` | §5 |
| 8 | Abort 报告可能泄露 traceback 中的 Key | 采纳:所有报告落盘前必须过 `redact_secrets()`(sk-… / Bearer … / api_key=… / publishable_key=…) | §6 L3 |
| + | 自查:LangGraph 条件边只读不能写状态,原设计"条件边做校验并写反馈"不可行 | 架构修正:「门禁节点(写状态)+ 路由条件边(纯路由)」两件套 | §0/§1 |

**实现落位(与 §8 目录对应)**:`state.py`(模型+reducer)/ `tools.py`(perf_audit、write_artifact、redact_secrets)/ `gates.py`(门禁节点+路由)/ `llm.py`(Budget、自修复、Mock/OpenAI 兼容 Runner)/ `nodes/`(六节点)/ `graph.py`(组装+run_chain)/ `__main__.py`(CLI:run / models 子命令)。
测试:55 项全绿(T1~T10、T13~T15 离线;T11/T12 cloud 集成默认跳过,RUN_CLOUD_TESTS=1 启用)。

---

## 10. 增补记录(v1.1 → v1.2,2026-10-09)

主人提供 2026-10-03 种子提示词,按「只提取通用网站设计规则」口径落位 5 条(2 条纯文案并入节点 SYSTEM,3 条为代码/门禁):

| # | 种子规则 | 落点 |
|---|---------|------|
| 1 | 风格偏好(高级简洁现代/克制科技感)+ 三禁忌(不过度赛博朋克/不做SaaS官网感/不做传统作品集模板感)+ 克制视觉手法(细网格/微光晕/噪点/细线条) | s1 SYSTEM「风格取向」段 |
| 2 | 作品卡数量 3~6 张 | RunConfig.min_cards/max_cards(默认 3/6,CLI `--min-cards/--max-cards`,make_config 启动前校验);gate_4 从 state.config 读取校验;T13 |
| 3 | 展示层次感、不要普通图片网格 | ContentCard.span ∈ {"", wide, full}(wide=跨2列,full=横贯全宽);s4 SYSTEM 规则 2;04-content-plan.md 展示跨度 |
| 4 | 联系模块隐私红线(只留姓名+联系方式,禁照片/年龄/所在地/工作年限) | s4 SYSTEM 规则 6 |
| 5 | 桌面端优先、兼顾移动端 | s1 SYSTEM「风格取向」段 |

另并入 s2 SYSTEM(纯文案偏好,不做门禁):首屏 delay 参考序列(50/120/280/460/580ms 递进,主视觉压轴)、悬停全站同幅同曲线。
