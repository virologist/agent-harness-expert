# 知识库索引（knowledge/index.md）

> 轻量索引：先读本文件定位，再按需读详文。本文件只存定位信息 + 一句话，常驻、很小。
> 读取策略、入库标准与进化库位置见 [../knowledge-policy.md](../knowledge-policy.md)。

## 使用方式（渐进三档读取）

1. 扫下表，定位"当前要设计的层"有哪些案例/模式相关。
2. 读选中文件的条目头确认相关性（patterns 已按主题合并，一文件含 2–4 条）。
3. 只读 1–2 个文件的完整详文。

> **硬规则（MUST）**：参考件读取顺序固定：index → h-framework → production-checklist → assets/\*，且集中在会话前段完成，禁止在中段零散插入（防打穿前缀缓存）。

---

## 框架案例（frameworks/core/）

| 框架 | 一句话定位 | 扩展 | 编排 | 上下文隔离 | 执行环境/权限 | E | T | C | S | L | V |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DeepSeek Harness | 一切皆插件、无特权内核 | 插件化(激进) | 中心化+子代理 | 子代理隔离 | 沙箱分层 + 审批 | 循环即插件 | MCP/defineTool | 组装注入 | 事件溯源日志 | 生命周期/审批 | 轨迹回放 |
| Hermes Agent | 自进化、文件即记忆 | 插件化 | 中心化+子代理 | 子代理隔离(带上限) | 审批/密钥拦截 | 自进化循环 | 40+工具/MCP | 文件即记忆 | Markdown 记忆 | 审批/密钥拦截 | 自修复验证 |
| Claude Code | 产品级 coding agent | 插件化 | 中心化 lead + 子代理 | 子代理独立上下文 | 权限 allow/ask/deny + sandbox | loop+subagents | 内置工具/MCP | CLAUDE.md/压缩 | auto memory/JSONL | hooks/权限 | checkpoint/回滚 |
| Codex Harness | 原生 agent 运行时 | 插件化 | 中心化 thread | thread 边界 | HITL/中断审批 | thread/turn | 内置+动态加载 | 上下文压缩 | thread 持久化 | HITL/中断 | 事件流/benchmark |
| OpenClaw | 网关/多渠道 agent OS | 插件化 | 网关分发 | 会话隔离 | Reader/Actor 权限分离 | 网关+engine | 3200+skills | 矢量记忆 | SQLite+矢量 | 权限分离 | 审计/回放 |

> 详细见 `frameworks/core/` 下各条目文件。
> **"执行环境/权限"列为 v1.2.0 新增**：设计 T/L 层时必答（凭证是否进执行环境、写操作影响半径）。

---

## 模型条目（models/core/）

> v1.3.0 新增：模型组合设计的数据层。机制零产品名，具体模型只在这里以数据身份出现。
> 延迟/成本为量级基线（注明核实日期），落地以用户实测为准。

| 模型 | 类别 | 一句话定位 | 接入形态 | 档位 |
|---|---|---|---|---|
| Jev | 决策型 | TypeSafe 的 System One 模型，类型化窄决策（early access） | 托管 API（POST /v1/decisions） | 决策型模型（System One） |
| CLM-8B | 决策型 | 对比学习开源 System One 模型，可自托管、同 schema | 自托管（clm-serve + vLLM 编码器） | 决策型模型（System One） |

> 详细见 `models/core/` 下各条目文件（含已验证适用域/不适用域/降级策略）。
> 用户点名的未收录模型：按 knowledge-policy.md 5.3「未收录模型处理通则」处理，不凭记忆推荐。

---

## 跨领域模式（patterns/）

> v1.4.0 新增：`efficiency-and-caching.md`（效率与缓存类 6 条）。
> 每组含「核心思想 / 可迁移层 / 案例 / **何时不用** / 对照问题」，按主题合并为一个文件。

| 模式 | 文件 | 来源领域 | 可迁移到 | 一句话 |
|---|---|---|---|---|
| event-sourcing | state-and-history.md | 数据库/软件工程 | S / V | 只追加不修改，事件流是单一真相源 |
| immutable-state | state-and-history.md | 函数式编程 | S / C | 状态不可变，变更即新版本 |
| cqrs | state-and-history.md | 软件工程 | S / V | 读写分离，命令与查询走不同路径 |
| reversible-computation | state-and-history.md | 编程语言 | L / P | 副作用可回滚，卸载即清理 |
| dependency-injection | structure-and-boundary.md | 软件工程 | P / T | 内核极薄，能力靠注入，可逆注册 |
| declarative-configuration | structure-and-boundary.md | DevOps/基础设施 | P / T | 用配置描述行为，而非写死代码 |
| graph-state-machine | structure-and-boundary.md | 工作流/编排 | E / S | 用图定义状态与流转，显式声明 |
| capability-security | structure-and-boundary.md | 安全 | L / T | 最小权限，按能力授予而非按身份 |
| pure-function-effects | composition-and-concurrency.md | 编程语言 | S / P | 副作用显式化、可逆、可组合 |
| actor-model | composition-and-concurrency.md | 并发/分布式 | P / E | 隔离实体间消息传递，天然并发 |
| model-cascade-task-routing | composition-and-concurrency.md | 成本工程/服务分层 | E / P / V | 按能力需求分派模型档位，级联升级 |
| system1-system2-dual-model | composition-and-concurrency.md | 认知科学/决策理论 | E / L / V | 快模型接窄决策，慢模型按需介入 |
| confidence-gated-control-flow | composition-and-concurrency.md | 控制系统/可靠性工程 | E / L / V | 置信度驱动放行/升级/拒绝 |
| prefix-stable-context | efficiency-and-caching.md | 推理工程 / CDN 缓存 | C / E / T | 前缀只追加，重排一次即从该字节起重算 |
| cache-aware-invalidation | efficiency-and-caching.md | 存储系统 / 编译缓存 | C / E / V | 重写上下文前先算失效预算 |
| deterministic-serialization | efficiency-and-caching.md | 构建可复现性 / 编译器 | C / T / S | 语义相同必须字节相同，否则全不命中 |
| result-memoization | efficiency-and-caching.md | 缓存系统 / 数据库 | T / C / S | 昂贵且确定的结果只算一次 |
| wall-clock-bounded-parallelism | efficiency-and-caching.md | OS 调度 / 并发控制 | E / T / P | 墙钟预算 + 并行度封顶 |
| streaming-interruptibility | efficiency-and-caching.md | 人机交互 / Web 性能 | E / L / V | 首字节与可取消决定体感 |

> 共 19 条，按主题合并为 4 个文件；每条含「核心思想 / 可迁移层 / 案例 / **何时不用** / 对照问题」。
> 设计 C / E / T 层时**必查** `efficiency-and-caching.md`——这三条线最容易被整份漏掉。

---

## 容量状态

- 常驻层（pinned）：5 / 5（用户指定，默认不替换）
- 流动层（rotating）：2 / 5（v1.3.0 首批模型条目：Jev、CLM-8B）
- core 总量：7 / 10
- `archive/`、`inbox/`：按需创建（当前无内容，不保留空目录）

> 外部进化库的位置、读写顺序与同步机制**唯一定义在 [../knowledge-policy.md](../knowledge-policy.md) §一**，此处不再重复。
