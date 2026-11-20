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


def _assert_initial_state_schema(state: dict, what: str) -> None:
    """断言 _state.json 符合 references/_state_schema.md v1 的全部必填字段口径。"""
    required = ("project", "current_stage", "completed_stages",
                "last_run_at", "per_stage_artifacts", "open_items")
    missing = [k for k in required if k not in state]
    is_true(not missing, f"{what}: _state.json 缺必填字段 {missing}")
    is_true(isinstance(state["project"], str) and state["project"] != "",
            f"{what}: project 应为非空字符串")
    eq(state["current_stage"], "P0", f"{what}: 初始 current_stage 应为 P0")
    eq(state["completed_stages"], [], f"{what}: 初始 completed_stages 应为空")
    eq(state["per_stage_artifacts"], {}, f"{what}: 初始 per_stage_artifacts 应为空字典")
    eq(state["open_items"], [], f"{what}: 初始 open_items 应为空列表")
    ts = state["last_run_at"]
    is_true(isinstance(ts, str) and len(ts) == 20 and "T" in ts and ts.endswith("Z"),
            f"{what}: last_run_at 应为秒精度 Z 后缀 UTC ISO 8601，实际 {ts!r}")


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
        # _state.json 必须符合 _state_schema.md v1（完整必填字段，state_io 可直接消费）
        state = json.loads(ws.read(".harness-kb/_state.json"))
        _assert_initial_state_schema(state, "首次创建")
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

        # --force 时重建模板文件，但 F-07：绝不覆盖 _state.json（撞限续跑核心）
        forced = _run_init(ws, ["--force"])
        exit_code(forced, 0, "--force 应返回 0")
        forced_data = json_out(forced, "--force 输出")
        eq(forced_data["created"], ["learnings.md", "mode2-log.md"],
           "--force 应重建两个模板文件，但不含 _state.json")
        eq("_state.json" in forced_data["preserved"], True,
           "F-07：--force 必须 preserve _state.json，不得重置断点")
        eq(forced_data["force"], True, "force 字段应标注 True")
        # 重建后模板内容应回到样板（不是原 marker），但 _state.json 原样保留
        contains(ws.read(".harness-kb/learnings.md"), "Pattern-Key 跟踪表",
                 "--force 后 learnings.md 应回到模板")
        eq(ws.read(".harness-kb/_state.json"), json.dumps(state_marker, ensure_ascii=False),
           "F-07：--force 后用户 _state.json（含 P2 进度）必须原样保留")
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
        # _state.json 必须能 json.loads 且符合 v1 完整 schema
        state_text = ws.read(".harness-kb/_state.json")
        try:
            state = json.loads(state_text)
        except json.JSONDecodeError as e:
            raise AssertionError(f"_state.json 不是合法 JSON: {e}\n---- 内容 ----\n{state_text}")
        _assert_initial_state_schema(state, "四个产物布局")
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


def test_init_state_consumable_by_state_io():
    """端到端回归：kb_init 产物必须能被 state_io.read_state → update_stage → write_state 闭环消费。

    回归锚点（P0 断裂）：旧版 _state.json 写 {stage, last_updated}，update_stage
    读到后 KeyError 'completed_stages'，SOP 第一动作「按 current_stage 续跑」完全失效。
    """
    ws = Workspace()
    try:
        proj = ws.path / "e2eproj"
        proj.mkdir(parents=True, exist_ok=True)
        scripts = HARNESS_KB_INIT.parent.parent / "skills" / "coding-prompt" / "scripts"

        # 1) 真实执行 init CLI（项目根 = e2eproj）
        proc = run(HARNESS_KB_INIT, [str(proj)])
        exit_code(proc, 0, "init 应返回 0")
        eq(json_out(proc, "init 输出")["status"], "ok", "init 状态应为 ok")

        # 2) read_state 断言全部必填字段存在且 current_stage == P0；
        # 3) update_stage(P1) 不抛错、completed_stages==['P1']、current_stage 推进到 P2
        code = (
            "from state_io import read_state, update_stage, REQUIRED_KEYS\n"
            f"proj = {str(proj)!r}\n"
            "s = read_state(proj)\n"
            "assert s is not None, 'read_state 不应返回 None'\n"
            "missing = [k for k in REQUIRED_KEYS if k not in s]\n"
            "assert not missing, f'缺必填字段: {missing}'\n"
            "assert s['project'] == 'e2eproj', s\n"
            "assert s['current_stage'] == 'P0', s\n"
            "assert s['completed_stages'] == [], s\n"
            "assert s['per_stage_artifacts'] == {}, s\n"
            "assert s['open_items'] == [], s\n"
            "assert s['last_run_at'].endswith('Z') and 'T' in s['last_run_at'], s\n"
            "print('SCHEMA_OK')\n"
            "out = update_stage(proj, 'P1')\n"
            "assert out['completed_stages'] == ['P1'], out\n"
            "assert out['current_stage'] == 'P2', out\n"
            "disk = read_state(proj)\n"
            "assert disk is not None and disk['current_stage'] == 'P2', disk\n"
            "assert disk['completed_stages'] == ['P1'], disk\n"
            "print('E2E_OK')\n"
        )
        proc2 = run_python(code, cwd=str(ws.path), syspath=[scripts])
        exit_code(proc2, 0, "read_state → update_stage → write_state 闭环不应抛错")
        contains(proc2.stdout, "SCHEMA_OK", "read_state 应读到完整 schema 初始 state")
        contains(proc2.stdout, "E2E_OK", "update_stage(P1) 应不抛错并推进状态")
    finally:
        ws.cleanup()


