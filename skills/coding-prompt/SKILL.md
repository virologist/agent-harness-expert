---
name: coding-prompt
version: "2.0.0"
display_name: 编程提示词优化
display_name_en: Coding Prompt
description_zh: "AI 编程提示词优化器与教练。在活跃编码会话中，用户向 AI 编写编程提示词或指令时使用——覆盖启动新功能、纠正 AI 方向、审查代码、请求测试、调试问题、准备交付全流程。触发场景：显式要求优化/改进/润色提示词（优化提示词、improve my prompt、提示词审查）、用户激活本技能（激活编程提示词）、或编码任务中指令模糊、缺少约束、缺少验收标准、可受益于提示词工程最佳实践时。用户说「更新技能」/「update skill」时触发技能知识库进化。非编程提示词或普通聊天不触发。"
description_en: "AI coding prompt optimizer and coach. Use whenever the user is writing programming prompts or instructions to an AI during active coding sessions — including starting new features, correcting AI's direction, reviewing code, requesting tests, debugging issues, or preparing delivery. Trigger when: explicit request to optimize/improve/refine a prompt (improve my prompt, prompt review), the user activates this skill (激活编程提示词), or during coding tasks where instructions to AI are vague, missing constraints, missing acceptance criteria, or could benefit from prompt engineering best practices. Also trigger when the user says '更新技能' or 'update skill' to evolve this skill's knowledge base. Do NOT trigger for non-coding prompts or general chat."
description: AI coding prompt optimizer and coach. This skill should be used whenever the user is writing programming prompts or instructions to an AI during active coding sessions— including when starting new features, correcting AI's direction, reviewing code, requesting tests, debugging issues, or preparing delivery. Trigger when, explicit request to optimize/improve/refine a prompt, the user activates this skill (激活编程提示词), or during coding tasks where instructions to AI are vague, missing constraints, missing acceptance criteria, or could benefit from prompt engineering best practices. Also trigger when the user says "更新技能" or "update skill" to evolve this skill's knowledge base. Do NOT trigger for non-coding prompts or general chat.
---

# Coding Prompt — AI 编程提示词最佳实践

> 激活：激活编程提示词 | 优化提示词 | improve my prompt

## Purpose

提升发给 AI 的编程提示词质量：诊断弱点、应用已验证的原则，并在活跃编码会话中主动检测常见的 AI 失败模式——覆盖设计、编码、测试、调试、交付全流程。

## 目录

| # | 内容 | 位置 |
|---|------|------|
| 1 | 诊断清单（D1-D16） | `references/checklist.md` |
| 2 | 核心原则 | `references/principles.md` |
| 3 | 沟通模式 | `references/patterns.md` |
| 4 | 工作流模板（启动→调试→交付） | `references/templates.md` |
| 5 | 反模式速查 | `references/anti-patterns.md` |
| 6 | 结构智慧 | `references/structure.md` |
| 7 | 进化协议 | `references/evolution.md` |
| 8 | 测试基础（对抗用例/执行证据/问题分级） | `references/testing-basics.md` |
| 9 | SDK 确定性校验清单（CodeBuddy Agent SDK 项目必检） | `references/sdk-checklist.md` |
| — | 经验沉淀（格式样板；团队语境写入项目内 `.harness-kb/`） | `references/learnings.md` |

> 经验层的**可写位置与环境判定**见 `references/evolution.md`「写入位置」——本表只列文件，不定义协议。

## 工作方式

本技能有两种模式。详细规则存于 `references/`——**按需加载，不提前加载**。

### Mode 1：显式优化（触发即完整诊断）

显式请求提示词优化时——触发词、粘贴提示词求审查、或以「优化提示词」开头——执行**完整诊断**并返回改写后的提示词。

**触发词**：
- `优化提示词: <你的提示词>` — 按全部原则重写
- `激活编程提示词` / `activate coding-prompt` — 进入主动模式
- `improve my prompt` / `check my prompt` / `prompt review` / `提示词审查`

**第一步：判断提示词类型，按级加载**（团队语境先读 `<项目>/.harness-kb/learnings.md`，独立使用读 `references/learnings.md`；文件不存在则跳过，视为无历史沉淀）：

