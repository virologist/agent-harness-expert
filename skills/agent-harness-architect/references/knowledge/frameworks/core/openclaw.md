---
name: OpenClaw
alias: openclaw
type: harness
source: https://docs.openclaw.ai
papers: []
added: 2026-08-23
version: MIT（活跃维护）
confidence: verified
pinned: true
---

## 一句话定位

开源的网关/多渠道 agent harness，定位是"agent 操作系统"——多渠道路由、会话隔离、海量技能，核心优势是"连接问题"。

## H 六层映射

- **E**: 网关 + 引擎双模式；单轮 executor（harness 只跑一个已准备好的 turn）
- **T**: ClawHub 3200+ 技能 + MCP（模型上下文协议）+ 插件热插拔 hot-reload
- **C**: 自动压缩（接近上限或溢出错误触发，溢出则压缩后重试）+ 压缩前 memory flush（静默写盘防丢关键上下文）+ 切点保留 tool_call 与 tool_result 成对不拆 + bootstrap 文件截断（留头 70%+尾 20%）
- **S**: SQLite 全量历史 + 矢量检索 + 会话隔离（每渠道/用户独立）
- **L**: 权限分离（Reader 只读解析 / Actor 只执行，双代理最小权限）+ ClawKeeper 三层安全（Skill 策略层 / Plugin 引擎拦截层 / Watcher 外部守护层）
- **V**: 对抗性 benchmark（LLMail-Inject，权限分离从 100% 攻击成功率降到 0%）+ 审计回放

## 范式 P

扩展方式=插件化（skills/plugins）· 配置方式=声明式（可视化配置/hot-reload）· 部署=自托管/托管 · 编排=网关（多渠道路由）

## 模型组合

模型后端经网关/配置可替换（多渠道路由的"连接"定位使模型可配置）。多模型分档/子代理分档的公开文档未见（未公开）。

## 原创点（框架外，重点标注）

1. **权限分离（least-privilege 双代理）**：Reader 代理（只读、解析）与 Actor 代理（只执行）工具隔离，中间用严格 JSON schema 通信——把最小权限从 prompt 层提升到编排层，抗 prompt 注入（LLMail-Inject 从 100% 攻击成功率降到 0%）。

## 设计启发

- **设计 L 层/多智能体安全时**：对照"你的代理之间怎么隔离权限？中间传自由文本还是严格 schema？"（权限分离）
- **设计 T 层权限时**：对照"最小权限是 prompt 层提示，还是结构层强制？"（最小权限）
