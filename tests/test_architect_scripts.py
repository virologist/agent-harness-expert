"""agent-harness-architect 另外三个脚本的冒烟测试。

resolve_paths.py / knowledge_lib.py / render_questionnaire.py
"""
from __future__ import annotations

import os
from pathlib import Path

from _harness import (
    ARCH_SCRIPTS,
    KNOWLEDGE_LIB,
    RENDER_Q,
    RESOLVE_PATHS,
    Workspace,
    contains,
    eq,
    exit_code,
    is_true,
    run,
)

ENTRY_HARNESS = """---
name: 测试框架
alias: 测试
type: harness
source: 测试来源
added: 2026-10-15
version: v1
confidence: 低
pinned: false
---

# 测试框架
"""


def _ext_env(ws: Workspace) -> dict:
    """把外部进化库重定向到 tmp，避免写 $HOME/.workbuddy。"""
    return {"WORKBUDDY_CONFIG_DIR": str(ws.path / "cfg")}


# ---------------------------------------------------------------------------
# resolve_paths.py
# ---------------------------------------------------------------------------

def test_resolve_paths_default_exit_zero():
    proc = run(RESOLVE_PATHS)
    exit_code(proc, 0, "resolve_paths 默认应成功定位")
    expect = str(ARCH_SCRIPTS.parent)
    contains(proc.stdout, f"SKILL_DIR={expect}", "SKILL_DIR 应由 __file__ 反推到包内")
    contains(proc.stdout, "EXT_DIR=", "EXT_DIR 应输出")


def test_resolve_paths_env_injection_wins():
    ws = Workspace()
    try:
        ws.write("SKILL.md", "# fake skill\n")
        # 脚本内部对两个路径都做 .resolve()，比较前先归一（macOS 上 /var → /private/var）
        ws_resolved = ws.path.resolve()
        proc = run(RESOLVE_PATHS, env={"SKILL_DIR": str(ws.path),
                                       "WORKBUDDY_CONFIG_DIR": str(ws.path / "cfg")})
        exit_code(proc, 0, "env 注入命中应返回 0")
        contains(proc.stdout, f"SKILL_DIR={ws_resolved}", "env 注入值应优先")
        contains(proc.stdout, f"EXT_DIR={ws_resolved / 'cfg' / 'agent-harness-knowledge'}",
                 "EXT_DIR 应跟随 WORKBUDDY_CONFIG_DIR")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# knowledge_lib.py
# ---------------------------------------------------------------------------

def test_knowledge_lib_status_exit_zero():
    ws = Workspace()
    try:
        proc = run(KNOWLEDGE_LIB, ["status"], env=_ext_env(ws))
        exit_code(proc, 0, "status 子命令应返回 0")
        contains(proc.stdout, "包内知识库（只读）", "应报告包内知识库")
        contains(proc.stdout, "外部进化库（可写）", "应报告外部进化库")
        contains(proc.stdout, "未初始化", "外部库未初始化时应提示")
    finally:
        ws.cleanup()


def test_knowledge_lib_init_and_ingest():
    ws = Workspace()
    try:
        env = _ext_env(ws)
        proc = run(KNOWLEDGE_LIB, ["init"], env=env)
        exit_code(proc, 0, "init 应返回 0")
        is_true((ws.path / "cfg" / "agent-harness-knowledge" / "index.md").is_file(),
                "init 应复制出外部 index.md")

        src = ws.write("entry.md", ENTRY_HARNESS)
        proc = run(KNOWLEDGE_LIB, ["ingest", src, "--row", "| 测试框架 | harness | 测试 |"], env=env)
        exit_code(proc, 0, "ingest 应返回 0")
        dest = ws.path / "cfg" / "agent-harness-knowledge" / "frameworks" / "core" / "entry.md"
        is_true(dest.is_file(), f"ingest 应按 type:harness 路由到 frameworks/core，实际未找到 {dest}")
        contains(proc.stdout, "已追加索引行", "ingest --row 应追加索引行")
        contains(ws.read("cfg/agent-harness-knowledge/index.md"), "| 测试框架 | harness | 测试 |",
                 "索引行应真的写进 index.md")
    finally:
        ws.cleanup()


