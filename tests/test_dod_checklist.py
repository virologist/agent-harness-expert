"""P3-3：coder DoD 清单 + tester 核验引用 — 最小验证集。

3 个用例：
  1) coder.md 存在「DoD 清单」节（防节标题被改/被删）
  2) tester.md 显式引用 coder.md 的 DoD 节（防 P3 开工核验被删）
  3) coder.md 的 9 条 DoD 条款都能在文件里 grep 到（防条款漂移/被删）

读 md 文件用 grep 风格的字符串包含断言，不解析 markdown AST——
比 AST 简单、比「文件存在」严格。
"""
from __future__ import annotations

from pathlib import Path

from _harness import contains, eq, is_true

REPO_ROOT = Path(__file__).resolve().parents[1]
CODER_MD = REPO_ROOT / "agents" / "agent-harness-coder.md"
TESTER_MD = REPO_ROOT / "agents" / "agent-harness-tester.md"


# 9 条 DoD 条款的唯一锚点短语——每条都设计成在该文件其它节不易自然出现的字串。
# 测试用「子串包含」匹配，与 _harness.contains 一致；任一缺失即视为条款漂移。
DOD_ANCHORS = [
    "代码真实可运行",                                              # 1
    "启动命令 + 入口可执行 + 启动日志无致命错误",                  # 2
    "happy path 真实调用",                                         # 3
    "错误路径用例",                                                # 4
    "改动只保留任务相关",                                          # 5
    "内容含义用 LLM 原生能力",                                     # 6
    "写操作幂等",                                                  # 7
    "凭证不进仓库",                                                # 8
    "不在 coder 阶段新建 `04-test/` 目录",                        # 9
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_coder_md_has_dod_section():
    """coder.md 必须存在「DoD 清单」节（标题级）。"""
    is_true(CODER_MD.is_file(), f"coder agent 文件应存在: {CODER_MD}")
    text = _read(CODER_MD)
    contains(text, "## DoD 清单", "coder.md 应含「DoD 清单」二级节标题")
    # 节标题末尾的修饰语不强约束（防「(Subhead)」被改动就破测试），但要求是 ## 层级
    eq(sum(1 for ln in text.splitlines() if ln.startswith("## DoD 清单")), 1,
       "「DoD 清单」二级节应唯一出现一次")


def test_tester_md_references_coder_dod():
    """tester.md 必须显式引用 coder.md 的 DoD 节（路径+节名双锚点）。"""
    is_true(TESTER_MD.is_file(), f"tester agent 文件应存在: {TESTER_MD}")
    text = _read(TESTER_MD)
    # 双锚点：路径引用 + 节名引用（任一缺失即视为引用被弱化）
    contains(text, "agent-harness-coder.md",
             "tester.md 应引用 coder.md 文件路径")
    contains(text, "DoD 清单",
             "tester.md 应出现「DoD 清单」字样")
    # 且应说明这是 P3 开工的前置门（防止"加了但是语义被改"）
    contains(text, "P3 阶段开工",
             "tester.md 应在 P3 阶段开工语境里引用 DoD")


def test_coder_md_dod_items_all_present():
    """9 条 DoD 条款锚点必须都能在 coder.md 里 grep 到——防条款漂移/被删。"""
    text = _read(CODER_MD)
    missing = [anchor for anchor in DOD_ANCHORS if anchor not in text]
    eq(missing, [],
       f"coder.md DoD 清单缺失以下条款锚点（条款漂移/被删）: {missing}\n"
       f"——若确需修改条款，请同步更新本测试的 DOD_ANCHORS 列表并加 commit 说明 WHY。")