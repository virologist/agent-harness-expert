"""冒烟测试公共夹具（纯标准库，零第三方依赖）。

约定：
  - 所有用例在 tmp 工作区里跑，跑完清理，不污染仓库与 $HOME。
  - **真实执行脚本、真实断言退出码与输出**，不做"文件存在"这类空断言。
  - 断言失败抛 AssertionError，由 run_tests.py 汇总；不允许为过测试放宽断言。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCH_SCRIPTS = REPO_ROOT / "skills" / "agent-harness-architect" / "scripts"
WIKI_SCRIPTS = REPO_ROOT / "skills" / "wiki-creator" / "scripts"
PKG_KNOWLEDGE = REPO_ROOT / "skills" / "agent-harness-architect" / "references" / "knowledge"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

PY = sys.executable

CHECK_DOC = ARCH_SCRIPTS / "check_design_doc.py"
LINT_KB = ARCH_SCRIPTS / "lint_knowledge.py"
KNOWLEDGE_LIB = ARCH_SCRIPTS / "knowledge_lib.py"
RESOLVE_PATHS = ARCH_SCRIPTS / "resolve_paths.py"
RENDER_Q = ARCH_SCRIPTS / "render_questionnaire.py"

WIKI_INIT = WIKI_SCRIPTS / "init_wiki.py"
WIKI_BUILD = WIKI_SCRIPTS / "build_index.py"
WIKI_LINT = WIKI_SCRIPTS / "lint.py"
WIKI_DIFF = WIKI_SCRIPTS / "diff.py"
WIKI_PARSE = WIKI_SCRIPTS / "parse_raw.py"


class Workspace:
    """tmp 工作区：用完必须 cleanup()。"""

    def __init__(self, prefix: str = "ahe-test-"):
        self.path = Path(tempfile.mkdtemp(prefix=prefix))

    def write(self, rel: str, content: str) -> Path:
        p = self.path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text(encoding="utf-8")

    def exists(self, rel: str) -> bool:
        return (self.path / rel).exists()

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.cleanup()


def run(script: Path, args=(), cwd=None, env=None) -> subprocess.CompletedProcess:
    """真实执行脚本，返回 CompletedProcess（stdout/stderr 已解码）。"""
    cmd = [PY, str(script), *(str(a) for a in args)]
    e = os.environ.copy()
    if env:
        e.update({k: str(v) for k, v in env.items()})
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=e,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_python(code: str, cwd=None, env=None, syspath=()) -> subprocess.CompletedProcess:
    """执行一段内联 python（用于测不可直接 CLI 调用的模块，如 _root.py / _common.py）。"""
    e = os.environ.copy()
    if env:
        e.update({k: str(v) for k, v in env.items()})
    paths = [str(p) for p in syspath]
    prefix = "import sys\n" + "".join(f"sys.path.insert(0, {p!r})\n" for p in paths)
    return subprocess.run(
        [PY, "-c", prefix + code],
        cwd=str(cwd) if cwd else None,
        env=e,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# ---------------------------------------------------------------------------
# 断言（失败即抛 AssertionError，绝不静默通过）
# ---------------------------------------------------------------------------

def eq(actual, expected, what: str) -> None:
    if actual != expected:
        raise AssertionError(f"{what}: 期望 {expected!r}，实际 {actual!r}")


def contains(text: str, needle: str, what: str) -> None:
    if needle not in text:
        raise AssertionError(f"{what}: 输出中未找到 {needle!r}\n---- 实际输出 ----\n{text}")


def not_contains(text: str, needle: str, what: str) -> None:
    if needle in text:
        raise AssertionError(f"{what}: 输出中不期望出现 {needle!r}\n---- 实际输出 ----\n{text}")


def is_true(cond, what: str) -> None:
    if not cond:
        raise AssertionError(what)


def exit_code(proc: subprocess.CompletedProcess, expected: int, what: str) -> None:
    if proc.returncode != expected:
        raise AssertionError(
            f"{what}: 期望退出码 {expected}，实际 {proc.returncode}\n"
            f"---- stdout ----\n{proc.stdout}\n---- stderr ----\n{proc.stderr}"
        )


def json_out(proc: subprocess.CompletedProcess, what: str) -> dict:
    """解析脚本 stdout 里的 JSON（脚本输出可能前后夹杂提示行时取第一个 {...} 块）。"""
    text = proc.stdout.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise AssertionError(f"{what}: 输出不是 JSON\n---- stdout ----\n{proc.stdout}")
        return json.loads(text[start:end + 1])


# ---------------------------------------------------------------------------
# wiki 夹具
# ---------------------------------------------------------------------------

SCHEMA_FIXTURE = """---
schema_version: v1
---

# Wiki 知识库约束配置

## 主题清单

| slug | 名称 | 简述 |
|------|------|------|
| llm-basics | 大模型基础 | 基础概念与方法 |

## 实体类型清单

- 概念
- 方法
- 模型
"""

PAGE_FIXTURE = """---
title: {title}
topic: llm-basics
entity_type: {entity_type}
aliases: [{aliases}]
sources: [raw/a.md]
schema_version: v1
---

# {title}

## 摘要

{title} 的简要说明。

## 关键论点

- 论点一，原文见 raw/a.md §1
- 论点二，原文见 raw/a.md §2

## 证据 / 来源

- 出自 [[llm-basics/{link}]]；原文见 raw/a.md §1
"""


def build_wiki_page(title: str, entity_type: str = "概念", aliases: str = "", link: str = "") -> str:
    return PAGE_FIXTURE.format(
        title=title, entity_type=entity_type, aliases=aliases, link=link or "transformer"
    )
