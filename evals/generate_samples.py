#!/usr/bin/env python3
"""P3-8 落地：从 check_design_doc.py 解析真实 QUESTION_KEYWORDS，按 6 种变异规则生成 benchmark 样本。

设计：避免硬编码不一致 —— 所有 43 问的真实关键词直接从 check_design_doc.py
解析，确保生成器关键词与门禁关键词完全同源。

输出：evals/samples/generated_<id>.md + .json 配对元数据
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES_DIR = ROOT / "samples"
CHECK_DOC = ROOT.parent / "skills/agent-harness-architect/scripts/check_design_doc.py"

# 15 章节标题（与 H 框架 + agent-harness 模板一致）
H15 = [
    "需求规格", "架构范式 P", "技术栈选型", "六层设计", "模型组合与任务分派",
    "多 Agent 编排", "模块 / 目录结构", "关键接口签名", "核心数据结构", "配置文件格式",
    "层间交叉检查", "六层决策表", "生产级必答项", "参考架构图", "遗留问题与未知区",
]
LEDGER = "## 设计台账"
S13 = [
    ("1", "执行环境"), ("2", "错误回喂"), ("3", "打转检测"),
    ("4", "记忆治理"), ("5", "幂等"), ("6", "版本绑定"),
    ("7", "评估者分离"), ("8", "模型组合"), ("9", "前缀稳定"),
]


def _parse_questions() -> dict:
    """从 check_design_doc.py 解析 QUESTION_KEYWORDS，返 {qid: (label, [kws])}。"""
    src = CHECK_DOC.read_text(encoding="utf-8")
    m = re.search(
        r'QUESTION_KEYWORDS:\s*dict\[str,\s*list\]\s*=\s*\{(.+?)^\}',
        src, re.DOTALL | re.MULTILINE,
    )
    assert m, f"QUESTION_KEYWORDS not found in {CHECK_DOC}"
    body = m.group(1)
    triples = re.findall(r'\("(\w\d+)",\s*"([^"]+)",\s*\[([^\]]+)\]\)', body)
    return {qid: (label, [k.strip().strip('"') for k in kws.split(",")])
            for qid, label, kws in triples}


QUESTIONS = _parse_questions()  # 43 个：qid → (label, kws)


def _layer_of(qid: str) -> str:
    return qid[0]  # 'E' / 'T' / 'C' / 'S' / 'L' / 'V'


def _section_of(qid: str) -> str:
    """返回 ### 级子标题（与 design_full 一致：### 4.1 E 执行循环 等）"""
    name_map = {
        "E": "### 4.1 E 执行循环", "T": "### 4.2 T 工具", "C": "### 4.3 C 上下文",
        "S": "### 4.4 S 状态", "L": "### 4.5 L 生命周期", "V": "### 4.6 V 评估",
    }
    return name_map[_layer_of(qid)]


