"""check_design_doc.py 冒烟测试（退出码语义 + 43 问覆盖）。

覆盖：完整文档 / 缺章节 / §13 结论空 / 占位符 / --lenient / --strict 兼容 /
43 问正负样本 / 文件不存在。
"""
from __future__ import annotations

import re

from _harness import (
    CHECK_DOC,
    FIXTURES,
    Workspace,
    contains,
    eq,
    exit_code,
    is_true,
    run,
)

FULL = FIXTURES / "design_full.md"
MISSING_SECTIONS = FIXTURES / "design_missing_sections.md"
EMPTY_CONCLUSIONS = FIXTURES / "design_empty_conclusions.md"
PLACEHOLDER = FIXTURES / "design_placeholder.md"
HEADINGS_ONLY = FIXTURES / "design_headings_only.md"

_COVERAGE_RE = re.compile(r"六层必答问题覆盖:\s*(\d+)/(\d+)")


def _coverage(proc) -> tuple[int, int]:
    m = _COVERAGE_RE.search(proc.stdout)
    is_true(m is not None, f"输出中未找到「六层必答问题覆盖: X/43」行\n{proc.stdout}")
    return int(m.group(1)), int(m.group(2))


def test_complete_doc_exit_zero():
    proc = run(CHECK_DOC, [FULL])
    exit_code(proc, 0, "完整设计文档应通过")
    contains(proc.stdout, "结论: 结构完整", "完整文档结论")
    contains(proc.stdout, "章节齐全度: 15/15", "完整文档章节齐全度")


def test_missing_sections_exit_one():
    proc = run(CHECK_DOC, [MISSING_SECTIONS])
    exit_code(proc, 1, "缺章节应默认返回 1")
    contains(proc.stdout, "缺章节", "缺章节提示")
    contains(proc.stdout, "结论: 存在缺失项", "缺章节结论行")


def test_empty_conclusions_exit_one():
    proc = run(CHECK_DOC, [EMPTY_CONCLUSIONS])
    exit_code(proc, 1, "§13 结论列空应返回 1")
    contains(proc.stdout, "§13 必答项结论空缺: 8 处", "§13 空缺计数")
    contains(proc.stdout, "第 1 项", "§13 第 1 项应被点名")


def test_placeholder_detected_exit_one():
    proc = run(CHECK_DOC, [PLACEHOLDER])
    exit_code(proc, 1, "存在未填占位符应返回 1")
    contains(proc.stdout, "未填占位符 <...>: 有", "占位符提示")
    contains(proc.stdout, "<待填>", "具体占位符应被列出")


def test_lenient_returns_zero():
    proc = run(CHECK_DOC, [MISSING_SECTIONS, "--lenient"])
    exit_code(proc, 0, "--lenient 应放行（返回 0）")
    contains(proc.stdout, "--lenient", "宽松模式说明行")
    contains(proc.stdout, "结论: 存在缺失项", "宽松模式仍需打印问题结论")


def test_strict_flag_backward_compatible():
    """旧调用方传 --strict 时期望"有问题→1"，默认严格后仍满足。"""
    proc = run(CHECK_DOC, [MISSING_SECTIONS, "--strict"])
    exit_code(proc, 1, "--strict 向后兼容：有问题仍返回 1")
    proc_ok = run(CHECK_DOC, [FULL, "--strict"])
    exit_code(proc_ok, 0, "--strict 下完整文档仍返回 0")


def test_43q_positive_full_coverage():
    proc = run(CHECK_DOC, [FULL])
    covered, total = _coverage(proc)
    eq(total, 43, "43 问总数")
    eq(covered, 43, "正样本应 43/43 覆盖")
    exit_code(proc, 0, "43 问全覆盖文档应通过")


def test_43q_negative_headings_only():
    """标题齐全但六层问题全缺 —— 修复前的假绿场景，必须返回 1。"""
    proc = run(CHECK_DOC, [HEADINGS_ONLY])
    exit_code(proc, 1, "43 问大面积缺失应返回 1")
    covered, total = _coverage(proc)
    eq(total, 43, "43 问总数")
    is_true(covered <= 15, f"负样本覆盖数应显著低于 43，实际 {covered}/43")
    contains(proc.stdout, "未覆盖:", "应列出未覆盖问题清单")


def test_43q_gate_is_additive_not_replacing():
    """43 问检查是叠加项：原有检查（台账 / 占位符 / §13）仍在工作。"""
    proc = run(CHECK_DOC, [HEADINGS_ONLY])
    contains(proc.stdout, "设计台账行: 有", "台账检查仍执行")
    contains(proc.stdout, "§13 必答项结论空缺: 无", "§13 检查仍执行")
    contains(proc.stdout, "生产级必答项: 9/9", "必答项检查仍执行")


def test_missing_file_is_error():
    ws = Workspace()
    try:
        proc = run(CHECK_DOC, [ws.path / "nope.md"])
        exit_code(proc, 1, "不存在的文档应报错退出 1")
        contains(proc.stderr + proc.stdout, "文件不存在", "文件不存在提示")
    finally:
        ws.cleanup()