def test_force_never_resets_state_but_reset_state_backs_up():
    """F-07：--force 不清空断点；--reset-state 才重置且覆盖前备份 .bak。"""
    ws = Workspace()
    try:
        # 首次 init + 用 state_io 推进到 P3（模拟撞限续跑进度）
        _run_init(ws)
        kb = ws.path / ".harness-kb"
        scripts = HARNESS_KB_INIT.parent.parent / "skills" / "coding-prompt" / "scripts"
        code = (
            "from state_io import update_stage\n"
            f"p = {str(ws.path)!r}\n"
            "update_stage(p, 'P0'); update_stage(p, 'P1'); update_stage(p, 'P2')\n"
        )
        proc = run_python(code, cwd=str(ws.path), syspath=[scripts])
        exit_code(proc, 0, "推进 state 到 P3 应成功")
        advanced = json.loads((kb / "_state.json").read_text(encoding="utf-8"))
        eq(advanced["current_stage"], "P3", "前置：进度应推进到 P3")
        eq(advanced["completed_stages"], ["P0", "P1", "P2"], "前置：应完成三个阶段")

        # --force 不得重置
        forced = _run_init(ws, ["--force"])
        exit_code(forced, 0, "--force 应成功")
        after_force = json.loads((kb / "_state.json").read_text(encoding="utf-8"))
        eq(after_force, advanced, "F-07：--force 后 _state.json 必须与推进前逐字段一致")
        is_true(not (kb / "_state.json.bak").exists(), "--force 不应产生 .bak")

        # --reset-state 才重置，且先备份
        reset = _run_init(ws, ["--reset-state"])
        exit_code(reset, 0, "--reset-state 应成功")
        data = json_out(reset, "--reset-state 输出")
        eq(data["reset_state"], True, "应标注 reset_state=True")
        is_true(data["state_backup"] and data["state_backup"].endswith("_state.json.bak"),
                "应返回 .bak 备份路径")
        backup = json.loads((kb / "_state.json.bak").read_text(encoding="utf-8"))
        eq(backup, advanced, ".bak 应含重置前的 P3 进度（覆盖前备份）")
        reset_state = json.loads((kb / "_state.json").read_text(encoding="utf-8"))
        eq(reset_state["current_stage"], "P0", "--reset-state 后应回到 P0")
        eq(reset_state["completed_stages"], [], "--reset-state 后 completed 应清空")
    finally:
        ws.cleanup()


def test_atomic_write_text_leaves_no_tmp():
    """F-09：_harness_kb_init 的原子写 helper 应完整覆盖且不留 .tmp 残局。"""
    ws = Workspace()
    try:
        init_dir = HARNESS_KB_INIT.parent
        target = ws.path / "data.json"
        target.write_text('{"old": 1}', encoding="utf-8")
        code = (
            "from pathlib import Path\n"
            f"import sys; sys.path.insert(0, {str(init_dir)!r})\n"
            "import _harness_kb_init as M\n"
            f"p = Path({str(target)!r})\n"
            "M.atomic_write_text(p, '{\"new\": 2}')\n"
            "print('OK')\n"
        )
        proc = run_python(code, cwd=ws.path, syspath=[init_dir])
        exit_code(proc, 0, "atomic_write_text 应成功")
        contains(proc.stdout, "OK", "原子写应执行成功")
        eq(json.loads(target.read_text(encoding="utf-8")), {"new": 2},
           "应完整覆盖旧内容")
        eq(list(ws.path.glob("data.json.*.tmp")), [], "不得留 .tmp 残局")
    finally:
        ws.cleanup()
