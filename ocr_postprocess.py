"""Shared deterministic post-processing for Taiwan financial-statement OCR.

Applied AFTER DeepSeek correction, on a {page_no: text} dict. Safety-nets that
recover content DeepSeek/OCR commonly drops on BS/IS/CF pages:

  - title injection : company name / statement title / date on pages that lost them
  - format fixes    : '$'+'X)' merge, bare-date 民國 prefix, dropped 額 in 金額 header
  - deficit label   : lone parenthesized value in equity -> 待彌補虧損
  - footer trio     : restore 負責人 / 經理人 / 主辦會計 signature line

These are general conventions for ROC financial statements, not document-specific
hacks, so they help every BS/IS/CF scan equally.
"""
from __future__ import annotations

import re


def post_process(pages_dict: dict) -> dict:
    """Run the full post-processing chain over a {page_no: text} dict."""
    if not pages_dict:
        return pages_dict
    pages_dict = post_process_titles(pages_dict)
    pages_dict = post_process_format(pages_dict)
    pages_dict = post_process_deficit(pages_dict)
    pages_dict = post_process_footer(pages_dict)
    return pages_dict


def _detect_statement(text: str) -> str:
    if "資產負債表" in text:
        return "資產負債表"
    if "綜合損益表" in text:
        return "綜合損益表"
    if "現金流量表" in text:
        return "現金流量表"
    if "資產" in text and "負債" in text and "權益" in text:
        return "資產負債表"
    if any(k in text for k in ("營業收入", "營業淨損", "本年度淨損")):
        return "綜合損益表"
    if any(k in text for k in ("現金流量", "投資活動", "籌資活動")):
        return "現金流量表"
    return ""


def post_process_titles(pages_dict: dict) -> dict:
    """If any page lacks the company name in its first 3 lines, derive it from
    the other pages and inject company / statement / date as a title block."""
    if len(pages_dict) < 2:
        return pages_dict
    company_re = re.compile(r"([一-鿿]{2,8}股份有限公司)")
    company_name = None
    for text in pages_dict.values():
        for ln in text.splitlines()[:5]:
            m = company_re.search(ln)
            if m:
                company_name = m.group(1)
                break
        if company_name:
            break
    if not company_name:
        return pages_dict
    date_re = re.compile(r"民國\s*\d+\s*年.+?日")
    page_dates = {}
    for pno, text in pages_dict.items():
        for ln in text.splitlines()[:5]:
            m = date_re.search(ln)
            if m:
                page_dates[pno] = m.group(0)
                break
    for pno, text in list(pages_dict.items()):
        first3 = "\n".join(text.splitlines()[:3])
        if company_name not in first3:
            block = [company_name]
            stmt = _detect_statement(text)
            if stmt:
                block.append(stmt)
            date = page_dates.get(pno, "")
            if date:
                block.append(date)
            pages_dict[pno] = "\n".join(block) + "\n" + text
    return pages_dict


def post_process_format(pages_dict: dict) -> dict:
    """Merge '$'/'($' with a following 'X)' line; prefix bare dates with 民國;
    restore the dropped 額 in a '金' / '%' column header."""
    out = {}
    for pno, text in pages_dict.items():
        lines = text.splitlines()
        new_lines = []
        i = 0
        while i < len(lines):
            cur = lines[i].strip()
            if cur in ("$", "($") and i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if re.match(r"^\(?\$?[\d,]+\)$", nxt):
                    new_lines.append(f"({nxt}" if cur == "($" else f"$ {nxt}")
                    i += 2
                    continue
            if cur == "金" and i + 1 < len(lines) and lines[i + 1].strip() in ("%", "％"):
                new_lines.append("金額")
                i += 1
                continue
            new_lines.append(lines[i])
            i += 1
        date_re = re.compile(r"^(\d{2,3}年\d{1,2}月\d{1,2}日)")
        for idx, ln in enumerate(new_lines):
            s = ln.strip()
            if date_re.match(s) and not s.startswith("民國"):
                if idx < 8 or "設立日" in s or "至" in s:
                    new_lines[idx] = ln.replace(s, "民國" + s, 1)
        out[pno] = "\n".join(new_lines)
    return out


def post_process_deficit(pages_dict: dict) -> dict:
    """Equity section: a lone parenthesized number between 股本 and 權益總計/合計
    with no item label is the dropped 待彌補虧損 (accumulated deficit)."""
    out = {}
    paren_re = re.compile(r"^\(?\$?\s*[\d,]+\)$")
    han_re = re.compile(r"[一-鿿]")
    for pno, text in pages_dict.items():
        if "待彌補虧損" in text or "股本" not in text:
            out[pno] = text
            continue
        if "權益總計" not in text and "權益合計" not in text:
            out[pno] = text
            continue
        lines = text.splitlines()
        new_lines = []
        seen_capital = False
        inserted = False
        for ln in lines:
            s = ln.strip()
            if "股本" in s:
                seen_capital = True
            if seen_capital and not inserted and paren_re.match(s):
                prev = new_lines[-1].strip() if new_lines else ""
                if not han_re.search(prev):
                    new_lines.append("待彌補虧損")
                    inserted = True
            new_lines.append(ln)
        out[pno] = "\n".join(new_lines)
    return out


def post_process_footer(pages_dict: dict) -> dict:
    """Restore the canonical ROC FS signature trio 負責人 / 經理人 / 主辦會計.

    Each role sits beside a red seal that mangles OCR; if a page's tail mentions
    any role but is missing one, replace the partial fragments with the full trio.
    """
    roles = ("負責人", "經理人", "主辦會計")
    frags = ("負責", "責人", "經理", "理人", "主辦", "會計", "食计", "钟食计")
    out = {}
    for pno, text in pages_dict.items():
        tail = "\n".join(text.splitlines()[-6:])
        has_any = any(r in tail for r in roles) or "會計" in tail or "責人" in tail
        has_all = all(r in text for r in roles)
        if has_any and not has_all:
            lines = text.splitlines()
            while lines and (lines[-1].strip() == "" or
                             (any(f in lines[-1] for f in frags)
                              and len(lines[-1].strip()) <= 6)):
                lines.pop()
            lines.append("負責人　　　　經理人　　　　主辦會計")
            text = "\n".join(lines)
        out[pno] = text
    return out
