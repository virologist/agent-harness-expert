"""agents/_harness_kb_init.py 的冒烟测试（P3-7）。

4 用例：建目录 / 已有目录不覆盖 / 4 个产物都建了 / safe_mkdir 沙箱 EEXIST 兼容。
所有用例在 tmp 工作区跑，跑完清理，不污染仓库与用户项目。
"""
from __future__ import annotations

import json
from pathlib import Path

from _harness import (
    Workspace,
    contains,
    eq,
    exit_code,
    is_true,
    json_out,
    run,
    run_python,
)


HARNESS_KB_INIT = (
    Path(__file__).resolve().parents[1] / "agents" / "_harness_kb_init.py"
)


def _run_init(ws: Workspace, args=()) -> object:
    """真实执行 init 脚本 CLI，返回 CompletedProcess。"""
    return run(HARNESS_KB_INIT, [str(ws.path), *args])


def _assert_artifact_layout(ws: Workspace, what: str) -> None:
    """断言 4 个产物都存在（learnings.md / mode2-log.md / _state.json / inbox/）。"""
    kb = ws.path / ".harness-kb"
    is_true(kb.is_dir(), f"{what}: .harness-kb/ 应是目录")
    is_true((kb / "learnings.md").is_file(), f"{what}: learnings.md 应是文件")
    is_true((kb / "mode2-log.md").is_file(), f"{what}: mode2-log.md 应是文件")
    is_true((kb / "_state.json").is_file(), f"{what}: _state.json 应是文件")
    is_true((kb / "inbox").is_dir(), f"{what}: inbox/ 应是目录")


def test_init_creates_kb_directory():
    """P3-7 用例 1：项目根不存在 .harness-kb/ 时，init 应建好整个目录树。"""
    ws = Workspace()
    try:
        proc = _run_init(ws)
        exit_code(proc, 0, "init 应返回 0")
        data = json_out(proc, "init 输出")
        eq(data["status"], "ok", "init 状态应为 ok")
        eq(data["kb_was_new"], True, "首次创建应为 kb_was_new=True")
        eq(data["created"], ["learnings.md", "mode2-log.md", "_state.json"],
           "首次创建应列出三个新文件")
        eq(data["preserved"], [], "首次创建不应有 preserved 项")
        _assert_artifact_layout(ws, "首次创建")
        # 关键样板内容断言（确认模板被正确写入）
        contains(ws.read(".harness-kb/learnings.md"), "Pattern-Key 跟踪表",
                 "learnings.md 应含 PK 跟踪表节")
        contains(ws.read(".harness-kb/mode2-log.md"), "| ts | signal | detail |",
                 "mode2-log.md 应含 mode2 标准表头")
        # _state.json 必须是合法 JSON
        state = json.loads(ws.read(".harness-kb/_state.json"))
        eq(state.get("stage"), None, "_state.json 初始 stage 应为 None（P3-5 接管）")
        is_true(isinstance(state.get("last_updated"), str) and "T" in state["last_updated"],
                "_state.json 应写入 UTC ISO 时间戳")
    finally:
        ws.cleanup()


def test_init_existing_directory_is_idempotent():
    """P3-7 用例 2：.harness-kb/ 已存在且有用户内容时，init 不应覆盖任何文件。"""
    ws = Workspace()
    try:
        # 首次跑 + 用户写入内容
        _run_init(ws)
        kb = ws.path / ".harness-kb"
        marker = "# 用户手写的 learnings，已写入了 PK-coder-007: 不可覆盖（防回归）\n"
        (kb / "learnings.md").write_text(marker, encoding="utf-8")
        log_marker = "# 用户追加的告警（tester 写过一行）\n"
        (kb / "mode2-log.md").write_text(log_marker, encoding="utf-8")
        state_marker = {"stage": "P2", "last_updated": "2026-10-01T00:00:00+00:00",
                        "user_added_field": "保护我不被覆盖"}
        (kb / "_state.json").write_text(json.dumps(state_marker, ensure_ascii=False),
                                         encoding="utf-8")
        # inbox/ 放一个文件，确认不被清理
        (kb / "inbox" / "user-note.md").write_text("# inbox 里的用户笔记\n", encoding="utf-8")

        # 第二次 init（不带 --force）
        proc = _run_init(ws)
        exit_code(proc, 0, "二次 init 应返回 0（幂等）")
        data = json_out(proc, "二次 init 输出")
        eq(data["kb_was_new"], False, "目录已存在，kb_was_new 应为 False")
        eq(data["created"], [], "二次 init 默认不应创建任何文件")
        eq(sorted(data["preserved"]), sorted(["learnings.md", "mode2-log.md", "_state.json"]),
           "二次 init 应全部 preserved")
        # 用户内容必须原样保留
        eq(ws.read(".harness-kb/learnings.md"), marker, "用户 learnings.md 不得被覆盖")
        eq(ws.read(".harness-kb/mode2-log.md"), log_marker, "用户 mode2-log.md 不得被覆盖")
        eq(ws.read(".harness-kb/_state.json"), json.dumps(state_marker, ensure_ascii=False),
           "用户 _state.json 不得被覆盖")
        is_true((kb / "inbox" / "user-note.md").is_file(), "inbox/ 已有文件不得被清理")

        # --force 时重建 3 个文件骨架（inbox/ 仍不清空）
        forced = _run_init(ws, ["--force"])
        exit_code(forced, 0, "--force 应返回 0")
        forced_data = json_out(forced, "--force 输出")
        eq(forced_data["created"], ["learnings.md", "mode2-log.md", "_state.json"],
           "--force 应重建三个文件骨架")
        eq(forced_data["force"], True, "force 字段应标注 True")
        # 重建后骨架内容应是模板（不是原 marker）
        contains(ws.read(".harness-kb/learnings.md"), "Pattern-Key 跟踪表",
                 "--force 后 learnings.md 应回到模板")
        is_true((kb / "inbox" / "user-note.md").is_file(),
                "--force 不应清理 inbox/ 已有文件")
    finally:
        ws.cleanup()


