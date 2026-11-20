#!/usr/bin/env python3
"""test_promoted_checker.py：测试 v1.8 promoted 规则自动晋升逻辑。

覆盖：
- pending + 复现数 ≥ 2 → promoted
- pending + 复现数 < 2 → 不变
- promoted + 复现数 < 2 → demoted 回 pending（防止数据漂移）
- 表格为空 → noop
- 报告 JSON 落盘正确
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# 把被测脚本所在目录加入 sys.path
TESTS_DIR = Path(__file__).resolve().parent
SCRIPT_DIR = TESTS_DIR.parent / "skills" / "coding-prompt" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from promoted_checker import (  # noqa: E402
    _parse_table, _apply_promotion, _serialize_table, promote, PROMOTE_THRESHOLD,
)


SAMPLE_TABLE = """| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |
|---|---|---|---|---|---|
| PK-coder-001 | 2026-10-15 | 1 | pending | coder | 写代码前先读设计文档 |
| PK-coder-002 | 2026-10-15 | 3 | pending | coder | 写完即跑 pytest 验证 |
| PK-coder-003 | 2026-10-15 | 5 | promoted | coder | DoD 清单 9 条必过 |
| PK-tester-001 | 2026-10-15 | 1 | promoted | tester | 假完成检测必跑 |
| _(空占位)_ | | | | | |
"""


def test_parse_table_basic():
    """表头 6 列 + 数据 4 行（空占位不计）。"""
    header, rows, start = _parse_table(SAMPLE_TABLE)
    assert len(header) == 6
    assert header[0] == "Pattern-Key"
    assert len(rows) == 5  # 含 1 行空占位
    assert rows[0][0] == "PK-coder-001"
    assert start >= 0  # 应在某个有效行号


def test_parse_table_empty():
    """空文本 → header=[], rows=[], start=-1"""
    header, rows, start = _parse_table("无表格的 markdown 文本")
    assert header == []
    assert rows == []
    assert start == -1


def test_apply_promotion_threshold():
    """复现数 ≥ 2 晋升；复现数 < 2 不动；promoted + 复现 < 2 demote。"""
    header, rows, _ = _parse_table(SAMPLE_TABLE)
    new_rows, changes = _apply_promotion(rows)
    by_pk = {r[0]: r[3] for r in new_rows}
    # PK-coder-001: pending + 1 → 不变 (pending)
    assert by_pk["PK-coder-001"] == "pending"
    # PK-coder-002: pending + 3 → 晋升 (promoted)
    assert by_pk["PK-coder-002"] == "promoted"
    # PK-coder-003: promoted + 5 → 不变
    assert by_pk["PK-coder-003"] == "promoted"
    # PK-tester-001: promoted + 1 → demote (pending)
    assert by_pk["PK-tester-001"] == "pending"
    # 变更数 2 (002 升 + tester-001 降)
    assert len(changes) == 2
    pk_changes = {(c["pk"], c["from"], c["to"]) for c in changes}
    assert ("PK-coder-002", "pending", "promoted") in pk_changes
    assert ("PK-tester-001", "promoted", "pending") in pk_changes


def test_apply_promotion_noop():
    """所有条目均符合现状（pending 复现 < 2 / promoted 复现 ≥ 2）→ 0 变更。"""
    md = """| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |
