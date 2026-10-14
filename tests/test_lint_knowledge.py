"""lint_knowledge.py 冒烟测试（默认严格 + --lenient + 三类条目校验）。"""
from __future__ import annotations

from _harness import (
    LINT_KB,
    PKG_KNOWLEDGE,
    Workspace,
    contains,
    exit_code,
    run,
)

FRAMEWORK_OK = """---
name: 示例框架
alias: 示例
type: harness
source: 官方文档（核实 2026-10-15）
added: 2026-10-15
version: v1
confidence: 中
pinned: true
---

# 示例框架

正文。
"""

MODEL_OK = """---
name: 示例模型
alias: 示例
type: model
category: 通用
source: 官方（核实 2026-10-15）
added: 2026-10-15
version: v1
confidence: 中
pinned: true
---

# 示例模型

## 一句话定位
定位。

## 接口形态
HTTP。

## 延迟
200ms。

## 已验证适用域
分诊。

## 已验证不适用域
长文生成。

## 降级策略
规则兜底。
"""


def test_package_knowledge_passes():
    """包内真实知识库（11 条目）应零问题、退出码 0。"""
    proc = run(LINT_KB, [PKG_KNOWLEDGE])
    exit_code(proc, 0, "包内知识库应通过")
    contains(proc.stdout, "0 个问题", "包内知识库问题数应为 0")


def test_framework_missing_frontmatter_field():
    ws = Workspace()
    try:
        bad = FRAMEWORK_OK.replace("pinned: true\n", "")
        ws.write("frameworks/core/bad.md", bad)
        proc = run(LINT_KB, [ws.path])
        exit_code(proc, 1, "缺 frontmatter 字段应默认返回 1")
        contains(proc.stdout, "frontmatter 缺字段: pinned", "应点名缺失字段")
    finally:
        ws.cleanup()


def test_model_missing_section():
    ws = Workspace()
    try:
        bad = MODEL_OK.replace("## 降级策略\n规则兜底。\n", "")
        ws.write("models/core/bad.md", bad)
        proc = run(LINT_KB, [ws.path])
        exit_code(proc, 1, "model 条目缺小节应返回 1")
        contains(proc.stdout, "缺小节「降级策略」", "应点名缺失小节")
    finally:
        ws.cleanup()


def test_lenient_returns_zero():
    ws = Workspace()
    try:
        ws.write("frameworks/core/bad.md", FRAMEWORK_OK.replace("pinned: true\n", ""))
        proc = run(LINT_KB, [ws.path, "--lenient"])
        exit_code(proc, 0, "--lenient 应放行")
        contains(proc.stdout, "--lenient", "宽松模式说明行")
        strict = run(LINT_KB, [ws.path, "--strict"])
        exit_code(strict, 1, "--strict 向后兼容：仍返回 1")
    finally:
        ws.cleanup()


def test_nonexistent_target_is_error():
    ws = Workspace()
    try:
        proc = run(LINT_KB, [ws.path / "nope"])
        exit_code(proc, 1, "目标路径不存在应返回 1")
        contains(proc.stderr + proc.stdout, "路径不存在", "路径不存在提示")
    finally:
        ws.cleanup()
