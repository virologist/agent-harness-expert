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
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROMOTE_THRESHOLD = 2  # 复现数 ≥ N 晋升


def atomic_write_text(path: Path, text: str) -> None:
    """F-09：唯一 tmp 名 + replace 原子写，避免中断留半截文件。"""
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _has_header(learnings_text: str) -> bool:
    """判断文本是否含 Pattern-Key 表头（F-04：区分 schema 损坏与合法空表）。"""
    return any(re.match(r"\|\s*Pattern-Key\s*\|", line)
               for line in learnings_text.splitlines())


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
    new_rows: list[list[str]] = []
    for row in rows:
        if len(row) < 6:
            # 畸形行（列数不足）不静默跳过——skip 必须可见可审计
            changes.append({"type": "skipped", "reason": f"列数不足 6（实际 {len(row)}）", "row": list(row)})
            new_rows.append(list(row))
            continue
        pk, first_seen, repro_count_str, status, source, summary = row[:6]
        if pk.startswith("_") or not pk.strip():
            new_rows.append(list(row))
            continue
        # 复现数列：解析为整数
        try:
            repro_count = int(repro_count_str.strip())
        except ValueError:
            # 畸形行（复现数非整数）不静默跳过——skip 必须可见可审计
            changes.append({"type": "skipped", "reason": f"复现数非整数: {repro_count_str!r}", "row": list(row)})
            new_rows.append(list(row))
            continue
        new_status = status
        if repro_count >= PROMOTE_THRESHOLD and status == "pending":
            new_status = "promoted"
        elif repro_count < PROMOTE_THRESHOLD and status == "promoted":
            new_status = "pending"
        if new_status != status:
            changes.append({
                "pk": pk, "from": status, "to": new_status, "repro_count": repro_count,
            })
        new_row = list(row)
        new_row[3] = new_status
        new_rows.append(new_row)
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
    # F-04：表头被删 = schema 损坏（fail-closed），不能与「表头在但无数据行」
    # 共用 noop/exit 0——否则晋升链静默停摆。
    if not _has_header(text):
        print(f"ERROR: {learnings_path} 缺少 Pattern-Key 表头（| Pattern-Key | ... |），"
              f"learnings schema 损坏，拒绝静默 noop", file=sys.stderr)
        return {"status": "schema_error", "reason": "missing_header"}
    header, rows, table_start = _parse_table(text)
    if not rows:
        return {"status": "noop", "reason": "empty_table", "header": header, "rows_count": 0}
    new_rows, changes = _apply_promotion(rows)
    # 分流：真实变更 vs 畸形行跳过（skip 可见可审计，但不触发写盘）
    skipped = [c for c in changes if c.get("type") == "skipped"]
    real_changes = [c for c in changes if c.get("type") != "skipped"]
    for s in skipped:
        print(f"WARNING: 跳过畸形行（{s['reason']}）: {s['row']}", file=sys.stderr)
    if not real_changes:
        result = {"status": "noop", "reason": "no_changes", "header": header,
                  "rows_count": len(rows), "changes": [], "skipped": skipped}
        if skipped:
            print(f"共 {len(skipped)} 条畸形行被跳过（无真实变更，文件未改动）", file=sys.stderr)
        return result
    # 重建 markdown：保留表前 + 表（用新数据）+ 表后
    lines = text.splitlines()
    table_end = table_start + 1  # header
    # 跳过分隔行
    if table_end < len(lines) and re.match(r"\|\s*---\s*\|", lines[table_end]):
        table_end += 1
    # 找表结束（第一个非 | 起始行）；表格在文件末尾且无尾随空行时，
    # for 循环不会 break —— 补 else 把 table_end 推到文末，避免末尾数据行被重复追加。
    for i in range(table_end, len(lines)):
        if not lines[i].strip().startswith("|"):
            table_end = i
            break
    else:
        table_end = len(lines)
    new_table = _serialize_table(header, new_rows)
    new_text = "\n".join(lines[:table_start]) + new_table + "\n" + "\n".join(lines[table_end:])
    # 落盘原文件（F-09：原子写）
    atomic_write_text(learnings_path, new_text)
    # 落盘晋升报告
    report = {
        "status": "promoted",
        "timestamp": _now_iso(),
        "learnings_path": str(learnings_path),
        "threshold": PROMOTE_THRESHOLD,
        "changes": real_changes,
        "skipped": skipped,
        "rows_processed": len(rows),
    }
    report_path = learnings_path.with_suffix(".promote-report.json")
    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    print(f"✓ 晋升 {len(real_changes)} 条 / 处理 {len(rows)} 行（阈值={PROMOTE_THRESHOLD}）")
    if skipped:
        print(f"⚠️ 另有 {len(skipped)} 条畸形行被跳过")
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
    try:
        result = promote(p)
    except (OSError, UnicodeDecodeError) as e:
        print(f"ERROR: 读取或写入失败: {e}", file=sys.stderr)
        return 1
    # F-04：error 与 schema_error 均 fail-closed 返回 1，只有成功/noop 返回 0
    return 0 if result.get("status") in ("promoted", "noop") else 1


if __name__ == "__main__":
    raise SystemExit(main())
