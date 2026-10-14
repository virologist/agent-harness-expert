---
name: Codex Harness
alias: codex
type: harness
source: https://github.com/openai/codex
papers: []
added: 2026-08-23
version: Apache 2.0（2026-08-20 开源）
confidence: verified
pinned: true
---

## 一句话定位

OpenAI 开源的 Codex 背后核心 agent 运行时，由 CLI + app-server（有状态执行守护进程）+ SDK 三件套组成，面向可嵌入、headless 的执行。

## H 六层映射

- **E**: agent loop + Item/Turn/Thread 三原语（包含关系 Thread 线程 ⊃ Turn 轮次 ⊃ Item 条目；turn 可中断）
- **T**: 内置工具 + 动态工具加载（按需搜索 schema，避免 prompt 膨胀）
- **C**: 上下文压缩保留中间推理状态、避免冗余验证（相比无压缩基线 token 减 83.3%）
- **S**: thread 持久化到磁盘（事件日志），可重连重建时间线、恢复/fork/归档
- **L**: HITL approval（Human-in-the-loop 人工审批，高危操作暂停待授权）+ interruptibility（可中断、可改运行时状态）
- **V**: 事件流（item/started、delta、completed）驱动可观测 + benchmark

## 范式 P

扩展方式=插件化（app-server 协议可接任意客户端）· 配置方式=命令式（codex exec）+协议化（JSON-RPC lite）· 部署=单机/分布式 · 编排=中心化

## 模型组合

支持模型选择配置（codex exec 可指定模型）。多模型分档/子代理分档的公开文档未见（未公开）。

## 原创点（框架外，重点标注）

1. **app-server 协议化运行时**：双向 JSON-RPC（JSONL over stdio），server 可主动发起 approval 请求并暂停 turn 等客户端回复——把 harness 做成稳定、可嵌入的协议表面。
2. **Item/Turn/Thread 三原语生命周期**：用显式生命周期事件（started/delta/completed）支撑可流式、可恢复的 UI，而非黑盒 request/response。

## 设计启发

- **想被外部嵌入时**：对照"你的 harness 是被命令行驱动，还是被协议驱动？谁拥有 turn 的生命周期？"（协议化运行时）
- **设计 S 层时**：对照"会话能不能恢复/fork？事件流是不是唯一真相？"（三原语）
- **设计 T 层时**：对照"工具是全部塞进 prompt，还是按需动态加载？"（动态工具加载）
