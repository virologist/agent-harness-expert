"""_common.py — 脚本间共享的解析/收集/校验原语（唯一真源，消除各脚本拷贝分叉）

被 build_index.py / lint.py / diff.py 复用。职责仅限：解析 frontmatter/SCHEMA、
收集页面与 raw、规范化与解析 wikilink（别名归一 + 非法风格识别）、计算哈希。
**不做任何语义创作，也不做"检索/召回"——选页判断权始终留给 LLM。**
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from _root import normalize_path  # re-export 便于统一入口

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------

# 宽匹配：抓取 [[ ... ]] 内的任意内容（含大写/中文/管道），再分类处理。
# 用 [^\[\]] 避免跨括号；惰性以命中最近的 ]]。
LINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# 规范 slug（kebab-case 英文，可选单个 topic 前缀）：
CONFORMING_TARGET_RE = re.compile(r"^[a-z0-9][a-z0-9-]*(?:/[a-z0-9][a-z0-9-]*)?$")
# slug 段（末段）规范：
CONFORMING_SEG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# 摘要 / 证据小节
SUMMARY_RE = re.compile(r"^##\s*摘要\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
SOURCE_SECTION_RE = re.compile(r"^##\s*(证据\s*/\s*来源|证据|来源)\s*$", re.MULTILINE)
# 来源锚点：正文中出现的 raw/ 路径或 §章节 标记
SOURCE_ANCHOR_RE = re.compile(r"raw/\S|§\S")

# entity_type 排序权重（未知类型放最后）
ENTITY_ORDER = {
    "概念": 1, "方法": 2, "模型": 3, "数据集": 4,
    "事件": 5, "论文": 6, "人物": 7, "机构": 8,
}

MAX_TOPIC_PAGES = 1000


# ---------------------------------------------------------------------------
# 基础 IO
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Frontmatter 解析（引号感知，修复含逗号/引号的列表项被拆错）
# ---------------------------------------------------------------------------

def split_yaml_list(s: str) -> list[str]:
    """拆分内联 YAML 列表内容（[] 之间的部分），感知引号与转义。

    'a, "b,c", \\'d\\'' -> ['a', 'b,c', 'd']
    """
    if not s or not s.strip():
        return []
    items, cur, quote = [], "", None
    i = 0
    while i < len(s):
        c = s[i]
        if quote:
            if c == "\\" and i + 1 < len(s):
                cur += s[i + 1]
                i += 2
                continue
            if c == quote:
                quote = None
                i += 1
                continue
            cur += c
            i += 1
            continue
        if c in "\"'":
            quote = c
            i += 1
            continue
        if c == ",":
            items.append(cur)
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    items.append(cur)
    return [x.strip() for x in items]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """简易 YAML frontmatter 解析：平铺标量 + 内联列表（引号感知）。"""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    fm: dict = {}
    for line in fm_text.splitlines():
        raw = line.rstrip()
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if ":" not in s:
            continue
        k, v = s.split(":", 1)
        k = k.strip()
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            fm[k] = split_yaml_list(v[1:-1])
        else:
            fm[k] = v.strip("'\"")
    return fm, body


# ---------------------------------------------------------------------------
# SCHEMA 解析（主题清单 / 实体类型清单 / schema_version）
# ---------------------------------------------------------------------------

def _is_table_sep_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c or "") for c in cells)


def current_schema_version(wiki_dir: Path) -> str:
    p = wiki_dir / "SCHEMA.md"
    if not p.exists():
        return "v1"
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("schema_version:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return "v1"


def load_schema(wiki_dir: Path) -> dict:
    """解析 SCHEMA.md：主题清单、实体类型清单、schema_version。

    主题行判定严格：排除表头(slug，大小写不敏感)、排除分隔行(含左对齐 |:---|)、
    且首格必须形如 kebab-case slug，避免把装饰行/错位行当成主题。
    """
    schema_path = wiki_dir / "SCHEMA.md"
    result = {
        "schema_version": current_schema_version(wiki_dir),
        "topics": {},
        "entity_types": set(),
    }
    if not schema_path.exists():
        return result

    section = None
    for line in schema_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("## "):
            if s.startswith("## 主题清单"):
                section = "topics"
            elif s.startswith("## 实体类型清单"):
                section = "entity_types"
            else:
                section = None
            continue
        if section == "topics" and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if not cells or not cells[0]:
                continue
            if cells[0].lower() == "slug":      # 表头
                continue
            if _is_table_sep_row(cells):        # 分隔行 |---| 或 |:---|
                continue
            if not CONFORMING_SEG_RE.match(cells[0]):  # 首格非合法 slug → 忽略
                continue
            name = cells[1] if len(cells) > 1 else cells[0]
            desc = cells[2] if len(cells) > 2 else ""
            result["topics"][cells[0]] = {"name": name, "desc": desc}
        elif section == "entity_types" and s.startswith("- "):
            et = s[2:].strip()
            if et:
                result["entity_types"].add(et)
    return result


# ---------------------------------------------------------------------------
# 页面收集（统一：含全部 .md，标记缺 topic，避免 build/lint 分叉）
# ---------------------------------------------------------------------------

def iter_page_files(wiki_dir: Path) -> list[Path]:
    pages_dir = wiki_dir / "pages"
    if not pages_dir.exists():
        return []
    return sorted(pages_dir.rglob("*.md"))


def load_pages(wiki_dir: Path) -> list[dict]:
    """读取 pages/**/*.md，返回富页面字典（含 raw_links）。

    与旧 build_index 不同：**不静默跳过缺 topic 的页**，而是标记 topic_missing=True，
    由调用方决定如何处理并在报告中可见，保证 build_index 与 lint 计数一致。
    """
    pages = []
    for md in iter_page_files(wiki_dir):
        text = md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text)
        slug = md.stem
        topic = fm.get("topic", "") or ""
        sources = fm.get("sources", []) or []
        aliases = fm.get("aliases", []) or []
        pages.append({
            "path": md.relative_to(wiki_dir).as_posix(),
            "abs_path": str(md),
            "slug": slug,
            "title": fm.get("title", slug) or slug,
            "topic": topic,
            "topic_missing": not topic,
            "entity_type": fm.get("entity_type", "") or "",
            "aliases": aliases,
            "sources": sources,
            "schema_version": fm.get("schema_version", "") or "",
            "summary": extract_summary(body),
            "raw_links": LINK_RE.findall(body),
            "body": body,
        })
    return pages


def extract_summary(body: str) -> str:
    m = SUMMARY_RE.search(body)
    if not m:
        return ""
    return m.group(1).strip().split("\n\n")[0].strip()


# ---------------------------------------------------------------------------
# Wikilink 规范化 + 别名解析 + 非法风格识别（必修 1/3 的核心）
# ---------------------------------------------------------------------------

def classify_link(raw: str) -> dict:
    """解析一条 [[...]] 原始内容。

    返回:
      target      —— 去掉显示名(|右侧)后的目标串（trim 后）
      display     —— 管道右侧显示名（无则 None）
      has_pipe    —— 是否用了 [[slug|显示名]] 语法
      slug_part   —— 目标的末段（topic/slug 取 slug），用于别名/页面匹配
      topic_hint  —— topic/slug 的前缀（无则 None）
      conforming  —— 是否符合规范 kebab-case（无大写/中文/空格/下划线/管道）
      issues      —— 非法风格原因列表（大写/非ASCII/空格下划线/管道/结构）
    """
    has_pipe = "|" in raw
    target, display = (raw.split("|", 1) if has_pipe else (raw, None))
    target = target.strip()
    display = display.strip() if display is not None else None

    if "/" in target:
        topic_hint, seg = target.split("/", 1)
        slug_part = seg.rsplit("/", 1)[-1]
        topic_hint = topic_hint.strip()
    else:
        topic_hint = None
        slug_part = target

    issues = []
    low_target = target.lower()
    if has_pipe:
        issues.append("pipe-display")
    if any(ch.isupper() for ch in target):
        issues.append("uppercase")
    if any(ord(ch) > 127 for ch in target):
        issues.append("non-ascii")
    if " " in target.strip() or "_" in target:
        issues.append("space-or-underscore")
    # 结构性：整目标不符合 kebab(/kebab) 规范
    if not CONFORMING_TARGET_RE.match(low_target):
        issues.append("malformed-slug")

    conforming = (not issues) and bool(CONFORMING_TARGET_RE.match(target))
    return {
        "raw": raw,
        "target": target,
        "display": display,
        "has_pipe": has_pipe,
        "slug_part": slug_part.strip(),
        "topic_hint": topic_hint,
        "conforming": conforming,
        "issues": issues,
    }


def build_alias_index(pages: list[dict]) -> dict[str, str]:
    """构建 归一化key -> 规范slug 的别名索引。

    key 来源优先级 **slug > alias > title**（全部 lower）。按三轮顺序、先到先得写入，
    保证真实 slug 永远压过别名/标题，避免"A 的 title 恰好等于 B 的 slug"时误解析。
    用于把 [[attn]] 解析到 attention、把 [[Attention]] / [[注意力机制]] 解析到其规范 slug。
    """
    idx: dict[str, str] = {}
    rounds = (
        [(p["slug"], p["slug"]) for p in pages],                          # 1) slug 最高优先
        [(a, p["slug"]) for p in pages for a in p["aliases"] if a],       # 2) 别名
        [(p.get("title", ""), p["slug"]) for p in pages],                 # 3) 标题兜底
    )
    for pairs in rounds:
        for key, slug in pairs:
            if not key:
                continue
            k = key.lower()
            if k not in idx:
                idx[k] = slug
    return idx


def resolve_link(link: dict, alias_index: dict[str, str], page_slugs: set[str]) -> dict:
    """给一条 classify_link 结果附加解析信息。

      resolved_slug —— 若命中别名索引则为其规范 slug，否则 None
      exists        —— resolved_slug 是否为真实存在的页面
      is_self       —— 占位，由调用方按当前页填充
    """
    key = link["slug_part"].lower()
    resolved = alias_index.get(key)
    return {
        **link,
        "resolved_slug": resolved,
        "exists": resolved in page_slugs if resolved else False,
    }


def analyze_page_links(page: dict, alias_index: dict[str, str], page_slugs: set[str]) -> dict:
    """解析一页的所有链接，返回带解析结果的列表 + 去重后的规范前向链接集合。"""
    links = []
    resolved_targets = []
    for raw in page["raw_links"]:
        info = resolve_link(classify_link(raw), alias_index, page_slugs)
        # dangling key：解析到规范 slug 用它，否则用 slug_part 小写
        miss_key = info["resolved_slug"] or info["slug_part"].lower()
        info["miss_key"] = miss_key
        info["is_self"] = (info["resolved_slug"] == page["slug"])
        links.append(info)
        if info["resolved_slug"] and info["resolved_slug"] != page["slug"]:
            resolved_targets.append(info["resolved_slug"])
        elif not info["resolved_slug"] and miss_key != page["slug"]:
            resolved_targets.append(miss_key)
    return {"links": links, "forward": resolved_targets}


# ---------------------------------------------------------------------------
# raw/ 文件收集（递归，修复子目录被忽略）
# ---------------------------------------------------------------------------

def iter_raw_files(root: Path) -> list[Path]:
    """递归收集 raw/ 下所有普通文件（跳过隐藏文件/目录），按相对路径 posix 返回顺序。"""
    raw_dir = root / "raw"
    if not raw_dir.exists():
        return []
    files = []
    for p in raw_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name.startswith("."):
            continue
        # 跳过隐藏目录内的文件
        rel_parts = p.relative_to(raw_dir).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        files.append(p)
    return sorted(files, key=lambda x: x.relative_to(root).as_posix())


def raw_rel(path: Path, root: Path) -> str:
    """raw 文件相对 wiki 根的 posix 路径，如 raw/sub/a.pdf。"""
    return path.relative_to(root).as_posix()
