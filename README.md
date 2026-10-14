# Agent Harness 全流程研发专家团

把用户的一个想法、或某个领域的最新研究，编排成**可落地的 agent**。基于通用框架 **H=(E,T,C,S,L,V)+P**（Harness = 六层功能 + 架构范式 P；层定义详解见包内 `skills/agent-harness-architect/references/h-framework.md`），由主理人编排四名专职成员协作完成，并沉淀进自进化知识底座。

## 类型

Team 型（多角色协作团队）

## 团队成员

主理人（team-lead，编排指挥）+ 四名专职成员：研究员（P0 检索整理，只读不写 wiki）、架构师（P1 六层设计）、编码工程师（P2 落地代码）、测试工程师（P3 独立对抗验证）。完整名单与头像见 `plugin.json` 的 `members`。

## 功能

**入口分流（三型）**：主理人先判型再开工——
- **轻量型**（无架构决策的单模块任务）：快速通道，只派编码 + 测试两名成员，跳过研究/设计与 wiki 编译，确认门只停一次；
- **想法型**：直接进 P1；
- **研究型**：从 P0 开始走全流程。

全流程四阶段，每阶段收尾由主理人增量编译进知识底座：

- **P0 研究**（可选）：`agentic-ai-research` 检索顶会顶刊的 Agentic AI 最新成果，产出研究简报。
- **P1 设计**：`agent-harness-architect` 澄清需求 → H+P 六层设计 → 可直接编码的设计文档。
- **P2 编码**：`coding-prompt` 按设计落地代码，主动监测假完成/范围蔓延。
- **P3 测试**：`coding-prompt` 独立验证 + 交付检查，产出测试报告（含**必跑命令清单**与 **SDK 确定性校验清单**，交付物使用 CodeBuddy Agent SDK 时逐条必检）。
- **P4 交付引导**：主理人判定交付形态，给出发布路径（`sites` / `cloud-service` / 运行说明），经同意后代为执行——打通「能跑」到「能上线」的最后一公里。
- **知识底座**：`wiki-creator` 作为唯一底座，零向量、零 chunk、单页为知识单元、两级索引，随项目自进化（轻量型任务跳过编译）。

核心特征：**三件事分工宪法**（语义给 LLM、计算给确定性脚本、判断审核给管家节点/人）；**确认门分级**（全流程默认停两次：设计确认 + 交付终审；轻量型停一次；可按用户要求逐阶段确认或一路到底）；**包内知识只读、增量写项目内**（架构知识进 `.wiki-creator/`、编码经验进 `.harness-kb/`，包升级不丢沉淀）；wiki 脚本显式 `--root` 禁用自动探测，杜绝跨专家共用全局根。

> 团队本身就是 H 框架的「活体示范」：主理人编排 = E 层，成员各绑技能 = T 层，成员隔离 = C 层，知识底座 = S 层，管家节点确认门 = L 层，测试独立验证 = V 层。

## 使用示例

- 帮我把一个想法做成可落地的 agent
- 帮我设计一个 Agent Harness 架构
- 调研 Agentic AI 最新进展并整理研究简报

## 头像

团队与成员头像位于 `avatars/` 目录。如需替换为自定义头像，要求：PNG/JPG、512×512 px、单张 ≤ 500KB。

## 安装

在 WorkBuddy 中通过**专家中心导入本 zip** 安装；或手动将解包后的 `agent-harness-expert/` 目录放到专家插件目录（如 `~/.workbuddy/plugins/marketplaces/my-experts/plugins/`）后，按平台流程注册使其可见。

## 打包分享

将 `agent-harness-expert/` 目录整体压缩为 zip（排除 `.DS_Store`、`__MACOSX/`）：

```bash
zip -r agent-harness-expert.zip agent-harness-expert -x "*.DS_Store" -x "__MACOSX*"
```
