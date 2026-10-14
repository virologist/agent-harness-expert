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
