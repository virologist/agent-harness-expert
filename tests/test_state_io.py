"""state_io.py 冒烟测试（5 用例）：read/write/update/缺文件/safe_mkdir。

每个用例真实调用 state_io 的三个 API，在 tmp 工作区构造项目根，
跑完断言字段值与磁盘内容；不依赖 pytest，纯标准库。
"""
from __future__ import annotations

from _harness import Workspace, contains, eq, exit_code, run_python, is_true


STATE_IO_SCRIPTS = (
    __file__.rsplit("/tests/", 1)[0] + "/skills/coding-prompt/scripts"
)


def _import(ws_path: str, body: str):
    """在临时项目根上跑一段内联 Python，state_io 用 sys.path 注入。"""
    return run_python(
        body,
        syspath=[STATE_IO_SCRIPTS],
        cwd=ws_path,
    )


def test_read_state_missing_returns_none():
    """缺文件时 read_state 应返回 None（全新项目判定），不应抛 IOError。"""
    ws = Workspace()
    try:
        proc = _import(
            str(ws.path),
            "import sys; sys.path.insert(0, %r)\n"
            "from state_io import read_state\n"
            "r = read_state(%r)\n"
            "print('NONE' if r is None else f'GOT:{r}')\n" % (STATE_IO_SCRIPTS, str(ws.path)),
        )
        exit_code(proc, 0, "缺文件应静默返回 None")
        eq(proc.stdout.strip(), "NONE", "read_state 缺文件应输出 NONE")
    finally:
        ws.cleanup()


def test_write_state_creates_file_and_validates():
    """write_state 应创建 .harness-kb/_state.json + 通过字段校验。"""
    ws = Workspace()
    try:
        proj = ws.path / "myproj"
        # 先 write_state 一份合法 state
        proc = _import(
            str(ws.path),
            "import sys, json, pathlib; sys.path.insert(0, %r)\n"
            "from state_io import write_state\n"
            "state = {\n"
            "    'project': 'myproj',\n"
            "    'current_stage': 'P0',\n"
            "    'completed_stages': [],\n"
            "    'last_run_at': '2026-10-15T10:00:00Z',\n"
            "    'per_stage_artifacts': {},\n"
            "    'open_items': ['seed'],\n"
            "}\n"
            "write_state(%r, state)\n"
            "p = pathlib.Path(%r) / '.harness-kb' / '_state.json'\n"
            "print('OK' if p.is_file() else 'NOFILE')\n"
            "print('LOADED' if json.loads(p.read_text())['project'] == 'myproj' else 'BAD')\n"
            % (STATE_IO_SCRIPTS, str(proj), str(proj)),
        )
        exit_code(proc, 0, "合法 write_state 应成功")
        contains(proc.stdout, "OK", "_state.json 应已落盘")
        contains(proc.stdout, "LOADED", "落盘内容应可被 json.loads 反解为 myproj")

        # 校验:再 write 一份缺 current_stage 的 state 必须抛 ValueError，让 Python 退出码 = 1
        proc2 = _import(
            str(ws.path),
            "import sys; sys.path.insert(0, %r)\n"
            "from state_io import write_state\n"
            "write_state(%r, {'project': 'x'})\n"
            "print('ACCEPTED')\n"
            % (STATE_IO_SCRIPTS, str(proj)),
        )
        exit_code(proc2, 1, "缺必填字段应抛 ValueError,Python 退出码 1")
        contains(proc2.stderr, "current_stage", "错误信息应点名缺失字段")
        if "ACCEPTED" in proc2.stdout:
            raise AssertionError(
                f"缺字段必须被拒: stdout={proc2.stdout!r}, stderr={proc2.stderr!r}"
            )
    finally:
        ws.cleanup()


def test_update_stage_advances_state():
    """update_stage 应完成、记产出、推进 current_stage、刷时间。"""
    ws = Workspace()
    try:
        proj = ws.path / "trackme"
        proc = _import(
            str(ws.path),
            "import sys, json, pathlib; sys.path.insert(0, %r)\n"
            "from state_io import update_stage, read_state\n"
            "out = update_stage(%r, 'P1', '/tmp/trackme/02-design/design.md')\n"
            "s = read_state(%r)\n"
            "print('STAGE:' + s['current_stage'])\n"
            "print('DONE:' + ','.join(s['completed_stages']))\n"
            "print('ARTIFACT:' + s['per_stage_artifacts']['P1'])\n"
            "print('ITEMS:' + str(len(s['open_items'])))\n"
            "print('PROJ:' + s['project'])\n"
            "print('TIME:' + s['last_run_at'])\n"
            "print('RETURN_STAGE:' + out['current_stage'])\n"
            % (STATE_IO_SCRIPTS, str(proj), str(proj)),
        )
        exit_code(proc, 0, "update_stage 应成功")
        eq(proc.stdout.splitlines()[0], "STAGE:P2", "完成后 current_stage 应推进到 P2")
        contains(proc.stdout, "DONE:P1", "completed_stages 应为 [P1]（仅完成 P1 一次）")
        contains(proc.stdout, "ARTIFACT:/tmp/trackme/02-design/design.md",
                 "per_stage_artifacts[P1] 应记原样路径")
        contains(proc.stdout, "ITEMS:0", "default open_items 应为空 list")
        contains(proc.stdout, "PROJ:trackme", "project 应回填为项目 basename")
        contains(proc.stdout, "TIME:2026-", "last_run_at 必须是 ISO 8601")
        contains(proc.stdout, "RETURN_STAGE:P2", "返回值应与磁盘一致")

        # 推进到 P4 → 下一阶段应为 complete
        proc2 = _import(
            str(ws.path),
            "import sys; sys.path.insert(0, %r)\n"
            "from state_io import update_stage\n"
            "out = update_stage(%r, 'P4', '/tmp/trackme/deliver.md')\n"
            "print('FINAL:' + out['current_stage'])\n"
            % (STATE_IO_SCRIPTS, str(proj)),
        )
        exit_code(proc2, 0, "P4 后应能再 update")
        contains(proc2.stdout, "FINAL:complete", "P4 → complete 是终态推进")
    finally:
        ws.cleanup()