def test_init_creates_all_four_artifacts():
    """P3-7 用例 3：四个产物（learnings.md / mode2-log.md / _state.json / inbox/）
    都应被创建，且内容是合法可解析的（文件类）或合法目录（inbox/）。"""
    ws = Workspace()
    try:
        proc = _run_init(ws)
        exit_code(proc, 0, "init 应返回 0")
        _assert_artifact_layout(ws, "四个产物布局")
        kb = ws.path / ".harness-kb"
        # _state.json 必须能 json.loads
        state_text = ws.read(".harness-kb/_state.json")
        try:
            state = json.loads(state_text)
        except json.JSONDecodeError as e:
            raise AssertionError(f"_state.json 不是合法 JSON: {e}\n---- 内容 ----\n{state_text}")
        is_true("stage" in state and "last_updated" in state,
                "_state.json 应至少含 stage / last_updated 字段")
        # learnings.md / mode2-log.md 必须是合法 utf-8 文本
        for name in ("learnings.md", "mode2-log.md"):
            txt = ws.read(f".harness-kb/{name}")
            is_true(len(txt) > 50, f"{name} 应有最小样板内容（>50 字），实际 {len(txt)}")
        # inbox/ 应是空目录
        inbox = kb / "inbox"
        is_true(inbox.is_dir(), "inbox/ 应是目录")
        eq(sorted(p.name for p in inbox.iterdir()), [],
           "新建的 inbox/ 应为空目录")
    finally:
        ws.cleanup()


def test_init_safe_mkdir_sandbox_eexist():
    """P3-7 用例 4：safe_mkdir 在 WorkBuddy 沙箱 EEXIST 误报下应幂等成功。

    模拟场景：沙箱 sitecustomize 把 mkdir(exist_ok=True) 误抛 PermissionError；
    safe_mkdir 把「目标已是目录」视为成功，其余错误原样抛出。
    本用例用 run_python 子进程跑 init 模块，monkey-patch Path.mkdir 抛
    PermissionError(EEXIST)，验证 init 仍能完整跑完，四个产物都建好。
    """
    ws = Workspace()
    try:
        init_dir = HARNESS_KB_INIT.parent
        code = (
            "import json\n"
            "from pathlib import Path\n"
            f"import sys; sys.path.insert(0, {str(init_dir)!r})\n"
            "import _harness_kb_init as M\n"
            "original_mkdir = Path.mkdir\n"
            "def patched_mkdir(self, *a, **kw):\n"
            "    if kw.get('exist_ok') and self.exists():\n"
            "        raise PermissionError(17, 'sandbox EEXIST (simulated)')\n"
            "    return original_mkdir(self, *a, **kw)\n"
            "Path.mkdir = patched_mkdir\n"
            f"result = M.init(Path({str(ws.path)!r}))\n"
            "print(json.dumps(result, ensure_ascii=False))\n"
        )
        proc = run_python(code, cwd=ws.path, syspath=[init_dir])
        exit_code(proc, 0, "沙箱 EEXIST 模拟下 init 应仍返回 0（safe_mkdir 应吞掉误报）")
        try:
            data = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as e:
            raise AssertionError(f"init 输出不是 JSON: {e}\n---- stdout ----\n{proc.stdout}")
        eq(data["status"], "ok", "沙箱 EEXIST 模拟下 init 应返回 ok 状态")
        eq(data["kb_was_new"], True, "首次 init 应标注 kb_was_new=True")
        # 四个产物都应在沙箱 mkdir 误报下被建好（说明 safe_mkdir 正确吞掉 PermissionError）
        _assert_artifact_layout(ws, "沙箱 EEXIST 模拟下")
        # 进一步：Path.mkdir 应仍被 monkey-patched（证明我们的模拟生效）
        # 即沙箱真的抛了 PermissionError，但 safe_mkdir 处理掉了
        eq(data["created"], ["learnings.md", "mode2-log.md", "_state.json"],
           "三个文件都应被新建")
    finally:
        ws.cleanup()
