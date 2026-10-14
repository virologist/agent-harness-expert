---
name: Claude Code
alias: claude-code
type: harness
source: https://www.anthropic.com/engineering/claude-code-best-practices
papers: []
added: 2026-08-23
version: 商用产品（闭源，架构有官方文档公开）
confidence: verified
pinned: true
---

## 一句话定位

Anthropic 的产品级 coding agent harness，核心是一个围绕 agent loop 的分层运行时。

## H 六层映射

- **E**: 中心 agent loop + subagents（隔离上下文、嵌套深度最多 5 层）+ TodoWrite 规划 + per-session web/subagent 硬上限（防失控）
- **T**: 内置工具（Read/Edit/Bash/Search）+ MCP（模型上下文协议）+ 权限门控（调用前 allow/ask/deny）
- **C**: 分层上下文——持久指令在文件（CLAUDE.md/rules）、技能按需加载、历史满自动 compaction 摘要；"持久规则在文件、噪音在 subagent、长会话显式 /compact"
- **S**: auto memory（跨会话记忆）+ JSONL transcripts（可审计）
- **L**: hooks 确定性拦截（PreToolUse/PostToolUse/SessionStart/Stop）+ 权限模式（allow/ask/deny/plan/sandbox）
- **V**: checkpoints 文件快照可回滚 + transcript 审计

## 范式 P

扩展方式=插件化（MCP/skills/hooks/subagents）· 配置方式=命令式+声明式（settings.json）· 部署=单机/CLI/多端 · 编排=中心化 lead agent + subagent 团队

## 模型组合

支持 Claude 系列模型档位切换（官方文档提供模型选择能力）；subagent 可指定独立模型，实现"同一循环内按子任务分档"。多档位预算分配/级联升级的量化策略未见官方公开（未公开）。

## 原创点（框架外，重点标注）

1. **subagent 上下文隔离**：子代理跑在独立上下文窗口，只回传最终结果+元数据，实现"数百个后台 agent 编排而不污染主上下文"。
2. **hooks 作为确定性拦截层**：命令/HTTP 类型的 hook 由 harness 确定性执行，低上下文成本，可 deny 工具调用——这是 L 层"安检门"的产品化范本。

## 设计启发

- **设计 L 层时**：对照"哪些动作该确定性拦截（hook），哪些该让模型判断（prompt/agent hook）？"（确定性拦截）
- **设计多智能体时**：对照"子任务该不该污染主上下文？隔离边界划在哪？"（subagent 隔离）
- **设计权限时**：对照"权限要不要分级（allow/ask/deny）？"（最小权限）
