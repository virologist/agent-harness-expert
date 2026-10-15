# Agent Harness 设计文档门禁 Benchmark（evals/）

> 跑 `python3 evals/run_benchmark.py --version <tag>` 对 7 + 6 = 13 个样本跑 check_design_doc
> 门禁，落盘结果到 `results/<version>.json`，输出 PASS/FAIL 表格 + 退出码 0/1/2。

## 样本来源（两类）

### 1. fixtures（7 个，symlink 到 `tests/fixtures/`）

P0-3c 加固门禁时定义的 6 个验收锚点 + 1 个 v1.2 报告新增的 boundary 样本。**本质上是「门禁自检的样本」，反映 P0-3c 加固是否生效——自证循环**。每版发布必须保持这 7 个全 PASS。

| 样本 | kind | 用途 |
|---|---|---|
| `design_from_template.md` | positive | 按模板填满 → 期望 43/43 + exit 0 |
| `design_full.md` | positive | 完整文档 → 期望 43/43 + exit 0 |
| `design_boundary_headings_only.md` | boundary | 仅 15 标题 → 期望 exit 1（无 4.x 限域） |
| `design_empty_conclusions.md` | negative | §13 结论空 → 期望 9 处未填 |
| `design_headings_only.md` | negative | 仅标题 → 期望 exit 1 |
| `design_missing_sections.md` | negative | 缺章节 → 期望 exit 1 |
| `design_placeholder.md` | negative | 含占位符 → 期望 22 处占位符 |

### 2. generated（6 个，由 `generate_samples.py` 产出）

P3-8 落地：从 `check_design_doc.py` 解析真实 QUESTION_KEYWORDS（43 问 + 复合关键词），按 6 种变异规则生成样本。**关键词与门禁同源，无硬编码漂移**。覆盖边界用例与门禁盲点探测。

| 样本 | kind | 用途 | 实测 |
|---|---|---|---|
| `generated_positive_full.md` | positive | 43 问全覆盖 + §13 全填 + 限域每段 ≥40 字符 | 43/43 + exit 0 |
| `generated_positive_partial.md` | positive | §4.1-§4.6 各保留前 60%，§13 填 5/9 | 5/43 + exit 1（**门禁对 partial 文档不友好：未达 200 字符整层判空，暴露 MIN_SECTION_CHARS=200 阈值的二元性**） |
| `generated_negative_dropped_e3_e7.md` | negative | E3 + E7 砍掉 | 41/43 + exit 1 |
| `generated_negative_unfilled_s13.md` | negative | §13 表格结论列全空 | 43/43 覆盖 + 9 处未填 + exit 1 |
| `generated_negative_keyword_stuffing.md` | negative | 每问只 1 个关键词（<20 字符） | 0/43 + exit 1（被 MIN_LINE_CHARS=20 拦下） |
| `generated_boundary_only_titles.md` | boundary | 仅 15 标题 | 0/43 + exit 1 |

## 复跑命令

```bash
# 跑当前所有样本
python3 evals/run_benchmark.py --version "1.6.0-post-p3-8"

# 重生成所有 generated 样本（覆盖式）
python3 evals/generate_samples.py

# 复跑确认 P0 锚点没破
python3 -m pytest tests/ -q
```

## 跨版本结果

`results/` 目录按 `<version>.json` 命名保留历次跑分。比较时关注 `samples[].verdict` 字段从 `PASS` 变 `FAIL` 的样本。

## 局限

- fixtures 7 个是「门禁自检的样本」——自证循环，每版必保 7/7 但不能反映「门禁对真实设计的有效性」
- generated 6 个是「关键词同源变异」——反映「门禁对可生成用例的覆盖」但不反映真实世界多样性
- 真实世界设计文档（从历史项目抽取）尚未纳入——这是 P3 候选清单的 P3-N+1（要追溯到「真实样本征集」流程）
