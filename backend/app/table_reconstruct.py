"""把 PaddleOCR 的文字框（含 bbox）幾何重建成表格 {columns, rows}。

核心想法：遠端 OCR 只回傳壓平的文字、欄位資訊全失；本地 PaddleOCR 有每塊
文字的座標，於是可用幾何把欄位拼回來——這能正確還原雙欄（左資產／右負債）
版面，修正「數字填錯欄」。流程：
  1. 以「數值框」中心分群定出數值欄錨點（右對齊、最穩定的格線）。
  2. 以「非數值框」左緣分群定出標籤欄錨點，且須與數值欄不重疊。
  3. 依 y 座標把框分群成列；每列每欄把框依 x 串接成儲存格。
"""
from __future__ import annotations

import re

_NUM = re.compile(r"^[\$\(\)\-—一,\.%\d\s]+$")
_DOLLAR = {"$", "S", "s", "＄"}


def _is_value(t: str) -> bool:
    t = t.strip()
    return (bool(t) and bool(_NUM.match(t)) and any(c.isdigit() for c in t)) or t in ("一", "—", "-")


def _cluster(vals: list[int], gap: int) -> list[tuple[float, int]]:
    """1D 分群：相鄰差 <= gap 視為同群。回傳 (中心, 群大小)。"""
    vals = sorted(vals)
    cl: list[list[int]] = [[vals[0]]]
    for v in vals[1:]:
        if v - cl[-1][-1] <= gap:
            cl[-1].append(v)
        else:
            cl.append([v])
    return [(sum(c) / len(c), len(c)) for c in cl]


def reconstruct(boxes: list[dict]) -> dict:
    """boxes -> {"columns": [], "rows": [[cell,...], ...]}。"""
    boxes = [b for b in boxes if (b.get("text") or "").strip()]
    if not boxes:
        return {"columns": [], "rows": []}
    W = max(b["x1"] for b in boxes)

    # 1. 數值欄錨點（出現 >=2 次的群）。只用「含阿拉伯數字、且信心 >=0.7」的框定錨點：
    #    - 排除破折號（一／–／-）：散布各 x，會把相鄰數字欄誤併。
    #    - 排除低信心雜訊框（如夾在兩欄間的誤判「1」）：會橋接相鄰欄、漏掉中間欄
    #      （例：普通股股本 與 資本公積 之間一個 0.6 分的「1」把兩欄併成一欄）。
    #    低信心框仍會在下方被「指派」到最近欄、不會遺失，只是不參與定欄。
    vcx = [b["cx"] for b in boxes
           if _is_value(b["text"]) and any(ch.isdigit() for ch in b["text"])
           and b.get("score", 1.0) >= 0.7]
    vcols = [c for c, n in _cluster(vcx, int(W * 0.045)) if n >= 2] if vcx else []

    # 2. 標籤欄錨點（非數值框左緣，>=3 次，且距任一數值欄 > 5%W）
    lx0 = [b["x0"] for b in boxes if not _is_value(b["text"])]
    lcand = [(c, n) for c, n in _cluster(lx0, int(W * 0.05)) if n >= 3] if lx0 else []
    lcols = [c for c, n in lcand if all(abs(c - v) > W * 0.05 for v in vcols)]

    cols = sorted([("L", c) for c in lcols] + [("V", c) for c in vcols], key=lambda t: t[1])
    if not cols:  # 全是雜訊 → 退化為每框一列
        rows = [[b["text"]] for b in sorted(boxes, key=lambda b: (b["cy"], b["cx"]))]
        return {"columns": [], "rows": rows}
    pos = [c[1] for c in cols]
    n = len(cols)

    def col_of(b: dict) -> int:
        key = b["x0"] if not _is_value(b["text"]) else b["cx"]
        return min(range(n), key=lambda i: abs(pos[i] - key))

    # 3. 列分群（y 容差 = 0.6 × 中位框高）
    hs = sorted(b["y1"] - b["y0"] for b in boxes)
    mh = hs[len(hs) // 2]
    tol = max(8, int(mh * 0.6))
    bs = sorted(boxes, key=lambda b: b["cy"])
    rows_b: list[list[dict]] = []
    cur: list[dict] = []
    cy = None
    for b in bs:
        if cy is None or abs(b["cy"] - cy) <= tol:
            cur.append(b)
            cy = b["cy"] if cy is None else (cy * (len(cur) - 1) + b["cy"]) / len(cur)
        else:
            rows_b.append(cur)
            cur = [b]
            cy = b["cy"]
    if cur:
        rows_b.append(cur)

    # 4. 組格
    grid: list[list[str]] = []
    for r in rows_b:
        cells = [""] * n
        buckets: dict[int, list[dict]] = {}
        for b in r:
            buckets.setdefault(col_of(b), []).append(b)
        for c, items in buckets.items():
            items.sort(key=lambda b: b["x0"])
            cells[c] = " ".join(it["text"] for it in items).strip()
        grid.append(cells)

    grid = _merge_dollar_columns(grid)
    grid = _drop_empty_columns(grid)
    return {"columns": [], "rows": grid}


def _merge_dollar_columns(grid: list[list[str]]) -> list[list[str]]:
    """把「只含 $/S」的欄併入右邊那一欄（$ 應黏在金額前）。"""
    if not grid:
        return grid
    n = len(grid[0])
    keep = [True] * n
    for c in range(n - 1):
        col_vals = [row[c].strip() for row in grid]
        nonempty = [v for v in col_vals if v]
        if nonempty and all(v in _DOLLAR for v in nonempty):
            for row in grid:
                if row[c].strip():
                    row[c + 1] = (row[c].strip() + " " + row[c + 1]).strip()
                    row[c] = ""
            keep[c] = False
    return [[row[c] for c in range(n) if keep[c]] for row in grid]


def _drop_empty_columns(grid: list[list[str]]) -> list[list[str]]:
    if not grid:
        return grid
    n = len(grid[0])
    keep = [any(row[c].strip() for row in grid) for c in range(n)]
    return [[row[c] for c in range(n) if keep[c]] for row in grid]


def grid_to_text(grid: dict) -> str:
    """把 {columns, rows} 攤平成 tab 分隔文字（供步驟2 唯讀文字檢視）。"""
    rows = grid.get("rows") or []
    return "\n".join("\t".join(cell for cell in row).rstrip("\t") for row in rows)
