---
name: Hermes Agent
alias: hermes
type: harness
source: https://github.com/NousResearch/hermes-agent
papers: []
added: 2026-08-23
version: v0.7.0
confidence: verified
pinned: true
---

## 一句话定位

Nous Research 开源的「自进化」agent harness，口号是 "The agent that grows with you"——技能由 AI 自己生成与迭代，记忆是文件而非向量库。

## H 六层映射

- **E**: 三层硬上限防死循环（记忆整理失败 3 次停、内置技能保护、`max_turns: 90`）+ tool_loop_guardrails（检测"重复失败/无进展"循环，警告或熔断）+ loop_caps（单轮 web≤50、subagent≤50）
- **T**: 内置 40+ 工具/技能 + MCP（模型上下文协议）多平台接入
- **C**: 双重压缩——网关层 85% 安全网（会话积压时先压）+ 主压缩 50% 触发；四阶段（清旧工具输出→定保护边界→9 字段结构化摘要→清孤立工具对）；"压缩只管工作窗口，不碰长期记忆"
- **S**: Markdown 文件记忆 + 分级存储（文件层=硬上限的长期记忆 / 情景层=全量存档按需注入 / 工作层=当前会话）+ 文件锁并发安全 + checkpoint 快照（50 版本）
- **L**: 审批路由、密钥泄露拦截、注入扫描、记忆漂移检测
- **V**: 三层容错——Checkpoint 快照+回滚、LLM 自愈（工具返回 error_type/exit_code/recovery_hint，模型自己推理修复）、verification-gated completion（"done"=每个验收标准都验证）

## 范式 P

扩展方式=插件化（Skill 系统）· 配置方式=向导式（setup 交互）+ 命令式 · 部署=自托管单机/服务器 · 编排=引擎（自主）+网关（多渠道路由）

## 模型组合

模型无关（经网关/MCP 接多平台模型）。多模型分档/子代理分档的具体策略公开文档未见（未公开）。

## 原创点（框架外，重点标注）

1. **自进化闭环**：完成 5 次以上工具调用的复杂任务后，自动生成 Markdown Skill 文档，下次复用；发现更优方案时自动更新技能——Harness 自己写自己，而非人工维护规则。
2. **文件即记忆**：用 Markdown 文件（非数据库/向量检索）作为记忆载体，容量无限、更轻量、跨会话贴合用户偏好。

## 设计启发

- **想自动化时**：对照"你的 harness 里，规则/技能/记忆哪些由人写、哪些该自进化？"（自进化）
- **设计 S 层时**：对照"记忆用文件还是向量库？文件可审计、向量可检索，你的场景要哪个？"（文件即记忆）
- **设计 V 层时**：对照"失败后能自动修复、让下次更稳吗？"（自修复）