def test_safe_mkdir_idempotent_under_existing_dir():
    """safe_mkdir 在目录已存在时不抛（兼容 WorkBuddy 沙箱 EEXIST 误报）。"""
    ws = Workspace()
    try:
        d = ws.path / "a" / "b" / "c"
        proc = _import(
            str(ws.path),
            "import sys, pathlib; sys.path.insert(0, %r)\n"
            "from state_io import safe_mkdir\n"
            "p = pathlib.Path(%r)\n"
            "safe_mkdir(p, parents=True)\n"
            "safe_mkdir(p, parents=True)   # 二次调用必须幂等\n"
            "safe_mkdir(p, parents=True)   # 三次\n"
            "print('OK' if p.is_dir() else 'FAIL')\n"
            % (STATE_IO_SCRIPTS, str(d)),
        )
        exit_code(proc, 0, "重复 safe_mkdir 不应抛异常")
        eq(proc.stdout.strip(), "OK", "三次 safe_mkdir 后目录必须存在")
        is_true(d.is_dir(), "safe_mkdir 真实创建了目录")
    finally:
        ws.cleanup()


def test_invalid_stage_rejected_and_state_not_corrupted():
    """非法 stage 必拒 + 已合法落盘的状态不被破坏。"""
    ws = Workspace()
    try:
        proj = ws.path / "guard"
        # 先落一份合法 state
        proc_init = _import(
            str(ws.path),
            "import sys; sys.path.insert(0, %r)\n"
            "from state_io import write_state\n"
            "write_state(%r, {\n"
            "    'project': 'guard',\n"
            "    'current_stage': 'P0',\n"
            "    'completed_stages': [],\n"
            "    'last_run_at': '2026-10-15T10:00:00Z',\n"
            "    'per_stage_artifacts': {},\n"
            "    'open_items': [],\n"
            "})\n"
            "print('INIT')\n"
            % (STATE_IO_SCRIPTS, str(proj)),
        )
        exit_code(proc_init, 0, "init 应成功")

        # 用非法 stage 调 update_stage → ValueError 让 Python 进程退出码 = 1
        proc_bad = _import(
            str(ws.path),
            "import sys; sys.path.insert(0, %r)\n"
            "from state_io import update_stage\n"
            "update_stage(%r, 'P9')\n"   # 不 try/except，让 ValueError 透出
            "print('ACCEPTED')\n"
            % (STATE_IO_SCRIPTS, str(proj)),
        )
        exit_code(proc_bad, 1, "非法 stage 应抛 ValueError，Python 退出 1")
        contains(proc_bad.stderr, "P9", "错误信息应点名非法 stage 值")
        not_contains_marker = "ACCEPTED"
        if not_contains_marker in proc_bad.stdout:
            raise AssertionError(
                f"非法 stage 调用不应输出 {not_contains_marker!r}: stdout={proc_bad.stdout!r}"
            )

        # 复核磁盘上原 state 没被改动（注意路径是 proj，不是 ws.path）
        proc_check = _import(
            str(ws.path),
            "import sys, json, pathlib; sys.path.insert(0, %r)\n"
            "p = pathlib.Path(%r) / '.harness-kb' / '_state.json'\n"
            "s = json.loads(p.read_text())\n"
            "print('STILL:' + s['current_stage'])\n"
            "print('DONE:' + ','.join(s['completed_stages']))\n"
            % (STATE_IO_SCRIPTS, str(proj)),
        )
        exit_code(proc_check, 0, "读盘校验应成功")
        eq(proc_check.stdout.splitlines()[0], "STILL:P0",
           "非法 stage 调用不应改动 current_stage")
        eq(proc_check.stdout.splitlines()[1], "DONE:",
           "非法 stage 调用不应改动 completed_stages")
    finally:
        ws.cleanup()