|---|---|---|---|---|---|
| PK-x-1 | 2026-10-15 | 1 | pending | coder | foo |
| PK-x-2 | 2026-10-15 | 5 | promoted | coder | bar |
"""
    _, rows, _ = _parse_table(md)
    new_rows, changes = _apply_promotion(rows)
    assert len(changes) == 0
    # 行内容应不变
    assert new_rows[0][3] == "pending"
    assert new_rows[1][3] == "promoted"


def test_serialize_table_round_trip():
    """_serialize_table 应能写出符合解析格式的表。"""
    header = ["Pattern-Key", "首次见", "复现数", "状态", "来源", "简述"]
    rows = [
        ["PK-x-1", "2026-10-15", "1", "pending", "coder", "foo"],
        ["PK-x-2", "2026-10-15", "5", "promoted", "coder", "bar"],
    ]
    md = _serialize_table(header, rows)
    # 重新解析应得回原数据
    h2, r2, _ = _parse_table(md)
    assert h2 == header
    assert r2 == rows


def test_promote_end_to_end():
    """完整流程：临时文件 → 跑 promote → 验证变更落盘 + 报告生成。

    夹具手工构造（沿原本文件 fixture 的 mkstemp 形态），使 pytest 与
    tests/run_tests.py 纯 stdlib 入口都能直接运行本用例。
    """
    import os
    fd, path = tempfile.mkstemp(suffix=".md", prefix="learnings-")
    os.close(fd)
    p = Path(path)
    p.write_text(SAMPLE_TABLE, encoding="utf-8")
    try:
        from promoted_checker import promote
        report = promote(p)
        assert report["status"] == "promoted"
        assert report["rows_processed"] == 5  # 4 数据行 + 1 空占位
        assert report["threshold"] == PROMOTE_THRESHOLD
        assert len(report["changes"]) == 2
        # 原文件已落盘
        text = p.read_text(encoding="utf-8")
        assert "promoted" in text
        # 报告 JSON 落盘
        report_path = p.with_suffix(".promote-report.json")
        assert report_path.is_file()
        report_data = json.loads(report_path.read_text(encoding="utf-8"))
        assert report_data["status"] == "promoted"
    finally:
        p.unlink(missing_ok=True)
        p.with_suffix(".promote-report.json").unlink(missing_ok=True)


def test_promote_schema_error_when_header_missing():
    """F-04：表头被删 = schema_error（非 noop），绝不静默 exit 0。"""
    fd, path = tempfile.mkstemp(suffix=".md", prefix="learnings-nohdr-")
    import os
    os.close(fd)
    p = Path(path)
    # 表头被删，只剩普通正文（无任何 | Pattern-Key | 行）
    p.write_text("# 经验沉淀\n\n正文段落，没有表格表头。\n", encoding="utf-8")
    try:
        from promoted_checker import promote
        report = promote(p)
        assert report["status"] == "schema_error", report
        assert report["reason"] == "missing_header", report
        # 不得生成晋升报告（fail-closed，不写盘）
        assert not p.with_suffix(".promote-report.json").exists()
    finally:
        p.unlink(missing_ok=True)


def test_promote_noop_when_table_header_exists_but_no_rows():
    """F-04：表头在但无数据行 = 合法 noop（与 schema_error 区分）。"""
    fd, path = tempfile.mkstemp(suffix=".md", prefix="learnings-emptyrows-")
    import os
    os.close(fd)
    p = Path(path)
    p.write_text(
        "| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |\n"
        "|---|---|---|---|---|---|\n",
        encoding="utf-8",
    )
    try:
        from promoted_checker import promote
        report = promote(p)
        assert report["status"] == "noop", report
        assert report["reason"] == "empty_table", report
    finally:
        p.unlink(missing_ok=True)


def test_cli_header_missing_returns_exit_one():
    """F-04：CLI 层表头缺失必须 exit 1（fail-closed），不得 exit 0。"""
    import subprocess
    fd, path = tempfile.mkstemp(suffix=".md", prefix="learnings-cli-")
    import os
    os.close(fd)
    p = Path(path)
    p.write_text("# 无表头正文\n", encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "promoted_checker.py"), "--learnings", str(p)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert proc.returncode == 1, f"表头缺失应 exit 1，实际 rc={proc.returncode}\n{proc.stderr}"
        assert "Pattern-Key" in proc.stderr, "错误应点名缺失的表头"
    finally:
        p.unlink(missing_ok=True)


def test_promote_noop_when_no_changes():
    """无变更时 → status=noop, 不写报告。

    夹具手工构造（形态同上），两测试入口兼容。
    """
    import os
    fd, path = tempfile.mkstemp(suffix=".md", prefix="learnings-noop-")
    os.close(fd)
    p = Path(path)
    p.write_text(
        "| Pattern-Key | 首次见 | 复现数 | 状态 | 来源 | 简述 |\n"
        "|---|---|---|---|---|---|\n"
        "| PK-x-1 | 2026-10-15 | 1 | pending | coder | foo |\n",
        encoding="utf-8",
    )
    try:
        from promoted_checker import promote
        report = promote(p)
        assert report["status"] == "noop"
        # 无报告落盘
        report_path = p.with_suffix(".promote-report.json")
        assert not report_path.exists()
    finally:
        p.unlink(missing_ok=True)
