#!/usr/bin/env python3
"""知识条目前置字段与必答小节校验（schema 校验，零第三方依赖）。

框架条目（frameworks/）必填 frontmatter:
    name, alias, type, source, added, version, confidence, pinned
模型条目（models/）必填 frontmatter:
    name, alias, type, category, source, added, version, confidence, pinned
    且必含小节: 一句话定位 / 接口形态 / 延迟 / 已验证适用域 / 已验证不适用域 / 降级策略
模式文件（patterns/）必填 frontmatter:
    name, group, count, added, confidence
    且每个 ### 小节须含: 核心思想 / 可迁移到 / 案例 / 何时不用 / 对照问题

退出码语义（默认即严格，门禁不做"假绿"）：
    0  无问题；或显式 --lenient（有问题也放行，仅作提示）
    1  存在任一问题（默认行为，无需加参数）
    --strict 保留为向后兼容开关，当前等同于默认行为。

用法:
    python3 lint_knowledge.py references/knowledge
    python3 lint_knowledge.py references/knowledge/frameworks/core/claude-code.md
    python3 lint_knowledge.py references/knowledge --lenient   # 只提示，不卡门禁
"""
from __future__ import annotations

import argparse
from pathlib import Path

FRAMEWORK_KEYS = ["name", "alias", "type", "source", "added", "version", "confidence", "pinned"]
MODEL_KEYS = ["name", "alias", "type", "category", "source", "added", "version", "confidence", "pinned"]
MODEL_SECTIONS = ["一句话定位", "接口形态", "延迟", "已验证适用域", "已验证不适用域", "降级策略"]
PATTERN_KEYS = ["name", "group", "count", "added", "confidence"]
PATTERN_SECTIONS = ["核心思想", "可迁移到", "案例", "何时不用", "对照问题"]


def parse_frontmatter(text: str):
    """解析 YAML frontmatter 的顶层 key（只取 `key: value` 形式，不解析嵌套）。"""
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    block = text[3:end]
    keys = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        idx = line.find(":")
        if idx > 0:
            keys.append(line[:idx].strip())
    return keys


def classify_entry(path: Path, root: Path | None) -> str:
    """判定条目类型：framework / model / pattern。

    只看**相对知识根的路径段**（精确相等），不做整条路径的子串匹配——
    否则知识库放在上层目录名含 "patterns"/"models" 的项目里（如 my-patterns-dir/）
    时，全部条目都会被误判成另一种类型，产生假 FAIL。
    """
    if root is not None:
        try:
            rel = path.resolve().relative_to(root.resolve())
            parts = [p for p in rel.parts if p not in (".", "")]
            # 目录段精确命中即认定（支持 patterns/、patterns/x/、core/models/ 等布局）
            for seg in parts[:-1]:
                if seg == "patterns":
                    return "pattern"
                if seg == "models":
                    return "model"
                if seg == "frameworks":
                    return "framework"
        except (ValueError, OSError):
            pass  # 条目不在 root 下（如单文件模式），退回全路径判定
    # 退化路径：按路径段精确匹配，而非子串包含
    parts = {p for p in path.resolve().parts}
    if "patterns" in parts:
        return "pattern"
    if "models" in parts:
        return "model"
    return "framework"


def lint_file(path: Path, root: Path | None = None) -> list:
    problems = []
    text = path.read_text(encoding="utf-8")
    keys = parse_frontmatter(text) or []
    kind = classify_entry(path, root)
    is_pattern = kind == "pattern"
    is_model = kind == "model"

    required = PATTERN_KEYS if is_pattern else (MODEL_KEYS if is_model else FRAMEWORK_KEYS)
    for key in required:
        if key not in keys:
            problems.append(f"frontmatter 缺字段: {key}")

    if is_model:
        for marker in MODEL_SECTIONS:
            if marker not in text:
                problems.append(f"缺小节「{marker}」")

    if is_pattern:
        sections = [ln for ln in text.splitlines() if ln.startswith("### ")]
        if not sections:
            problems.append("未找到任何 `### ` 模式小节")
        for sec in sections:
            title = sec[4:].strip()
            start = text.find(sec)
            nxt = text.find("\n### ", start + 1)
            body = text[start:nxt] if nxt != -1 else text[start:]
            for marker in PATTERN_SECTIONS:
                if marker not in body:
                    problems.append(f"小节「{title}」缺「{marker}」")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="知识条目结构校验（默认严格：有问题即退出码 1）")
    ap.add_argument("target", help="知识库目录或单个条目文件")
    ap.add_argument("--strict", action="store_true",
                    help="存在任一问题即以退出码 1 结束（向后兼容；当前等同默认行为）")
    ap.add_argument("--lenient", action="store_true",
                    help="宽松模式：存在问题也返回 0，仅作提示不卡门禁")
    args = ap.parse_args()

    target = Path(args.target).expanduser().resolve()
    files = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(p for p in target.rglob("*.md") if p.name != "index.md")
    else:
        raise SystemExit(f"路径不存在: {target}")

    total = 0
    # 目录模式：root = 目标目录，条目类型按相对路径段判定
    # 单文件模式：root = 文件所在目录的上级（references/knowledge），保证相对判定可用
    lint_root = target if target.is_dir() else target.parent.parent
    for f in files:
        problems = lint_file(f, root=lint_root)
        rel = f.name
        if problems:
            total += len(problems)
            print(f"[FAIL] {rel}")
            for p in problems:
                print(f"       - {p}")
        else:
            print(f"[OK]   {rel}")

    print(f"\n共 {len(files)} 个条目，{total} 个问题")
    if total == 0:
        return 0
    print("结论: 存在问题，需补齐上表列出的字段 / 小节")
    if args.lenient:
        if args.strict:
            print("（同时给了 --strict 与 --lenient：以 --lenient 为准，退出码 0）")
        else:
            print("（--lenient：已按宽松模式放行，退出码 0；门禁须去掉本参数）")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