def test_knowledge_lib_ingest_rejects_dirty_row():
    ws = Workspace()
    try:
        src = ws.write("entry.md", ENTRY_HARNESS)
        proc = run(KNOWLEDGE_LIB, ["ingest", src, "--row", "这不是表格行"], env=_ext_env(ws))
        exit_code(proc, 1, "脏索引行应被拒绝（退出码 1）")
        contains(proc.stderr + proc.stdout, "索引行不合格", "应给出不合格原因")
    finally:
        ws.cleanup()


def test_knowledge_lib_promote_dry_run():
    ws = Workspace()
    try:
        src = ws.write("entry.md", ENTRY_HARNESS)
        proc = run(KNOWLEDGE_LIB, ["promote", src], env=_ext_env(ws))
        exit_code(proc, 0, "promote 默认 dry-run 应返回 0")
        contains(proc.stdout, "[dry-run]", "未加 --apply 应只打印计划")
    finally:
        ws.cleanup()


def test_knowledge_lib_missing_file_is_error():
    ws = Workspace()
    try:
        proc = run(KNOWLEDGE_LIB, ["ingest", ws.path / "nope.md"], env=_ext_env(ws))
        exit_code(proc, 1, "ingest 不存在文件应返回 1")
        contains(proc.stderr + proc.stdout, "文件不存在", "应提示文件不存在")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# P1-5：ingest 挂 lint + 查重 + 路径常量统一
# ---------------------------------------------------------------------------

def test_knowledge_lib_ingest_duplicate_rejected_by_default():
    """同名不传 --force 应被拒绝（默认拒绝而非默认覆盖）。"""
    ws = Workspace()
    try:
        env = _ext_env(ws)
        src = ws.write("entry.md", ENTRY_HARNESS)
        proc = run(KNOWLEDGE_LIB, ["ingest", src], env=env)
        exit_code(proc, 0, "首次 ingest 应通过")
        proc = run(KNOWLEDGE_LIB, ["ingest", src], env=env)
        exit_code(proc, 1, "同名二次 ingest 默认应被拒绝")
        contains(proc.stdout, "条目已存在", "应明示条目已存在")
        contains(proc.stdout, "--force", "应提示 --force 强制覆盖")
    finally:
        ws.cleanup()


def test_knowledge_lib_ingest_force_overwrites():
    """传 --force 应允许覆盖已存在的条目。"""
    ws = Workspace()
    try:
        env = _ext_env(ws)
        src = ws.write("entry.md", ENTRY_HARNESS)
        proc = run(KNOWLEDGE_LIB, ["ingest", src], env=env)
        exit_code(proc, 0, "首次 ingest 应通过")
        # 改源文件内容，强制覆盖应写入新内容
        new_text = ENTRY_HARNESS.replace("# 测试框架", "# 测试框架_已覆盖")
        src.write_text(new_text, encoding="utf-8")
        proc = run(KNOWLEDGE_LIB, ["ingest", src, "--force"], env=env)
        exit_code(proc, 0, "--force 应允许覆盖")
        contains(proc.stdout, "已收录", "覆盖后应打印已收录")
        dest = ws.path / "cfg" / "agent-harness-knowledge" / "frameworks" / "core" / "entry.md"
        contains(dest.read_text(encoding="utf-8"), "测试框架_已覆盖",
                 "确认目标文件已被覆盖为新内容")
    finally:
        ws.cleanup()


