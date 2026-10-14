---
name: CLM-8B
alias: clm-8b
type: model
category: 决策型
source: https://github.com/Contrastive-LM/CLM
added: 2026-09-28
version: v0.1（CLM-v0.1-8B，Apache-2.0 开源权重）
confidence: verified
pinned: false
---

## 一句话定位

Contrastive Language Models：对比学习（InfoNCE）训练的开源 System One 模型（决策型），用状态-动作嵌入对齐在封闭候选集上做类型化决策，可自托管，与 TypeSafe API 同 schema。

## 接口形态

- 自托管两进程：`clm-serve`（:8700，CPU，含嵌入缓存与热加载 head）+ vLLM Qwen3-8B pooling 编码器（:8090，GPU）；也支持进程内 `Engine.rank/answer` 免服务调用。
- TypeSafe 兼容 wire schema：`POST /v1/systemone`，同一个 CLMClient 可无缝切换本地 clm-serve 与托管 Jev（api.typesafe.ai）。
- 架构：冻结 LLM backbone（Qwen3-8B）+ 20M 参数可训练投影头；推理 = 每段新文本一次嵌入 + 每个缓存候选一次点积。
- 对应四分类中的「决策型模型（System One）」档位；训练数据：60M Nemotron Q&A 预训练 + 30M 合成难负例中训 + 1M agentic 轨迹后训。
- 来源：Apache-2.0 官方仓库 + 模型卡（2026-09-28 核实）。

## 延迟 / 成本量级

- 官方自报：零样本任务（computer-use/游戏/工具调用）与 Jev 相当、最高 9× 低延迟；微调后作 verifier 比 Jev 快 4.1–5.7×（作者自报，2026-09-28 核实）。
- 嵌入缓存：状态/动作嵌入分离缓存，候选文本只嵌入一次（官方示例：冷缓存 106 token / 热缓存 38 token，58.1ms，单卡 RTX 4090）。
- 无按 token 计价：Apache-2.0 开源自托管，成本 = GPU 算力；候选集大或跨状态复用时延迟优势最大。

## 已验证适用域

- 封闭候选集的类型化决策/工具路由/检索池初筛（官方 README：routes tools, shortlists retrieval pools, answers typed decisions）。
- best-of-N verifier（验证器）：轻量微调后 Terminal-Bench 2.1 87.6%、DeepSWE 81.6% SOTA（作者自报）。
- 候选动作多或跨状态复用的场景（WikiRacing / T-Rex 基准，官方仓库附带）。

## 已验证不适用域

- **非生成式**：只能在封闭候选集内打分/排序，不能生成自由文本或推理链（官方仓库架构描述，作者自报）。
- **长状态截断**：state 超 2048 token 被截断，需同时调大编码器与服务的 max length 且耗更多显存（官方自报）。
- **无视觉/多模态**：仅文本，视觉支持在 roadmap 未落地（官方自报）。
- 以上负结果均出自官方仓库/模型卡 → 按来源分级通则记 verified、标注"作者自报"。

## 降级策略

- 自托管实例故障：同 schema 切换托管 Jev（TypeSafe 兼容，客户端改动最小，见 jev 条目）。
- 无 GPU 环境：窄决策降级到快速低价 LLM 档位，或候选集有确定性特征时降级为确定性规则。
- 升档方向：若窄决策实际需要开放推理，属路由错误，应回归强力 LLM 档位。

## 设计启发

- 与 Jev 构成「自托管 vs 托管」同档对照：私有化部署约束、供应商锁定权衡的样本。
- 嵌入缓存机制：候选集大/高频复用时延迟优势——设计分档预算时可作"窄决策卸载收益"的量化参照。
- 轻量微调（20M head）即可适配领域：决策型模型"先通用后微调"的路线对照物。
