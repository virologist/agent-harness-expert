"""parse_raw.py — 多格式解析 → 干净 markdown（带 §章节 锚点，供页面标注来源）

支持格式:
    .pdf  .docx .doc(best-effort)  .xlsx .xls  .csv
    .pptx .md .markdown .txt .json .html/.htm

用法:
    python parse_raw.py <file> [-o/--output <path>]

参数:
    file            要解析的 raw 文件路径（必填）
    -o, --output    输出到文件（utf-8）；不指定则输出到 stdout

依赖（按需安装，缺失会优雅降级而非崩溃）:
    pip install pypdf openpyxl python-docx python-pptx beautifulsoup4 xlrd
    旧版 .doc/.xls 需要：xlrd（.xls）；.doc 若系统装有 LibreOffice(soffice/libreoffice)
    会自动转 txt 获得最佳质量，否则做可读文本抢救(salvage)并标注"降级"。

解析质量会在输出头部标注：`完整` 或 `降级(<原因>)`，便于 LLM 判断可信度。
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Windows 默认 stdout 可能是 GBK，强制 utf-8，避免 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _try_import(name: str):
    try:
        return __import__(name)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# 各格式解析器（返回 "正文"；异常由 parse() 统一兜底）
# ---------------------------------------------------------------------------

def parse_pdf(path: Path) -> str:
    pypdf = _try_import("pypdf")
    if pypdf is None:
        return _degraded(path, "pypdf 未安装")
    reader = pypdf.PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        parts.append(f"## §page-{i}\n\n{text}\n")
    return "\n".join(parts) or _degraded(path, "PDF 无可提取文本（可能是扫描件，需 OCR）")


def parse_xlsx(path: Path) -> str:
    openpyxl = _try_import("openpyxl")
    if openpyxl is None:
        return _degraded(path, "openpyxl 未安装")
    wb = openpyxl.load_workbook(str(path), data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"## §sheet-{sheet.title}\n")
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        header = list(rows[0])
        parts.append("| " + " | ".join(_cell(c) for c in header) + " |")
        parts.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows[1:]:
            cells = list(row) + [None] * (len(header) - len(row))
            parts.append("| " + " | ".join(_cell(c) for c in cells[: len(header)]) + " |")
        parts.append("")
    return "\n".join(parts)


def parse_xls(path: Path) -> str:
    """旧版 .xls 走 xlrd（openpyxl 明确不支持 .xls）。"""
    xlrd = _try_import("xlrd")
    if xlrd is None:
        return _office_fallback(path, "xlrd 未安装（.xls 需要 xlrd）")
    wb = xlrd.open_workbook(str(path))
    parts = []
    for sh in wb.sheets():
        parts.append(f"## §sheet-{sh.name}\n")
        if sh.nrows == 0:
            continue
        header = [sh.cell_value(0, c) for c in range(sh.ncols)]
        parts.append("| " + " | ".join(_cell(c) for c in header) + " |")
        parts.append("|" + "|".join("---" for _ in header) + "|")
        for r in range(1, sh.nrows):
            cells = [sh.cell_value(r, c) for c in range(sh.ncols)]
            parts.append("| " + " | ".join(_cell(c) for c in cells) + " |")
        parts.append("")
    return "\n".join(parts) or _degraded(path, "xls 无数据")


def parse_csv(path: Path) -> str:
    parts = ["## §table\n"]
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return _degraded(path, "CSV 为空")
    header = rows[0]
    parts.append("| " + " | ".join(_escape_pipe(h) for h in header) + " |")
    parts.append("|" + "|".join("---" for _ in header) + "|")
    for row in rows[1:]:
        cells = list(row) + [""] * (len(header) - len(row))
        parts.append("| " + " | ".join(_escape_pipe(c) for c in cells[: len(header)]) + " |")
    parts.append("")
    return "\n".join(parts)


def parse_docx(path: Path) -> str:
    docx = _try_import("docx")
    if docx is None:
        return _office_fallback(path, "python-docx 未安装")
    try:
        doc = docx.Document(str(path))
    except Exception as e:
        # 常见：把旧 .doc 或其它二进制改名为 .docx；转降级通道
        return _office_fallback(path, f"python-docx 无法解析（{e}）")
    parts = []
    section_idx = 0
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style and para.style.name.startswith("Heading"):
            section_idx += 1
            parts.append(f"## §heading-{section_idx} {text}\n")
        else:
            parts.append(text)
    # 段落之外，表格/文本框内容也尽量抽取
    for ti, table in enumerate(getattr(doc, "tables", []), 1):
        parts.append(f"\n## §table-{ti}\n")
        for row in table.rows:
            cells = [_escape_pipe(c.text.replace("\n", " ")) for c in row.cells]
            parts.append("| " + " | ".join(cells) + " |")
    return "\n".join(parts) or _degraded(path, "docx 无文本")


def parse_doc(path: Path) -> str:
    """旧版二进制 .doc：优先 LibreOffice 转 txt（高质量），否则可读文本抢救。"""
    return _office_fallback(path, "旧版 .doc（非 docx）")


def parse_pptx(path: Path) -> str:
    pptx = _try_import("pptx")
    if pptx is None:
        return _office_fallback(path, "python-pptx 未安装")
    try:
        prs = pptx.Presentation(str(path))
    except Exception as e:
        return _office_fallback(path, f"python-pptx 无法解析（{e}）")
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        parts.append(f"## §slide-{i}\n")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        parts.append(t)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [_escape_pipe(c.text.replace("\n", " ")) for c in row.cells]
                    parts.append("| " + " | ".join(cells) + " |")
        parts.append("")
    return "\n".join(parts) or _degraded(path, "pptx 无文本")


def parse_html(path: Path) -> str:
    bs4 = _try_import("bs4")
    if bs4 is None:
        return _fallback_text(path, "beautifulsoup4 未安装")
    soup = bs4.BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    body = "\n".join(lines)
    return ("## §html-body\n\n" + body) if body else _degraded(path, "html 无文本")


def parse_json(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    return f"## §json\n\n```json\n{raw.strip()}\n```\n"


def parse_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    out = []
    sec = 0
    for ln in lines:
        if ln.lstrip().startswith("#"):
            sec += 1
            out.append(f"## §heading-{sec} {ln.lstrip('#').strip()}\n")
        else:
            out.append(ln)
    body = "\n".join(out)
    if sec == 0:  # 无任何标题 → 用单一 §raw 锚点，保证来源可定位
        body = "## §raw\n\n" + body
    return body


# ---------------------------------------------------------------------------
# 降级 / 抢救通道（任何解析失败都走这里，绝不只丢一句异常）
# ---------------------------------------------------------------------------

def _cell(v) -> str:
    if v is None:
        return ""
    return _escape_pipe(str(v).replace("\n", " "))


def _escape_pipe(s: str) -> str:
    return str(s).replace("|", "\\|")


def _salvage_text(path: Path) -> str:
    """从二进制文件里抢救可读文本：分别按 utf-8 与 utf-16le 解码，取信息量更高的一路。"""
    data = path.read_bytes()

    def printable_runs(s: str) -> str:
        # 保留字母/数字/中日韩/常见标点/空白，丢弃控制字符与替换符
        keep = re.findall(
            r"[\u4e00-\u9fff\u3000-\u303fA-Za-z0-9，。、；：？！（）《》【】\-_/\\.,:;!?()\[\]'\" \t]+",
            s,
        )
        return "\n".join(run for run in (k.strip() for k in keep) if len(run) >= 2)

    cand_utf8 = printable_runs(data.decode("utf-8", errors="ignore"))
    cand_utf16 = printable_runs(data.decode("utf-16-le", errors="ignore"))
    def score(s):
        return sum(c.isalnum() or "\u4e00" <= c <= "\u9fff" for c in s)
    best = cand_utf16 if score(cand_utf16) > score(cand_utf8) else cand_utf8
    return best.strip()


def _libreoffice_to_text(path: Path) -> "str | None":
    """若系统装有 LibreOffice，用 headless 转 txt（最佳质量）。失败返回 None。"""
    exe = None
    for name in ("soffice", "libreoffice"):
        if shutil.which(name):
            exe = name
            break
    if exe is None:
        return None
    try:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                [exe, "--headless", "--convert-to", "txt:Text", "--outdir", td, str(path)],
                check=False, capture_output=True, timeout=120,
            )
            produced = Path(td) / (path.stem + ".txt")
            if produced.exists():
                txt = produced.read_text(encoding="utf-8", errors="ignore").strip()
                if txt:
                    return txt
    except Exception:
        return None
    return None


def _degraded(path: Path, reason: str) -> str:
    """降级标记：正文用抢救文本，头部注明降级原因（由 parse() 拼最终 header）。"""
    salvaged = _salvage_text(path)
    note = f"（降级：{reason}；以下为可读文本抢救，可能不完整）"
    body = salvaged if salvaged else "（未能抢救出可读文本）"
    return f"## §raw\n\n{note}\n\n{body}\n"


def _office_fallback(path: Path, reason: str) -> str:
    """Office 类文件的兜底：先试 LibreOffice 转 txt，再退到二进制文本抢救。"""
    lo = _libreoffice_to_text(path)
    if lo is not None:
        return f"## §doc-converted\n\n（经 LibreOffice 转换；原始降级原因：{reason}）\n\n{lo}\n"
    return _degraded(path, reason)


def _fallback_text(path: Path, reason: str) -> str:
    try:
        return f"## §raw\n\n（降级：{reason}）\n\n" + path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"## §raw\n\n（降级：{reason}；读取失败：{e}）\n"


PARSERS = {
    ".pdf": parse_pdf,
    ".xlsx": parse_xlsx,
    ".xls": parse_xls,
    ".csv": parse_csv,
    ".docx": parse_docx,
    ".doc": parse_doc,
    ".pptx": parse_pptx,
    ".html": parse_html,
    ".htm": parse_html,
    ".md": parse_text,
    ".markdown": parse_text,
    ".txt": parse_text,
    ".json": parse_json,
}

# 这些扩展名解析失败时走"办公兜底(LibreOffice→salvage)"，其余走纯文本兜底
_OFFICE_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".pptx", ".ppt"}


def parse(path: Path) -> str:
    ext = path.suffix.lower()
    parser = PARSERS.get(ext, parse_text)
    degraded = False
    try:
        content = parser(path)
        if content.lstrip().startswith("## §raw") and ("降级" in content[:200]):
            degraded = True
        if content.startswith("## §doc-converted"):
            degraded = True
    except Exception as e:
        if ext in _OFFICE_EXTS:
            content = _office_fallback(path, f"解析异常：{e}")
        else:
            content = _fallback_text(path, f"解析异常：{e}")
        degraded = True

    quality = "降级" if degraded else "完整"
    header = (
        f"# 源文件：{path.name}\n\n"
        f"> 路径：{path.name}\n> 解析器：{ext or '未知(按纯文本)'}\n> 解析质量：{quality}\n\n"
    )
    return header + content


def main() -> int:
    parser = argparse.ArgumentParser(description="解析 raw 文件 → 干净 markdown（带 §锚点）")
    parser.add_argument("file", help="raw 文件路径")
    parser.add_argument("-o", "--output", help="输出到文件（utf-8）；不指定则输出到 stdout")
    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()
    if not path.exists():
        print(f"错误：文件不存在 {path}", file=sys.stderr)
        return 1

    content = parse(path)
    if args.output:
        Path(args.output).write_text(content, encoding="utf-8")
        print(f"已写入 {args.output}（{len(content)} 字符）", file=sys.stderr)
    else:
        print(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