def test_knowledge_lib_ingest_lint_rejects_bad_entry():
    """lint 失败的不合格条目应被拒绝收录（不调入）。"""
    ws = Workspace()
    try:
        # 故意去掉必填的 pinned（framework frontmatter 必填字段）
        bad = ENTRY_HARNESS.replace("pinned: false\n", "")
        src = ws.write("bad.md", bad)
        proc = run(KNOWLEDGE_LIB, ["ingest", src], env=_ext_env(ws))
        exit_code(proc, 1, "lint 失败的条目应拒绝收录")
        contains(proc.stdout, "LINT FAIL", "应明示 lint 失败")
        contains(proc.stdout, "pinned", "应点名缺失的字段")
        # 验证目标文件未创建（不调入）
        ext = ws.path / "cfg" / "agent-harness-knowledge"
        is_true(not (ext / "frameworks" / "core" / "bad.md").exists(),
                "lint 拒绝的条目不应落到外部库")
    finally:
        ws.cleanup()


def test_knowledge_lib_uses_resolve_paths_knowledge_dirname():
    """ext_dir() 应跟随 resolve_paths.py 的 KNOWLEDGE_DIRNAME 常量（路径统一）。"""
    ws = Workspace()
    try:
        env = _ext_env(ws)
        proc = run(KNOWLEDGE_LIB, ["status"], env=env)
        exit_code(proc, 0, "status 应返回 0")
        # 抓"外部进化库（可写）:"行做路径归一比较（macOS /tmp vs /private/tmp）
        ext_line = [ln for ln in proc.stdout.splitlines() if "外部进化库（可写）:" in ln][0]
        kb_ext = ext_line.split("外部进化库（可写）:", 1)[1].strip()
        rp_proc = run(RESOLVE_PATHS, env=env)
        exit_code(rp_proc, 0, "resolve_paths 应返回 0")
        rp_ext_line = [ln for ln in rp_proc.stdout.splitlines() if ln.startswith("EXT_DIR=")][0]
        rp_ext = rp_ext_line.split("=", 1)[1]
        # 用 realpath 归一再比较，避开 macOS /tmp vs /private/tmp 分叉
        is_true(os.path.realpath(kb_ext) == os.path.realpath(rp_ext),
                f"knowledge_lib 报出的 ext ({kb_ext}) 应与 resolve_paths 的 EXT_DIR ({rp_ext}) 一致")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# render_questionnaire.py
# ---------------------------------------------------------------------------

def test_render_selected_dims():
    proc = run(RENDER_Q, ["--dims", "goal,success", "--project", "支付助手"])
    exit_code(proc, 0, "渲染指定维度应返回 0")
    contains(proc.stdout, "# 支付助手 需求澄清问卷", "标题应带项目名")
    contains(proc.stdout, "### Q1. 目标与用途", "第一问应为 goal")
    contains(proc.stdout, "### Q2. 成功标准", "第二问应为 success")
    eq(proc.stdout.count("### Q"), 2, "只应渲染 2 个维度")


def test_render_all_dims_count():
    proc = run(RENDER_Q, ["--all"])
    exit_code(proc, 0, "--all 应返回 0")
    eq(proc.stdout.count("### Q"), 11, "--all 应渲染 11 个维度")


def test_render_unknown_dim_is_error():
    proc = run(RENDER_Q, ["--dims", "goal,not-a-dim"])
    exit_code(proc, 1, "未知维度应报错退出 1")
    contains(proc.stderr + proc.stdout, "未知维度", "应提示未知维度")


def test_render_requires_dims_or_all():
    proc = run(RENDER_Q)
    eq(proc.returncode, 2, "既无 --dims 也无 --all 应是 argparse 用法错误（退出码 2）")


def test_render_writes_out_file():
    ws = Workspace()
    try:
        out = ws.path / "sub" / "q.md"
        proc = run(RENDER_Q, ["--dims", "oracle", "--out", out])
        exit_code(proc, 0, "--out 应返回 0")
        is_true(out.is_file(), "--out 应写出文件（含自动建父目录）")
        contains(out.read_text(encoding="utf-8"), "验收来源（oracle）", "写出内容应含指定维度")
    finally:
        ws.cleanup()
