#!/usr/bin/env python3
"""v1.8 promoted 规则晋升：基于 learnings.md 的 Pattern-Key 跟踪表自动晋升。

晋升规则（与 learnings.md 采集协议一致）：
- 复现数 ≥ 2 的 pending 条目 → promoted（晋升为团队规则，列入下一版 P0/P1 优化候选）
- 复现数 < 2 的 promoted 条目 → demoted 回 pending（防止数据漂移）
- archived 状态只能由主理人显式标注（脚本不自动归档）

输入：项目级 .harness-kb/learnings.md 路径
输出：
  1. 原文件就地更新（状态列变更）
  2. 落盘晋升报告 <learnings.md 路径>.promote-report.json（含变更前后对比）

退出码：
  0 = 处理成功
  1 = 解析/写入失败
  2 = learnings.md 路径不存在（用户需先 init _harness_kb）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

PROMOTE_THRESHOLD = 2  # 复现数 ≥ N 晋升


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_table(learnings_text: str) -> tuple[list[str], list[list[str]], int]:
    """解析 learnings.md 的 Pattern-Key 跟踪表，返 (表头, 数据行, 表起始行号)。

    表头列：| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |
    """
    lines = learnings_text.splitlines()
    table_start = None
    for i, line in enumerate(lines):
        if re.match(r"\|\s*Pattern-Key\s*\|", line):
            table_start = i
            break
    if table_start is None:
        return [], [], -1
    header = [c.strip() for c in lines[table_start].strip("|").split("|")]
    # 跳过分隔行
    data_start = table_start + 2
    rows = []
    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line.startswith("|"):
            break
        cols = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cols)
    return header, rows, table_start


def _apply_promotion(rows: list[list[str]]) -> tuple[list[list[str]], list[dict]]:
    """对每行检查复现数/状态，返 (新行, 变更记录)。"""
    changes = []
    new_rows = []
    for row in rows:
        if len(row) < 6:
            new_rows.append(row)
            continue
        pk, first_seen, repro_count_str, status, source, summary = row[:6]
        if pk.startswith("_") or not pk.strip():
            new_rows.append(row)
            continue
        # 复现数列：解析为整数
        try:
            repro_count = int(repro_count_str.strip())
        except ValueError:
            new_rows.append(row)
            continue
        new_status = status
        change = {"pk": pk, "from": status, "to": new_status, "repro_count": repro_count}
        if repro_count >= PROMOTE_THRESHOLD and status == "pending":
            new_status = "promoted"
        elif repro_count < PROMOTE_THRESHOLD and status == "promoted":
            new_status = "pending"
        change["to"] = new_status
        if new_status != status:
            changes.append(change)
        new_rows = list(row)
        new_rows[3] = new_status
        new_rows = tuple(new_rows)
        new_rows = list(new_rows)
    return new_rows, changes


def _serialize_table(header: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(header) + " |"]
    # 分隔行
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def promote(learnings_path: Path) -> dict:
    if not learnings_path.is_file():
        print(f"ERROR: learnings.md 不存在: {learnings_path}（请先跑 _harness_kb_init.py 建 .harness-kb/）", file=sys.stderr)
        return {"status": "error", "reason": "file_not_found"}
    text = learnings_path.read_text(encoding="utf-8")
    header, rows, table_start = _parse_table(text)
    if not rows:
        return {"status": "noop", "reason": "empty_table", "header": header, "rows_count": 0}
    new_rows, changes = _apply_promotion(rows)
    if not changes:
        return {"status": "noop", "reason": "no_changes", "header": header, "rows_count": len(rows), "changes": []}
    # 重建 markdown：保留表前 + 表（用新数据）+ 表后
    lines = text.splitlines()
    table_end = table_start + 1  # header
    # 跳过分隔行
    if table_end < len(lines) and re.match(r"\|\s*---\s*\|", lines[table_end]):
        table_end += 1
    # 找表结束（第一个非 | 起始行）
    for i in range(table_end, len(lines)):
        if not lines[i].strip().startswith("|"):
            table_end = i
            break
    new_table = _serialize_table(header, new_rows)
    new_text = "\n".join(lines[:table_start]) + new_table + "\n" + "\n".join(lines[table_end:])
    # 落盘原文件
    learnings_path.write_text(new_text, encoding="utf-8")
    # 落盘晋升报告
    report = {
        "status": "promoted",
        "timestamp": _now_iso(),
        "learnings_path": str(learnings_path),
        "threshold": PROMOTE_THRESHOLD,
        "changes": changes,
        "rows_processed": len(rows),
    }
    report_path = learnings_path.with_suffix(".promote-report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ 晋升 {len(changes)} 条 / 处理 {len(rows)} 行（阈值={PROMOTE_THRESHOLD}）")
    print(f"  报告: {report_path}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="learnings.md Pattern-Key promoted 规则自动晋升")
    ap.add_argument("--learnings", required=True, help="<项目>/.harness-kb/learnings.md 路径")
    args = ap.parse_args()
    p = Path(args.learnings).expanduser().resolve()
    if not p.is_file():
        print(f"ERROR: learnings.md 不存在: {p}", file=sys.stderr)
        return 2
    result = promote(p)
    return 0 if result.get("status") != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
