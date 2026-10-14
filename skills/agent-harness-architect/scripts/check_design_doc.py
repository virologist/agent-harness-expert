#!/usr/bin/env python3
"""设计文档结构自检（schema 校验：已知结构 -> 确定结果）。

只报"缺什么"，不判断"该不该缺"——要不要补由 LLM/架构师决定。

用法:
    python3 check_design_doc.py designs/支付助手-harness-design-v1.md
"""
import argparse
import re
from pathlib import Path

HEADINGS = [
    "需求规格", "架构范式 P", "技术栈选型", "六层设计", "模型组合与任务分派", "多 Agent 编排",
    "模块 / 目录结构", "关键接口签名", "核心数据结构", "配置文件格式",
    "层间交叉检查", "六层决策表", "生产级必答项", "参考架构图", "遗留问题与未知区",
]

# 生产级必答项（与 assets/design-doc.md §13 一致）+ 模型组合（§5）
MUST_ANSWER = [
    "执行环境", "错误回喂", "打转检测", "记忆治理", "幂等", "版本绑定", "评估者分离",
    "模型组合", "前缀稳定",
]

# 「可编码三门槛」（类型完整 / API 真实 / 标准可达）的唯一定义处是
# references/production-checklist.md。三门槛判定的是**内容质量**（类型有没有定义、
# API 是否真实、标准能否验证），属于语义判断，按三件事分工宪法归LLM，不做脚本化。
# 脚本只做它能确定的事：§13 每一行是否真的填了结论。
GATE_POINTER = "类型完整 / API 真实 / 标准可达（唯一定义处：references/production-checklist.md）"

# §13 生产级必答项的编号行，检测「表还在但结论列全空」这种结构性缺失
_ANSWER_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|")


# 已被文档规范占用的合法记号：出现这些形态时不算"未填占位符"
#   - HTML/SVG 标签：<div> <T> <name> <your-key>
#   - 泛型 / 类型参数：List<String>、Dict<K, V>、Promise<T>
#   - 比较与数学：a < b、x <= 1、n < 10
_ALLOWED_TAG = re.compile(
    r"^<[A-Za-z_][A-Za-z0-9_.:\-]*(?:\s*/?)?>$"      # <div> <T> <my-key> </span>
)
_TOLDF_SLOT = re.compile(r"^<[^<>\n]{1,60}>$")
# `<` 左侧紧邻这些字符时，几乎必然是比较运算或泛型（a<b、List<T>、x<=1）
_IDENT_CHAR_BEFORE = re.compile(r"[A-Za-z0-9_)\]]$")
# 形似标签但实为占位符的常见缩写（TBD / TODO / FIXME / XXX）
_TODO_LIKE = re.compile(r"^<(?:TBD|TODO|FIXME|XXX|N/A|N/T)>$", re.IGNORECASE)


def _is_placeholder_token(tok: str, line_prefix: str) -> bool:
    """判断单个 <...> 记号是否为未填占位符。

    line_prefix 是该记号在同一行左侧的原文，用于识别比较运算 / 泛型场景。
    """
    if not _TOLDF_SLOT.match(tok):
        return False
    if _TODO_LIKE.match(tok):
        return True
    if _ALLOWED_TAG.match(tok):
        return False
    # 比较运算或泛型：a < b、x <= 1、List<String>
    if _IDENT_CHAR_BEFORE.search(line_prefix):
        return False
    return True


def find_placeholders(body: str) -> list:
    """返回正文中疑似未填的占位符列表（已排除代码围栏内的合法尖括号）。

    判定策略：逐个 <...> 记号看其**行内左侧上下文**——
    左侧紧邻标识符字符 → 判为比较运算/泛型，放行；
    记号本身是合法标签形态 → 放行；
    其余（左侧为空白/冒号/行首，形如 <待填> <your field> <TBD>）→ 判为未填占位符。
    """
    found = []
    for line in body.splitlines():
        for m in re.finditer(r"<[^<>\n]{1,60}>", line):
            if _is_placeholder_token(m.group(0), line[: m.start()]):
                found.append(m.group(0))
    return found


def _strip_fenced(text: str) -> str:
    """去掉 ``` 围栏代码块内容（占位符检测不看代码块内合法尖括号）。"""
    out, in_fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def find_unanswered(body: str) -> list:
    """返回 §13 生产级必答项里「有编号但结论列为空」的条目。

    只判**结构**（表还在、行还在、结论没写），不判内容质量——
    「结论写得够不够」归LLM，按三件事分工宪法不做规则匹配。
    """
    unanswered = []
    for line in body.splitlines():
        m = _ANSWER_ROW.match(line.strip())
        if not m:
            continue
        num, item, conclusion = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        # 跳过表头行与分隔行（表头形如| # | 必答项 | 结论 |）
        if not num.isdigit():
            continue
        if not conclusion:
            unanswered.append(f"§13 第 {num} 项「{item or '未命名'}」未填结论")
    return unanswered


def check(path: Path) -> tuple:
    if not path.is_file():
        raise SystemExit(f"文件不存在: {path}")
    text = path.read_text(encoding="utf-8")

    missing_h = [h for h in HEADINGS if h not in text]
    missing_m = [m for m in MUST_ANSWER if m not in text]
    has_ledger = "设计台账" in text
    body = _strip_fenced(text)
    placeholders = find_placeholders(body)
    unanswered = find_unanswered(body)
    return missing_h, missing_m, has_ledger, unanswered, placeholders


def main() -> int:
    ap = argparse.ArgumentParser(description="设计文档结构自检")
    ap.add_argument("doc", help="设计文档路径")
    ap.add_argument("--strict", action="store_true", help="存在任一项缺失即以退出码 1 结束")
    args = ap.parse_args()

    missing_h, missing_m, has_ledger, unanswered, placeholders = check(Path(args.doc).expanduser().resolve())

    print(f"检查对象: {Path(args.doc).resolve()}")
    print(f"  章节齐全度: {len(HEADINGS) - len(missing_h)}/{len(HEADINGS)}")
    if missing_h:
        print(f"    缺章节: {', '.join(missing_h)}")
    print(f"  生产级必答项: {len(MUST_ANSWER) - len(missing_m)}/{len(MUST_ANSWER)}")
    if missing_m:
        print(f"    未出现: {', '.join(missing_m)}")
    if unanswered:
        print(f"  §13 必答项结论空缺: {len(unanswered)} 处")
        for u in unanswered:
            print(f"    - {u}")
    else:
        print("  §13 必答项结论空缺: 无")
    print(f"  设计台账行: {'有' if has_ledger else '缺'}")
    # 去重保序，最多列 10 个，避免刷屏
    uniq = list(dict.fromkeys(placeholders))
    print(f"  未填占位符 <...>: {'有，需补写 ' + str(len(uniq)) + ' 处 → ' + ', '.join(uniq[:10]) if uniq else '无'}")
    print(f"  语义项（脚本不判，需你自查）: {GATE_POINTER}")

    problems = bool(missing_h or missing_m or unanswered or not has_ledger)
    if problems and args.strict:
        return 1
    print("结论: " + ("存在缺失项，需人工判断是否补齐" if problems else "结构完整"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