| 提示词类型 | 识别特征 | 加载文件 |
|-----------|---------|---------|
| 新功能/设计 | 启动新特性、方案设计 | 全部（checklist + principles + patterns + templates + anti-patterns + structure） |
| 纠偏/继续 | 修正方向、推进长任务 | checklist + principles + anti-patterns + structure |
| 测试/验收/审查 | 测试、验收、代码审查 | checklist + templates + anti-patterns |
| 调试/交付/走查 | 排查问题、UX 走查、发布检查 | checklist + templates |

无法判断类型时按「新功能/设计」全量加载。诊断中发现需要其他文件时按需补载。

**第二步：逐项过 checklist 诊断，应用原则改写**。

**输出格式**：

```
## 诊断结果
- D2 缺少约束: <缺什么>
- D4 缺少场景: <缺什么>

## 优化后的提示词
<改写后的提示词>
```

原始提示词 ≤ 30 行时在开头回显原文；超过则省略回显。诊断无信号触发时，直接说「提示词已足够好」并给可选的微调建议，不强行重写。

### Mode 2：主动监控（只报高优信号）

Mode 1 触发后，技能在本次会话保持激活。此模式下**只**在检测到以下信号时主动警报：

| 警报 | 信号 | 响应 |
|-------|------|------|
| 🚨 **假完成** | D12 | AI 声称「完成」但代码含 stub/TODO/占位返回/示例数据。追加：`[coding-prompt] ⚠️ 检测到假完成：代码包含 <具体问题>，请替换为真实实现。` |
| 🚨 **规则匹配偏见** | D11 | 选择硬编码规则/正则/打分，而 LLM 原生更优。追加：`[coding-prompt] ⚠️ 检测到规则匹配偏见：建议使用 LLM 原生能力替代硬编码 <具体规则>。` |
| 🚨 **缺回归测试** | D13 | 完成/更新代码但未验证未修改功能。追加：`[coding-prompt] ⚠️ 检测到缺少回归测试：<改动内容> 完成后未验证未修改功能是否仍正常，请补充回归测试。` |
| 🚨 **范围蔓延** | D14 | 改了无关代码、重构未要求部分、加未请求功能。追加：`[coding-prompt] ⚠️ 检测到范围蔓延：改动涉及未要求的 <具体内容>。请回退无关改动，只保留任务相关变更。` |
| 🚨 **伪称已运行** | D15 | 声称「测试通过/已验证」但无真实执行证据。追加：`[coding-prompt] ⚠️ 检测到伪称已运行：「通过」缺乏真实执行证据，请实际执行并贴出命令与输出。` |
| 🚨 **弱化测试** | D16 | 为过测试删断言/放宽预期/跳过用例。追加：`[coding-prompt] ⚠️ 检测到弱化测试：为通过而 <删除断言/放宽预期>。请恢复断言强度，从实现层面修复。` |

**其余信号（D1-D10）**：不主动打断。仅显式要求提示词审查时才提。

**Mode 2 不加载 reference 文件**——上表规则足够支撑主动监控。唯一动作：进入 Mode 2 时读一次经验层（团队语境 `<项目>/.harness-kb/learnings.md`，独立使用 `references/learnings.md`；不存在则跳过），将其「反模式」分节纳入监控范围（个人踩过的坑实时生效）。

**会话持续性**：Mode 2 依赖对话上下文。疑似上下文退化（~10 轮未明确提及主动监控）时，先重新确认激活状态再发警报。

**团队语境激活路径（agent-harness-expert 专家团）**：上面两条规则面向「用户与单个 AI 交互式对话」场景。当本技能被**多 agent 团队**中的编码工程师使用时（主理人 spawn 独立 agent 下发任务），触发词不会出现在任务指令里，Mode 2 按默认逻辑永不激活。此时按以下等效规则执行：

- **任务开始即视为已触发**：编码工程师加载本技能时等效于执行一次「激活编程提示词」，直接进入 Mode 2，不等待触发词（见该 agent 的「Mode 2 启动条款」）。
- **不适用「重新确认激活状态」**：独立 agent 无确认对象，任务执行期间 Mode 2 持续有效。
- **经验层读取位置**：团队语境读 `<项目>/.harness-kb/learnings.md`（独立使用读 `references/learnings.md`）。

**黄金法则**：用户原始指令永远优先。警报和建议是增益，绝不覆盖。

**进化**：用户说「更新技能」/「update skill」时，加载 `references/evolution.md` 并遵循之。
