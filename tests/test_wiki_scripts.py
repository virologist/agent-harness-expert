"""wiki-creator 7 个脚本的冒烟测试。

build_index.py / _root.py / parse_raw.py / _common.py / diff.py / init_wiki.py / lint.py
每个脚本至少 2 例（happy path + boundary/error path）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from _harness import (
    SCHEMA_FIXTURE,
    WIKI_BUILD,
    WIKI_DIFF,
    WIKI_INIT,
    WIKI_LINT,
    WIKI_PARSE,
    WIKI_SCRIPTS,
    Workspace,
    build_wiki_page,
    contains,
    eq,
    exit_code,
    is_true,
    json_out,
    not_contains,
    run,
    run_python,
)


def _make_wiki(ws: Workspace, pages: dict[str, str]) -> None:
    """init_wiki + 写 SCHEMA + 写页面 + 写 raw 源文件。"""
    proc = run(WIKI_INIT, ["--root", ws.path])
    exit_code(proc, 0, "init_wiki 应成功")
    ws.write("wiki/SCHEMA.md", SCHEMA_FIXTURE)
    for rel, content in pages.items():
        ws.write(f"wiki/pages/{rel}", content)
    ws.write("raw/a.md", "# 原始材料\n\n正文。\n")


# ---------------------------------------------------------------------------
# _root.py（模块，无 CLI）
# ---------------------------------------------------------------------------

def test_root_detect_with_project_marker():
    ws = Workspace()
    try:
        ws.write("pyproject.toml", "[project]\nname='x'\n")
        proc = run_python(
            "from _root import detect_wiki_root\nprint(detect_wiki_root())\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "detect_wiki_root 不应抛异常")
        # 脚本内部走 Path.cwd()（已解析符号链接），比较前先归一
        eq(proc.stdout.strip(), str((ws.path / ".wiki-creator").resolve()),
           "项目标记命中应绑定项目根")
    finally:
        ws.cleanup()


def test_root_detect_global_fallback():
    ws = Workspace()
    try:
        proc = run_python(
            "from pathlib import Path\nfrom _root import detect_wiki_root\n"
            "print(detect_wiki_root())\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "无项目标记时不应抛异常")
        eq(proc.stdout.strip(), str(Path.home() / ".wiki-creator"), "无标记应回落全局目录")
    finally:
        ws.cleanup()


def test_root_global_fallback_warns_cross_task_pollution():
    """F-02：回落全局根时 stderr 须有中文告警（含路径+跨任务污染提示）；不改默认拒绝。"""
    ws = Workspace()
    try:
        # standalone 回落：行为不变（仍返回全局根），但必须告警
        proc = run_python(
            "from pathlib import Path\nfrom _root import detect_wiki_root\n"
            "print('ROOT:' + str(detect_wiki_root()))\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
            env={"WORKBUDDY_CONTEXT": "standalone"},
        )
        exit_code(proc, 0, "standalone 回落不应抛异常")
        contains(proc.stdout, "ROOT:", "应返回全局根路径")
        contains(proc.stderr, "回落全局根", "F-02：stderr 须提示回落全局根")
        contains(proc.stderr, "跨任务污染", "F-02：stderr 须提示跨任务污染风险")

        # team 模式仍拒绝回落（默认拒绝语义保留，不放宽）
        proc2 = run_python(
            "from _root import detect_wiki_root\n"
            "try:\n    detect_wiki_root()\n    print('NO_RAISE')\n"
            "except RuntimeError:\n    print('RAISED')\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
            env={"WORKBUDDY_CONTEXT": "team"},
        )
        exit_code(proc2, 0, "子进程应正常退出")
        eq(proc2.stdout.strip(), "RAISED", "F-02：team 模式必须保留拒绝回落语义")
    finally:
        ws.cleanup()


def test_root_normalize_path_keeps_posix_paths():
    proc = run_python(
        "import sys\nfrom _root import normalize_path\n"
        "p = normalize_path('/c/Users/someone')\n"
        "print('CONVERTED' if str(p) != '/c/Users/someone' else 'KEPT')\n",
        syspath=[WIKI_SCRIPTS],
    )
    exit_code(proc, 0, "normalize_path 不应抛异常")
    if sys.platform != "win32":
        eq(proc.stdout.strip(), "KEPT", "非 Windows 不得把 /c/... 误改成盘符路径")


def test_root_safe_mkdir_idempotent():
    ws = Workspace()
    try:
        d = ws.path / "a" / "b"
        proc = run_python(
            f"from pathlib import Path\nfrom _root import safe_mkdir\n"
            f"p = Path({str(d)!r})\nsafe_mkdir(p, parents=True)\nsafe_mkdir(p, parents=True)\n"
            f"print('OK' if p.is_dir() else 'FAIL')\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "重复 safe_mkdir 不应抛异常")
        eq(proc.stdout.strip(), "OK", "safe_mkdir 应幂等且目录存在")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# _common.py（模块，无 CLI）
# ---------------------------------------------------------------------------

def test_common_split_yaml_list_quoted():
    proc = run_python(
        "from _common import split_yaml_list\n"
        "print(split_yaml_list('a, \"b,c\", d'))\n",
        syspath=[WIKI_SCRIPTS],
    )
    exit_code(proc, 0, "split_yaml_list 不应抛异常")
    eq(proc.stdout.strip(), "['a', 'b,c', 'd']", "带引号的逗号不得被拆开")


def test_common_parse_frontmatter_inline_list():
    text = "---\ntitle: 注意力\naliases: [attn, 注意力机制]\n---\n\n正文\n"
    proc = run_python(
        f"from _common import parse_frontmatter\n"
        f"fm, body = parse_frontmatter({text!r})\n"
        f"print(fm.get('aliases'), fm.get('title'), body.strip())\n",
        syspath=[WIKI_SCRIPTS],
    )
    exit_code(proc, 0, "parse_frontmatter 不应抛异常")
    contains(proc.stdout, "['attn', '注意力机制']", "内联列表应被解析")
    contains(proc.stdout, "注意力", "标量字段应被解析")


def test_common_classify_link_style_issues():
    proc = run_python(
        "from _common import classify_link\n"
        "bad = classify_link('Attn Show|显示名')\n"
        "good = classify_link('transformer')\n"
        "print(sorted(bad['issues']), bad['conforming'], good['conforming'])\n",
        syspath=[WIKI_SCRIPTS],
    )
    exit_code(proc, 0, "classify_link 不应抛异常")
    contains(proc.stdout, "'uppercase'", "大写应被识别为非法风格")
    contains(proc.stdout, "'pipe-display'", "管道显示名应被识别")
    contains(proc.stdout, "False True", "非法/合法链接的 conforming 应相反")


def test_common_load_schema_topics():
    ws = Workspace()
    try:
        ws.write("wiki/SCHEMA.md", SCHEMA_FIXTURE)
        proc = run_python(
            f"from pathlib import Path\nfrom _common import load_schema\n"
            f"s = load_schema(Path({str(ws.path / 'wiki')!r}))\n"
            f"print(s['schema_version'], sorted(s['topics'].keys()), sorted(s['entity_types']))\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "load_schema 不应抛异常")
        contains(proc.stdout, "['llm-basics']", "主题清单应被解析")
        contains(proc.stdout, "'概念'", "实体类型清单应被解析")
        contains(proc.stdout, "v1", "schema_version 应被解析")
    finally:
        ws.cleanup()


def test_common_load_json_missing_is_silent_corrupt_warns():
    """F-06：文件不存在静默返回默认；文件存在但 JSON 损坏须 stderr 中文告警含路径。"""
    ws = Workspace()
    try:
        missing = ws.path / "nope.json"
        proc = run_python(
            "from pathlib import Path\nfrom _common import load_json\n"
            f"r = load_json(Path({str(missing)!r}), {{'k': 'default'}})\n"
            "print('GOT:' + repr(r))\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "文件不存在不应抛异常")
        contains(proc.stdout, "GOT:{'k': 'default'}", "文件不存在应静默返回默认值")
        eq(proc.stderr, "", "文件不存在（合法首次）不得写 stderr 告警")

        corrupt = ws.path / "bad.json"
        corrupt.write_text("BROKEN{ 不是JSON", encoding="utf-8")
        proc2 = run_python(
            "from pathlib import Path\nfrom _common import load_json\n"
            f"r = load_json(Path({str(corrupt)!r}), {{'k': 'default'}})\n"
            "print('GOT:' + repr(r))\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc2, 0, "损坏 JSON 不应抛异常（回退默认）")
        contains(proc2.stdout, "GOT:{'k': 'default'}", "损坏应回退默认值")
        contains(proc2.stderr, "JSON 损坏", "损坏须有中文告警")
        contains(proc2.stderr, "bad.json", "告警须含文件路径")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# init_wiki.py
# ---------------------------------------------------------------------------

def test_init_wiki_creates_skeleton():
    ws = Workspace()
    try:
        proc = run(WIKI_INIT, ["--root", ws.path])
        exit_code(proc, 0, "init_wiki 首次创建应返回 0")
        data = json_out(proc, "init_wiki 输出")
        eq(data["status"], "created", "首次应为 created")
        eq(data["schema_action"], "created", "SCHEMA 应为 created")
        is_true(ws.exists("wiki/SCHEMA.md"), "应创建 SCHEMA.md")
        is_true(ws.exists("raw"), "应创建 raw/")
        is_true(ws.exists("wiki/pages"), "应创建 pages/")
    finally:
        ws.cleanup()


def test_init_wiki_preserves_user_schema_even_with_force():
    ws = Workspace()
    try:
        run(WIKI_INIT, ["--root", ws.path])
        marker = "# 用户手写的 SCHEMA，任何情况都不应被覆盖\n"
        ws.write("wiki/SCHEMA.md", marker)
        again = run(WIKI_INIT, ["--root", ws.path])
        exit_code(again, 0, "重复 init 应返回 0")
        eq(json_out(again, "重复 init")["schema_action"], "preserved", "重复 init 应保护 SCHEMA")
        forced = run(WIKI_INIT, ["--root", ws.path, "--force"])
        exit_code(forced, 0, "--force 应返回 0")
        eq(json_out(forced, "--force")["schema_action"], "preserved", "--force 也不得覆盖 SCHEMA")
        eq(ws.read("wiki/SCHEMA.md"), marker, "用户 SCHEMA 内容必须原样保留")
    finally:
        ws.cleanup()


def test_init_wiki_reset_schema_backups():
    ws = Workspace()
    try:
        run(WIKI_INIT, ["--root", ws.path])
        ws.write("wiki/SCHEMA.md", "# 改坏了的版本\n")
        before_reset = ws.read("wiki/SCHEMA.md")
        proc = run(WIKI_INIT, ["--root", ws.path, "--reset-schema"])
        exit_code(proc, 0, "--reset-schema 应返回 0")
        eq(json_out(proc, "--reset-schema")["schema_action"], "reset-with-backup",
           "应标注 reset-with-backup")
        is_true(ws.exists("wiki/SCHEMA.md.bak"), "覆盖前应备份")
        eq(ws.read("wiki/SCHEMA.md.bak"), before_reset, "备份应是覆盖前的那一份内容")
        contains(ws.read("wiki/SCHEMA.md"), "Wiki 知识库约束配置", "SCHEMA 应被模板覆盖")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# build_index.py
# ---------------------------------------------------------------------------

def test_build_index_ok():
    ws = Workspace()
    try:
        _make_wiki(ws, {
            "llm-basics/attention.md": build_wiki_page("注意力机制", link="transformer"),
            "llm-basics/transformer.md": build_wiki_page("Transformer", entity_type="模型",
                                                         aliases="tf", link="attention"),
        })
        proc = run(WIKI_BUILD, ["--root", ws.path])
        exit_code(proc, 0, "build_index 应返回 0")
        data = json_out(proc, "build_index 输出")
        eq(data["status"], "ok", "build_index 状态")
        eq(data["page_count"], 2, "页面数")
        eq(data["indexed_page_count"], 2, "入索引页面数")
        is_true(data["backlinks_count"] >= 2, "两页互相引用应产生反链")
        contains(ws.read("wiki/index.md"), "llm-basics", "index.md 应含主题")
        is_true(ws.exists("wiki/topics/llm-basics.md"), "应生成主题索引")
    finally:
        ws.cleanup()


def test_build_index_without_wiki_exit_one():
    ws = Workspace()
    try:
        proc = run(WIKI_BUILD, ["--root", ws.path])
        exit_code(proc, 1, "缺 wiki/ 应返回 1")
        contains(proc.stdout, "wiki/ 不存在", "应提示 wiki/ 不存在")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# diff.py
# ---------------------------------------------------------------------------

def test_diff_detects_new_raw_file():
    ws = Workspace()
    try:
        _make_wiki(ws, {"llm-basics/attention.md": build_wiki_page("注意力机制")})
        proc = run(WIKI_DIFF, ["--root", ws.path])
        exit_code(proc, 0, "diff 应返回 0")
        data = json_out(proc, "diff 输出")
        is_true("raw/a.md" in data["new"], f"新文件应被识别为 new，实际 {data['new']}")
        eq(data["changed"], [], "首次 diff 不应有 changed")
    finally:
        ws.cleanup()


def test_diff_unchanged_after_build():
    ws = Workspace()
    try:
        _make_wiki(ws, {"llm-basics/attention.md": build_wiki_page("注意力机制")})
        run(WIKI_BUILD, ["--root", ws.path])
        proc = run(WIKI_DIFF, ["--root", ws.path])
        exit_code(proc, 0, "build 后 diff 应返回 0")
        data = json_out(proc, "diff 输出")
        is_true("raw/a.md" in data["unchanged"], f"已编译文件应 unchanged，实际 {data}")
        eq(data["new"], [], "编译后不应再有 new")
        # 改动源文件 → 应变为 changed，并经 source_to_pages 反查到受影响页
        ws.write("raw/a.md", "# 原始材料\n\n改过了。\n")
        proc2 = run(WIKI_DIFF, ["--root", ws.path])
        data2 = json_out(proc2, "diff 二次输出")
        is_true("raw/a.md" in data2["changed"], f"内容变化应变为 changed，实际 {data2}")
        is_true(len(data2["affected_pages"]) >= 1, "changed 文件应反查到受影响页面")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# lint.py
# ---------------------------------------------------------------------------

def test_lint_clean_wiki():
    ws = Workspace()
    try:
        _make_wiki(ws, {
            "llm-basics/attention.md": build_wiki_page("注意力机制", link="transformer"),
            "llm-basics/transformer.md": build_wiki_page("Transformer", entity_type="模型",
                                                         aliases="tf", link="attention"),
        })
        run(WIKI_BUILD, ["--root", ws.path])
        proc = run(WIKI_LINT, ["--root", ws.path])
        exit_code(proc, 0, "lint 应返回 0")
        data = json_out(proc, "lint 输出")
        eq(data["page_count"], 2, "lint 页面数")
        eq(data["orphans"], [], "互相引用不应有孤立页")
        eq(data["dangling_links"], [], "引用存在的页不应有悬空链接")
        eq(data["topic_missing"], [], "页面都有 topic")
        eq(data["missing_source_section"], [], "页面都有来源小节")
    finally:
        ws.cleanup()


def test_lint_detects_dangling_and_missing_topic():
    ws = Workspace()
    try:
        _make_wiki(ws, {"llm-basics/attention.md": build_wiki_page("注意力机制", link="ghost-page")})
        bad = ws.read("wiki/pages/llm-basics/attention.md").replace("topic: llm-basics\n", "")
        ws.write("wiki/pages/llm-basics/attention.md", bad)
        proc = run(WIKI_LINT, ["--root", ws.path])
        exit_code(proc, 0, "lint 报告问题仍返回 0（问题写在 JSON 里）")
        data = json_out(proc, "lint 输出")
        is_true("ghost-page" in data["dangling_links"],
                f"悬空目标应被识别，实际 {data['dangling_links']}")
        is_true(len(data["topic_missing"]) == 1, f"缺 topic 的页应被列出，实际 {data['topic_missing']}")
    finally:
        ws.cleanup()


def test_lint_without_wiki_exit_one():
    ws = Workspace()
    try:
        proc = run(WIKI_LINT, ["--root", ws.path])
        exit_code(proc, 1, "缺 wiki/ 应返回 1")
        contains(proc.stdout, "wiki/ 不存在", "应提示 wiki/ 不存在")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# parse_raw.py
# ---------------------------------------------------------------------------

def test_parse_raw_markdown():
    ws = Workspace()
    try:
        src = ws.write("a.md", "# 标题\n\n正文一段。\n")
        proc = run(WIKI_PARSE, [src])
        exit_code(proc, 0, "解析 md 应返回 0")
        contains(proc.stdout, "解析质量：完整", "md 应完整解析")
        contains(proc.stdout, "## §heading-1", "md 标题应生成 § 锚点")
        contains(proc.stdout, "正文一段", "正文应保留")
    finally:
        ws.cleanup()


def test_parse_raw_csv_table():
    ws = Workspace()
    try:
        src = ws.write("t.csv", "name,score\n注意力,9\n")
        proc = run(WIKI_PARSE, [src])
        exit_code(proc, 0, "解析 csv 应返回 0")
        contains(proc.stdout, "| name | score |", "csv 应转 markdown 表格")
    finally:
        ws.cleanup()


def test_parse_raw_missing_file_exit_one():
    ws = Workspace()
    try:
        proc = run(WIKI_PARSE, [ws.path / "nope.md"])
        exit_code(proc, 1, "文件不存在应返回 1")
        contains(proc.stderr + proc.stdout, "文件不存在", "应提示文件不存在")
    finally:
        ws.cleanup()


def test_parse_raw_writes_output_file():
    ws = Workspace()
    try:
        src = ws.write("a.md", "# 标题\n\n正文。\n")
        # 注：parse_raw 的 -o 不自动建父目录（父目录不存在会 FileNotFoundError）。
        # 这是脚本现状，本用例按"父目录已存在"的契约断言，不替它放宽。
        out = ws.path / "a.parsed.md"
        proc = run(WIKI_PARSE, [src, "-o", out])
        exit_code(proc, 0, "-o 应返回 0")
        is_true(out.is_file(), "-o 应写出文件")
        contains(out.read_text(encoding="utf-8"), "源文件：a.md", "写出内容应含源文件头")
    finally:
        ws.cleanup()


def test_parse_raw_json_roundtrip():
    ws = Workspace()
    try:
        src = ws.write("d.json", json.dumps({"a": 1}, ensure_ascii=False))
        proc = run(WIKI_PARSE, [src])
        exit_code(proc, 0, "解析 json 应返回 0")
        contains(proc.stdout, '"a": 1', "json 内容应原样保留")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# P3-6：独立 wiki 触发全局根警告（WORKBUDDY_CONTEXT env 探测）
# ---------------------------------------------------------------------------

def test_root_standalone_mode_global_fallback_unchanged():
    """P3-6: 独立用户场景（WORKBUDDY_CONTEXT=standalone 或未设）维持原行为：
    cwd 无项目标记时仍可回落 ~/.wiki-creator/。"""
    ws = Workspace()
    try:
        proc = run_python(
            "from pathlib import Path\nfrom _root import detect_wiki_root\n"
            "print(detect_wiki_root())\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
            env={"WORKBUDDY_CONTEXT": "standalone"},
        )
        exit_code(proc, 0, "standalone 模式不应抛异常")
        eq(proc.stdout.strip(), str(Path.home() / ".wiki-creator"),
           "standalone 模式无项目标记时应维持回落全局根（行为不变）")
    finally:
        ws.cleanup()


def test_root_team_mode_forbids_global_fallback():
    """P3-6: 团队模式（WORKBUDDY_CONTEXT=team）+ cwd 无项目标记时，
    detect_wiki_root() 必须抛 RuntimeError，禁止静默回落全局根。"""
    ws = Workspace()
    try:
        proc = run_python(
            "from _root import detect_wiki_root\n"
            "try:\n"
            "    detect_wiki_root()\n"
            "    print('NO_RAISE')\n"
            "except RuntimeError as e:\n"
            "    print('RAISED', str(e)[:60])\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
            env={"WORKBUDDY_CONTEXT": "team"},
        )
        exit_code(proc, 0, "子进程应正常退出（异常被捕获打印 RAISED）")
        eq(proc.stdout.strip().split(" ", 1)[0], "RAISED",
           "team 模式无项目标记时必须抛 RuntimeError，不得回落全局根")
        contains(proc.stdout, "WORKBUDDY_CONTEXT=team",
                 "错误信息应明确提示 team 模式约束，便于排查")
    finally:
        ws.cleanup()


# ---------------------------------------------------------------------------
# P4（N-1 闭合）：load_pages 坏页隔离——lint/build_index 不 traceback、坏页可见
# ---------------------------------------------------------------------------

def test_load_pages_isolates_undecodable_page():
    """坏页（非 UTF-8）被隔离进 decode_errors，好页照常解析。"""
    ws = Workspace()
    try:
        ws.write("wiki/pages/bad.md", "skip")
        # 直接写二进制内容（非 UTF-8）
        (ws.path / "wiki" / "pages" / "bad.md").write_bytes(b"\x00\xff binary junk")
        ws.write("wiki/pages/good.md", build_wiki_page("Good"))
        proc = run_python(
            "from pathlib import Path\n"
            "from _common import load_pages\n"
            "pages, errs = load_pages(Path('wiki'))\n"
            "print(len(pages), len(errs))\n"
            "print(pages[0]['slug'])\n"
            "print(errs[0]['path'])\n",
            cwd=ws.path, syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "load_pages 遇坏页不应抛异常")
        first = proc.stdout.strip().splitlines()
        eq(first[0], "1 1", "应恰好解析出 1 个好页 + 1 个坏页")
        eq(first[1], "good", "好页 slug 应为 good")
        eq(first[2], "pages/bad.md", "坏页 path 应为 wiki 相对 posix 路径")
    finally:
        ws.cleanup()


def test_lint_reports_decode_errors_no_traceback():
    """lint 遇坏页：decode_errors 进报告、0 traceback、page_count 只计健康页。"""
    ws = Workspace()
    try:
        _make_wiki(ws, {"good.md": build_wiki_page("Good")})
        (ws.path / "wiki" / "pages" / "bad.md").write_bytes(b"\x00\xff binary junk")
        proc = run(WIKI_LINT, ["--root", ws.path])
        exit_code(proc, 0, "lint 坏页走报告哲学，rc 仍 0")
        result = json_out(proc, "lint 输出应为 JSON")
        eq(result["page_count"], 1, "page_count 只计健康页")
        is_true("decode_errors" in result, "报告应含 decode_errors 键")
        eq(result["decode_errors"][0]["path"], "pages/bad.md", "坏页路径应入报告")
        not_contains(proc.stderr, "Traceback", "lint 不应产生 traceback")
    finally:
        ws.cleanup()


def test_build_index_reports_decode_errors_no_traceback():
    """build_index 遇坏页：completed_with_errors + rc=1 + stderr WARNING + 0 traceback。"""
    ws = Workspace()
    try:
        _make_wiki(ws, {"good.md": build_wiki_page("Good")})
        (ws.path / "wiki" / "pages" / "bad.md").write_bytes(b"\x00\xff binary junk")
        proc = run(WIKI_BUILD, ["--root", ws.path])
        exit_code(proc, 1, "坏页使索引/manifest 不完整，build 应 rc=1")
        result = json_out(proc, "build 输出应为 JSON")
        eq(result["status"], "completed_with_errors", "status 应降级为 completed_with_errors")
        contains(proc.stderr, "WARNING: 页面读取失败", "stderr 应有 WARNING 行")
        not_contains(proc.stderr, "Traceback", "build 不应产生 traceback")
    finally:
        ws.cleanup()


def test_healthy_wiki_has_no_decode_errors_key():
    """口径 3：健康 wiki 的 lint/build 报告不得出现 decode_errors 键（零新增键）。"""
    ws = Workspace()
    try:
        _make_wiki(ws, {"good.md": build_wiki_page("Good")})
        lint_proc = run(WIKI_LINT, ["--root", ws.path])
        lint_result = json_out(lint_proc, "lint 输出应为 JSON")
        is_true("decode_errors" not in lint_result, "健康路径 lint 报告不得含 decode_errors 键")
        build_proc = run(WIKI_BUILD, ["--root", ws.path])
        exit_code(build_proc, 0, "健康 wiki build 应 rc=0")
        build_result = json_out(build_proc, "build 输出应为 JSON")
        eq(build_result["status"], "ok", "健康路径 status 应为 ok")
        is_true("decode_errors" not in build_result, "健康路径 build 报告不得含 decode_errors 键")
    finally:
        ws.cleanup()


def test_init_wiki_broken_dir_returns_json_error_not_traceback():
    """P2-1：wiki / raw / --root 为普通文件时，应输出 JSON error + exit 1，无裸 traceback。"""
    ws = Workspace()
    try:
        # 构造 wiki 为普通文件的损坏根
        (ws.path / "wiki").write_text("I am a file not a dir", encoding="utf-8")
        proc = run(WIKI_INIT, ["--root", str(ws.path)])
        exit_code(proc, 1, "损坏目录应 exit 1")
        not_contains(proc.stderr, "Traceback", "不得有裸 traceback")
        # stderr 与 stdout 中应有可读 JSON error
        combined = proc.stdout + proc.stderr
        is_true('"status": "error"' in combined or '"status":"error"' in combined,
                f"应输出结构化 JSON error: {combined}")
        is_true("error" in combined, "JSON 应含 error 字段说明原因")

        # --root 指向普通文件
        f = ws.path / "afile"
        f.write_text("x", encoding="utf-8")
        proc2 = run(WIKI_INIT, ["--root", str(f)])
        exit_code(proc2, 1, "--root 为普通文件应 exit 1")
        not_contains(proc2.stderr, "Traceback", "不得有裸 traceback")
    finally:
        ws.cleanup()


def test_parse_raw_libreoffice_failure_emits_reason():
    """F-10：LibreOffice 转换异常时不得静默吞——须向 stderr 打中文原因标记。"""
    proc = run_python(
        "import sys, subprocess\n"
        "from pathlib import Path\n"
        "import parse_raw as M\n"
        # 让 which 认为 soffice 存在，但 subprocess.run 抛异常触发 except 分支
        "M.shutil.which = lambda name: ('soffice' if name == 'soffice' else None)\n"
        "def boom(*a, **kw):\n"
        "    raise RuntimeError('模拟转换失败')\n"
        "M.subprocess.run = boom\n"
        "r = M._libreoffice_to_text(Path('/tmp/sample.docx'))\n"
        "assert r is None, r\n"
        "print('DONE')\n",
        syspath=[WIKI_SCRIPTS],
    )
    exit_code(proc, 0, "转换失败应返回 None 不抛异常")
    contains(proc.stdout, "DONE", "函数应正常返回")
    contains(proc.stderr, "LibreOffice 转换失败", "F-10：须有中文原因标记")
    contains(proc.stderr, "sample.docx", "告警应含文件路径")


def test_atomic_write_text_leaves_no_tmp_and_overwrites():
    """F-09：原子写 helper 应覆盖旧内容、无 .tmp 残留、内容完整可解析。"""
    # 用真实工作区逐一验证两个模块的 helper
    ws = Workspace()
    try:
        for mod_name in ("init_wiki", "build_index"):
            target = ws.path / f"{mod_name}.json"
            target.write_text('{"old": true}', encoding="utf-8")
            proc = run_python(
                f"from pathlib import Path\n"
                f"import {mod_name} as M\n"
                f"p = Path({str(target)!r})\n"
                f"M.atomic_write_text(p, '{{\"new\": 42}}')\n"
                "print('OK')\n",
                syspath=[WIKI_SCRIPTS],
            )
            exit_code(proc, 0, f"{mod_name}.atomic_write_text 应成功")
            contains(proc.stdout, "OK", f"{mod_name} 原子写应执行成功")
            # 内容已被完整覆盖
            eq(json.loads(target.read_text(encoding="utf-8")), {"new": 42},
               f"{mod_name} 原子写应完整覆盖旧内容")
            # 无 .tmp 残局
            tmps = list(ws.path.glob(f"{mod_name}.json.*.tmp"))
            eq(tmps, [], f"{mod_name} 原子写不得留 .tmp 残局")
    finally:
        ws.cleanup()


def test_parse_raw_atomic_write_survives_replace_failure():
    """F-09 补齐：parse_raw 的 -o 写出必须是原子写——replace 崩断时
    目标文件不被破坏（不留半截内容）、且无 .tmp 残局。

    能红能绿：修复前 parse_raw 无 atomic_write_text（非原子 write_text 直写），
    本用例在 helper 缺失 / replace 崩断两条路径上均失败；修复后全绿。
    """
    ws = Workspace()
    try:
        # ── 路径 A：崩断模拟——replace 抛错时目标文件保持原样 ──
        target = ws.path / "out.md"
        target.write_text("ORIGINAL-CONTENT", encoding="utf-8")
        proc = run_python(
            "import pathlib\n"
            "from pathlib import Path\n"
            "import parse_raw as M\n"
            f"target = Path({str(target)!r})\n"
            # 崩溃模拟：replace 阶段抛错（等价于进程在提交前被杀）
            "def boom(self, *a, **kw):\n"
            "    raise OSError('模拟 replace 崩断')\n"
            "pathlib.Path.replace = boom\n"
            "try:\n"
            "    M.atomic_write_text(target, 'NEW-CONTENT')\n"
            "    print('NO_RAISE')\n"
            "except OSError as e:\n"
            "    print('RAISED', str(e))\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc, 0, "replace 崩断应被正常抛出（不静默吞错）")
        contains(proc.stdout, "RAISED", "replace 崩断必须抛异常，不得静默吞")
        # 目标文件未被破坏：仍是完整旧内容，而不是半截
        eq(target.read_text(encoding="utf-8"), "ORIGINAL-CONTENT",
           "replace 崩断时目标文件不得被破坏（不得留半截内容）")
        # 无 tmp 残局
        tmps = list(ws.path.glob("out.md.*.tmp"))
        eq(tmps, [], "replace 崩断后不得留 .tmp 残局")

        # ── 路径 B：CLI 层崩断——main() 的 -o 必须走原子写 ──
        # （若 CLI 仍用非原子 write_text 直写，目标文件会被写成半截/新内容）
        src = ws.write("a.md", "# 标题\n\n正文。\n")
        cli_target = ws.path / "cli.md"
        cli_target.write_text("CLI-ORIGINAL", encoding="utf-8")
        proc_cli = run_python(
            "import pathlib, sys\n"
            "from pathlib import Path\n"
            "import parse_raw as M\n"
            f"src = Path({str(src)!r})\n"
            f"out = Path({str(cli_target)!r})\n"
            "def boom(self, *a, **kw):\n"
            "    raise OSError('模拟 replace 崩断')\n"
            "pathlib.Path.replace = boom\n"
            "sys.argv = ['parse_raw.py', str(src), '-o', str(out)]\n"
            "rc = M.main()\n"
            "print('RC', rc)\n",
            syspath=[WIKI_SCRIPTS],
        )
        exit_code(proc_cli, 0, "崩断模拟子进程应正常退出（异常被 main 捕获转成 rc=1）")
        contains(proc_cli.stdout, "RC 1", "CLI 撞上 replace 崩断应返回 1 而非崩溃")
        eq(cli_target.read_text(encoding="utf-8"), "CLI-ORIGINAL",
           "CLI replace 崩断时目标文件不得被破坏（不得留半截内容）")
        cli_tmps = list(ws.path.glob("cli.md.*.tmp"))
        eq(cli_tmps, [], "CLI replace 崩断后不得留 .tmp 残局")

        # ── 路径 C：CLI 正常路径——-o 写出后无 tmp 残留且内容完整 ──
        proc2 = run(WIKI_PARSE, [src, "-o", cli_target])
        exit_code(proc2, 0, "-o 应返回 0")
        is_true(cli_target.is_file(), "-o 应写出文件")
        contains(cli_target.read_text(encoding="utf-8"), "源文件：a.md", "写出内容应含源文件头")
        cli_tmps2 = list(ws.path.glob("cli.md.*.tmp"))
        eq(cli_tmps2, [], "CLI -o 正常路径也不得留 .tmp 残局")
    finally:
        ws.cleanup()