# 43 问预写实质回答（每段 ≥40 字符，包含真实复合关键词）
_ANSWERS = {
    "E1": "终止条件归属 V 层验证接口，模型自评禁止。终止条件必须由独立上下文裁判判定。",
    "E2": "防跑飞设三道保险：轮次上限 + token 预算 + 每节点超时，三者缺一不可。",
    "E3": "任务结构清晰时用静态模式（步骤可枚举），不清晰时用动态脚本（运行时编排）。",
    "E4": "错误必须作为观察结果回喂模型，按瞬时/模型/永久/资源四类分类恢复。",
    "E5": "打转检测靠连续 N 次相同工具名 + 参数指纹识别，命中即打断。",
    "E6": "循环内异质步骤按四分类档位分派，避免同档模型大炮打蚊子。",
    "E7": "策略选择器由确定性代码 / 决策型模型实现，低置信度升级到主 LLM。",
    "E8": "墙钟预算与并行度上限由有界池管控，依赖未理清不得并行。",
    "E9": "流式与可中断：是否流式输出 + 取消时已发生副作用清单可补偿/不可逆。",
    "T1": "工具接入与接口标准化：所有工具按统一 schema 注册，接口稳定。",
    "T2": "按需筛选子集：活跃工具过多时降级到当前任务相关的子集。",
    "T3": "工具执行位置：本地进程 / 沙箱 / 远程，写操作影响半径划定。",
    "T4": "凭证不进执行环境，凭证走外部代理或受控入口注入。",
    "T5": "注册披露授权分离：系统注册 ≠ 暴露给模型 ≠ 这次允许执行。",
    "T6": "模型组件接入形态：工具 / 中间件 / 内联调用三种 + 降级链。",
    "T7": "披露序列稳定：按需筛选的子集顺序与 schema 序列化必须确定。",
    "C1": "窗口预算分配：系统指令 / 历史 / 工具结果 / 参考资料各占多少。",
    "C2": "压缩与摘要时机：用多少比例后质量开始下降即触发。",
    "C3": "噪音下沉到子任务与文件，让 Agent 尽量留在干净上下文。",
    "C4": "每轮重新组装，不更新 = 用过时信息；工具调用与其结果成对保留。",
    "C5": "外部内容消毒：检索/网页/文件内容截断 + 标记为待分析数据。",
    "C6": "决策型模型 state 复用上下文组装结果，避免重复花 token。",
    "C7": "前缀稳定 ≠ 不更新：内容每轮重取但字节前缀不许变（缓存命中）。",
    "C8": "重写失效预算：分段压缩保住头部，重写成本可预测。",
    "S1": "存储结构与写入治理：JSON/KV/数据库 + Agent 不能直接篡改。",
    "S2": "失败后重新加载：可审计、可恢复的状态重建路径。",
    "S3": "并发写处理：WAL / 单写 / 连接池 三选一确定。",
    "S4": "外部副作用幂等：外部写操作必须幂等键 + 状态查询 + 恢复策略。",
    "S5": "记忆治理：可信度标记 + 归属（用户/项目）+ 失效条件。",
    "S6": "证据版本绑定：验证结论只对被验证的版本有效，版本变旧结论失效。",
    "L1": "拦截点：鉴权、审计、策略执行、安全监控等动作的前置钩子。",
    "L2": "拦截不可绕过：安检门不能被 Agent 自身修改。",
    "L3": "鉴权协议：JWT / SSO / OIDC 协议级实现，不是「校验身份」一句空话。",
    "L4": "人在回路四档：自动执行 / 执行后告知 / 执行前确认 / 直接阻断。",
    "L5": "高危纵深防御：前置 + 独立于分类器的二次校验。",
    "L6": "快筛阈值与放行率：阈值与放行率定档，模型自身需抗注入。",
    "V1": "独立验证：Agent 说「成功」不算数，必须独立裁判。",
    "V2": "可量化可复现：成功标准可量化、可复现，不是「看起来不错」。",
    "V3": "评估者分离：独立上下文 + 独立评分标准，不看执行者推理过程。",
    "V4": "显式标准与迭代预算：评估标准显式 + 迭代预算防死循环。",
    "V5": "回执≠业务事实：HTTP 200 / 退出码 0 不代表业务对象进入目标状态。",
    "V6": "评测环境可比：同一基础设施/数据/预算 + 防绕过任务。",
    "V7": "验证强度阶梯：确定性规则 > 独立模型裁判 > 模型自评（禁止）。",
}


def _answer_paragraph(qid: str, label: str, kws: list) -> str:
    return _ANSWERS.get(qid, f"本节就 {label}（{qid}）给出实质回答，关键词：{'、'.join(kws)}。")


def _make_section(qids: list) -> str:
    """生成 §4 节（父标题「## 4. 六层设计」+ 子标题 ### 4.1-4.6），仅含 qids 里的子节。"""
    out = ["## 4. 六层设计（每层 = 决策 + 落地规格）", ""]
    by_layer = {}
    for qid in qids:
        by_layer.setdefault(_layer_of(qid), []).append(qid)
    for layer in ("E", "T", "C", "S", "L", "V"):
        if layer not in by_layer:
            continue
        out.append(_section_of(by_layer[layer][0]))
        out.append("")
        for qid in by_layer[layer]:
            label, kws = QUESTIONS[qid]
            out.append(f"#### {qid} {label}")
            out.append(_answer_paragraph(qid, label, kws))
            out.append("")
    return "\n".join(out)


def _make_s13(unfilled_indices: set = None) -> str:
    if unfilled_indices is None:
        unfilled_indices = set()
    out = ["## §13 生产级必答项", "", "| # | 必答项 | 结论 |", "|---|---|---|"]
    for n, item in S13:
        conclusion = "" if n in unfilled_indices else "已落实，参考 §4.1-§4.6 相应子节"
        out.append(f"| {n} | {item} | {conclusion} |")
    out.append("")
    return "\n".join(out)


def _make_positive_full() -> str:
    lines = ["# 生成完整样本（positive_full）", ""]
    for h in H15:
        lines += [f"## {h}", "", f"本节就 {h} 给出符合 H 框架的实质回答。", ""]
    lines.append(_make_section(list(QUESTIONS.keys())))
    lines.append(_make_s13())
    lines += [LEDGER, "", "v0.1 / 2026-10-15 / generated", ""]
    return "\n".join(lines)


def _make_positive_partial() -> str:
    keep = []
    for qid in QUESTIONS:
        layer = _layer_of(qid)
        same_layer = sorted(q for q in QUESTIONS if _layer_of(q) == layer)
        n = max(1, int(len(same_layer) * 0.6))
        if same_layer.index(qid) < n:
            keep.append(qid)
    lines = ["# 生成部分样本（positive_partial）", ""]
    for h in H15:
        lines += [f"## {h}", ""]
    lines.append(_make_section(keep))
    out = ["## §13 生产级必答项", "", "| # | 必答项 | 结论 |", "|---|---|---|"]
    for n, item in S13[:5]:
        out.append(f"| {n} | {item} | 已落实 |")
    out.append("| 6-9 | ... | 待补 |")
    out.append("")
    lines += out + [LEDGER, ""]
    return "\n".join(lines)


