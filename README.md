# Agent Harness 全流程研发专家团

> **版本**：v1.8.2（pytest 110/110 / evals 16/16 / validate 0 errors）
> **v1.8.2 变更**：修复 state_io 旧 schema 崩溃与并发写数据丢失；修 7 项可靠性缺陷（表头缺失 fail-closed、JSON 损坏告警、--force 断点保护、非原子写、LibreOffice 静默吞异常）；wiki 根防污染护栏接入团队模板；确定性路径选路替代 find|head；版本号与 9 成员/110 测试内容对齐
> **EVAL 口径**：最新结果 = `evals/results/1.8.2.json`（16/16 PASS、total_questions=43）；`evals/results/1.8.1.json` = **有效历史归档**（total_questions=43，本批入库）；`evals/results/v1.8.1.json`（及同形 `v1.8.0.json`）= **废弃口径**（total_questions=0，旧版误用 `v` 前缀跑 benchmark 落盘的遗留），**勿引用**
> **v1.8.1 变更（历史）**：恢复包根 `settings.json`（官方校验 1 error → 0 error）+ wiki lint 空目录明确报错。`settings.json` 属**发布源资产**：随 CANON 一起打包以过官方校验，但运行时从不读取（见下方「发布源纪律」）——历史口径与「缺失不视为错误」并不矛盾
> **版本可追溯性（tag ↔ 内容）**：tag `v1.8.1`（commit `16ad92a`）对应**旧内容**——5 成员（lead + 4）/ 89 测试；当前工作区及 `v1.8.2` tag 为 **10 成员（lead + 9）/ 110 测试**。**不要按 v1.8.1 还原成员结构**（会退回 5 人团队），本批 commit 后已打 tag `v1.8.2`
> **三源部署**：my-experts HEAD + GitHub push + OneDrive 镜像
> **v1.1 报告 29 项短板 100% 处置**——含跳过 2 项的转化落地
> **跨包元教训**：9 条 ML-1 ~ ML-9 见 `evals/META_LESSONS.md`

把用户的一个想法、或某个领域的最新研究，编排成**可落地的 agent**。基于通用框架 **H=(E,T,C,S,L,V)+P**（Harness = 六层功能 + 架构范式 P；层定义详解见包内 `skills/agent-harness-architect/references/h-framework.md`），由主理人编排九名专职成员协作完成，并沉淀进自进化知识底座。

## 类型

Team 型（多角色协作团队）

## 三道门禁

- **pytest**：110/110 通过（v1.5.2 baseline 0）
- **evals benchmark**：16/16 PASS（7 fixtures + 6 generated + 3 real samples）
- **validate_expert**：0 errors（v1.5.2 baseline 3 errors）

## 门禁使用

```bash
# 跑全部 pytest
python3 -m pytest tests/ -q

# 跑 evals benchmark（门禁）
# 注意：--version 用**不带 v 前缀**的版本号（如 1.8.2），落盘即 results/1.8.2.json
# 若误用 v 前缀，会生成 results/vX.Y.Z.json（total_questions=0 的**废弃口径**，勿引用）
python3 evals/run_benchmark.py --version 1.8.2

# 重生成 6 个 generated 样本（关键词与门禁同源）
python3 evals/generate_samples.py
```

## 跨包元教训（9 条）

详见 `evals/META_LESSONS.md`——9 条 ML 跨包可复用教训，评审任何 Team 型专家包时引用。

## 关键 commit 索引

| 范围 | commit | 摘要 |
|---|---|---|
| 规范 | `6052a9e` | profession 对齐（agent 名由 `.codebuddy-plugin/plugin.json` 的 `agentName`/`agents[]` 解析，不依赖 `settings.json`） |
| 门禁 | `98887be` / `de246e2` | 退出码反转 + 43 问覆盖 + 加固 |
| 门禁 | `e00d920` | MUST_ANSWER 限域到 §4.1-§4.6 |
| 协作 | `79def5c` | 撞限协议下沉四成员 |
| 协作 | `8a6e81c` | 回传信封 schema 化 |
| 状态 | `c562da3` | 断点状态机显式化 |
| 工具 | `2a58eed` | Mode 2 告警落 `<项目>/.harness-kb/mode2-log.md` |
| 真实样本 | `aca043f` | viral-evo-lab P4_monitoring_design.md（127 行真实设计） |
| 路线图 | `361e738` / `aca043f` | v1.6.0 + v1.7.1 |
| 多模板 | `eb50394` | v1.7.2：check_design_doc 加 --template 参数（harness / problem-solution） |
| 自进化 | `b015671` / `26a936a` | v1.8：promoted 规则晋升机制（复现数 ≥2 自动晋升 + demote 防护） |
| 可靠性 | `v1.8.2`（本批） | 修 state_io 旧 schema 崩溃与并发写丢失 + 7 项可靠性缺陷；wiki 护栏接线 + 确定性路径选路；`parse_raw` 输出改原子写；9 成员/110 测试入编并打 tag |

## 团队成员

主理人（team-lead，编排指挥）+ 九名专职成员：研究员（P0 检索整理，只读不写 wiki）、架构师（P1 六层设计）、编码工程师（P2 落地代码）、可靠性工程师（P2.5 常驻，运行期稳定性）、测试工程师（P3 独立对抗验证）、一致性审计员（P3.5/发布前静态对账）、验收评审员（P3 终审/P4 语义与价值裁决准备）、发布运维工程师（P4 发布链与多副本同步）、知识策展人（各阶段收尾 wiki 语义审计，只读不写 wiki）。完整名单与头像见 `.codebuddy-plugin/plugin.json` 的 `agents`。

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
- **知识底座**：`wiki-creator` 作为唯一底座，零向量、零 chunk、单页为知识单元、两级索引，随项目自进化（轻量型任务跳过编译）。每次增量编译后由知识策展人做语义级质量审计（矛盾/陈旧/不对题引用；轻量型跳过）。

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

> **发布源纪律（D1）**：**发布源 = CANON**（`~/.workbuddy/plugins/marketplaces/my-experts/plugins/agent-harness-expert`，git 权威源），**禁止从 EXPERT_DIR**（`~/.workbuddy/plugins/marketplaces/experts/plugins/agent-harness-expert`，宿主运行时副本）打包。宿主会按私有规则过滤 `settings.json` 等文件、并随时间覆盖运行时副本；从 EXPERT_DIR 打包会丢失发布资产、导致官方校验回到 1 error。所有源码/文档改动先落 CANON，验证通过后逐文件同步到 EXPERT_DIR（`settings.json` / `.downloaded_at` 不同步）。
>
> **`settings.json` 缺失不视为错误（F-05 明文）**：该文件属**发布源资产**——随 CANON 一起打包以过官方校验，但**程序运行不依赖该文件**（agent 名由 `.codebuddy-plugin/plugin.json` 的 `agentName` / `agents[]` + 各成员 frontmatter 解析，运行时不读 `settings.json`）。宿主按私有规则过滤该文件、运行期缺失由宿主管理，属**合法态**。**不要反复手工补写 EXPERT_DIR**——宿主同步会覆盖它，手工补写既无效又制造双副本漂移。

将 **CANON** 的 `agent-harness-expert/` 目录整体压缩为 zip（排除 `.DS_Store`、`__MACOSX/`）：

```bash
zip -r agent-harness-expert.zip agent-harness-expert -x "*.DS_Store" -x "__MACOSX*"
```
