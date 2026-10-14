---
name: DeepSeek Harness
alias: dsh
type: harness
source: https://github.com/deepseek-ai/deepseek-harness
papers: ["A Programming Paradigm for Spatiotemporal Composability"]
added: 2026-08-23
version: v0.1 (developer preview)
confidence: verified
pinned: true
---

## 一句话定位

可组合的开源 agent harness，核心哲学是「一切皆插件、无特权内核」，连执行循环本身也是插件。

## H 六层映射

- **E**: 日志驱动循环，数据决定续步（"数据"=工具是否还欠一次请求 + next-step 队列是否非空）；引擎本身不设步数上限、靠数据自然终止，失控轮次由配置 `max_rounds` 兜底；turn 结束有 5 种原因（completed 完成 / blocked 拦截 / max-tokens 截断 / aborted 取消 / error 异常）；失败从"干净边界"重开轮次（从持久历史重建全新轮次，不续跑半截输出），重试是插件（2 次、500ms–10s、抖动）
- **T**: ctx.tools / MCP（模型上下文协议，标准工具接入）/ defineTool 按需注册；工具分"可并行/独占"，有界并行池（≤10），读写按依赖调度
- **C**: 三层 token 管控——PTC（Programmatic Tool Calling，中间变量本地执行不喂 LLM）、工具输出 >8192 字符裁剪、上下文 80% 水位触发压缩（留最近 16% + LLM 摘要）；切点保留 tool_call 与 tool_result 成对不拆
- **S**: append-only 事件溯源日志（zstd JSONL），可回放/fork/恢复；"model-visible means logged"（模型看到的必被记录）
- **L**: 沙箱分层（只读→工作区可写→危险全访问）+ 审批 ask + agent/before-dispatch 拦截
- **V**: 三维评估（outcome 结果 / compliance 红线合规 / process 过程），session log 是唯一权威源，产出确定性 score+explanation

## 范式 P

扩展方式=插件化（无特权内核，激进）· 配置方式=声明式（cordis.yml / patch）· 部署=单机可扩展 · 编排=中心化+子代理

## 模型组合

模型为声明式配置项（cordis.yml 装配），harness 本身不硬绑单一模型。多模型分档/子代理分档的公开文档未见（未公开）。

## 原创点（框架外，重点标注）

1. **无特权内核**：连「执行循环」都降级为插件，插件化原则推演到底，没有需要打补丁的特权部分。
2. **Cordis 时空可组合性**：effect/coeffect 从编译期类型论提升为运行时机制（88 页 PL 论文）——白话即"组件的副作用可声明、可逆、卸载即回滚"，空间上无侵入挂载+热插拔，时间上卸载即回滚副作用。
3. **「model-visible means logged」事件溯源不变量**：append-only 日志是单一真相源，运行时断言"凡是进模型的东西必被记录"。

## 设计启发

- **选插件化时**：对照"你的插件化边界停在哪里？为什么执行循环不是插件、还留着特权部分？"（无特权内核）
- **设计 S 层时**：对照"日志是'顺便记录'还是'单一真相源'？模型看到的每样东西，都能从日志重建吗？"（事件溯源）
- **设计 L 层时**：对照"组件卸载后，它注册的服务、事件、副作用会自己清理吗？"（可逆副作用）