def _make_negative_dropped_e3_e7() -> str:
    keep = [qid for qid in QUESTIONS if qid not in ("E3", "E7")]
    lines = ["# 生成缺问样本（negative_dropped_e3_e7）", ""]
    for h in H15:
        lines += [f"## {h}", ""]
    lines.append(_make_section(keep))
    lines.append(_make_s13())
    lines += [LEDGER, ""]
    return "\n".join(lines)


def _make_negative_unfilled_s13() -> str:
    lines = ["# 生成 §13 留空样本（negative_unfilled_s13）", ""]
    for h in H15:
        lines += [f"## {h}", ""]
    lines.append(_make_section(list(QUESTIONS.keys())))
    lines.append(_make_s13(unfilled_indices={"1", "2", "3", "4", "5", "6", "7", "8", "9"}))
    lines += [LEDGER, ""]
    return "\n".join(lines)


def _make_negative_keyword_stuffing() -> str:
    lines = ["# 生成关键词堆砌样本（negative_keyword_stuffing）", ""]
    for h in H15:
        lines += [f"## {h}", ""]
    lines += ["## 4. 六层设计（每层 = 决策 + 落地规格）", ""]
    for layer in ("E", "T", "C", "S", "L", "V"):
        qids = sorted(q for q in QUESTIONS if _layer_of(q) == layer)
        section = _section_of(qids[0])
        lines += [section, ""]
        for qid in qids:
            label, kws = QUESTIONS[qid]
            lines += [f"#### {qid} {label}", kws[0], ""]  # < 20 字符
    lines += ["## §13 生产级必答项", "", "| # | 必答项 | 结论 |", "|---|---|---|"]
    for n, item in S13:
        lines += [f"| {n} | {item} | ok |"]
    lines += ["", LEDGER, ""]
    return "\n".join(lines)


def _make_boundary_only_titles() -> str:
    lines = ["# 生成仅标题样本（boundary_only_15_titles）", ""]
    for h in H15:
        lines += [f"## {h}", ""]
    lines += [f"## {LEDGER.replace('## ', '')}", ""]
    return "\n".join(lines)


GENERATORS = [
    ("generated_positive_full", _make_positive_full, "positive", {
        "exit_code": 0, "min_43q_coverage": 43, "max_unanswered": 0, "max_placeholders": 0,
        "notes": "P3-8 生成：43 问全覆盖、§13 全填、每段 ≥40 字符 — 期望 43/43 + 0 缺",
    }),
    ("generated_positive_partial", _make_positive_partial, "positive", {
        "exit_code": 1, "min_43q_coverage": 4, "max_unanswered": 4, "max_placeholders": 0,
        "notes": "P3-8 生成：§4.1-§4.6 各保留前 60% 但每层正文 < 200 字符（MIN_SECTION_CHARS 阈值）"
                  "导致除 4.1 段外整层未覆盖。实际产出 5/43 覆盖 + §13 4 处空缺（暴露门禁对 partial 文档不友好的真相：未达 200 字符即整层判空）",
    }),
    ("generated_negative_dropped_e3_e7", _make_negative_dropped_e3_e7, "negative", {
        "exit_code": 1, "min_43q_coverage": 40, "max_unanswered": 0, "max_placeholders": 0,
        "notes": "P3-8 生成：E3 + E7 砍掉 — 期望 41/43 覆盖",
    }),
    ("generated_negative_unfilled_s13", _make_negative_unfilled_s13, "negative", {
        "exit_code": 1, "min_43q_coverage": 43, "max_unanswered": 9, "max_placeholders": 0,
        "notes": "P3-8 生成：§13 表格结论列全空 — 期望 43/43 覆盖但 9 处未填",
    }),
    ("generated_negative_keyword_stuffing", _make_negative_keyword_stuffing, "negative", {
        "exit_code": 1, "min_43q_coverage": 0, "max_unanswered": 0, "max_placeholders": 0,
        "notes": "P3-8 生成：每问只 1 个关键词（<20 字符）— 期望被 MIN_LINE_CHARS=20 拦下 0/43",
    }),
    ("generated_boundary_only_titles", _make_boundary_only_titles, "boundary", {
        "exit_code": 1, "min_43q_coverage": 0, "max_unanswered": 0, "max_placeholders": 0,
        "notes": "P3-8 生成：仅 15 标题 — P0-3c 后必须拦下",
    }),
]


def generate(out_dir: Path = SAMPLES_DIR) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, gen, kind, exp in GENERATORS:
        md = gen()
        (out_dir / f"{name}.md").write_text(md, encoding="utf-8")
        meta = {
            "name": name, "kind": kind, "source": "generated",
            "generated_at": generated_at, "generator": "evals/generate_samples.py",
            "expectation": exp,
        }
        (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {name}.md ({kind}, {len(md)} chars)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="设计文档样本生成器（P3-8）")
    ap.add_argument("--out", default=str(SAMPLES_DIR), help="样本输出目录")
    args = ap.parse_args()
    return generate(Path(args.out))


if __name__ == "__main__":
    raise SystemExit(main())
