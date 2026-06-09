# 選頁辨識（Page Selection OCR）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓使用者在辨識前挑選特定頁，只對選到的頁執行完整辨識管線（渲染／前處理／OCR／LLM 校正皆只跑選到的頁），輸出保留原始頁碼。

**Architecture:** 方案 A——選頁清單一路傳進引擎逐頁迴圈，未選頁在 `get_pixmap` 前跳過。掃描檔 OCR 回來是位置編號（1..M），辨識後做一次「位置→原始頁碼」回填；文字層檔直接以原始 key 過濾。前端以單一 `selected` 狀態同步「縮圖打勾」與「頁碼輸入」。

**Tech Stack:** Backend：FastAPI、PyMuPDF（`fitz`）、Pillow、pytest。Frontend：React + Vite + TypeScript、vitest。

**設計依據：** `docs/superpowers/specs/2026-06-09-page-selection-ocr-design.md`

---

## 檔案結構

| 檔案 | 動作 | 責任 |
|---|---|---|
| `ocr_lib.py` | 修改 `iter_hidpi` | 接受 `pages` 過濾、yield `(page_no, image)` |
| `ocr_recognize.py` | 修改 `recognize` + 新增 `_remap_to_original` | 選頁過濾（兩路線）＋ 掃描檔頁碼回填 |
| `backend/app/engine.py` | 修改 `recognize` | 透傳 `pages` |
| `backend/app/jobs.py` | 修改 `Job` / `start_recognition` / `_run` | 帶 `pages` 進背景任務、存於 Job |
| `backend/app/schemas.py` | 新增 `RecognizeRequest` | `/recognize` 請求模型 |
| `backend/app/main.py` | 修改 `recognize` 端點 | 收選頁、驗證、正規化 |
| `backend/tests/test_page_selection.py` | 新建 | 引擎過濾 + 回填 + 端點驗證測試 |
| `frontend/src/lib/pageRange.ts` | 新建 | `parseRange` / `formatRange` 純函式 |
| `frontend/src/lib/pageRange.test.ts` | 新建 | 純函式測試 |
| `frontend/src/state.ts` | 修改 | `selected` 狀態 + 4 個 actions |
| `frontend/src/state.test.ts` | 修改 | 新 actions 的 reducer 測試 |
| `frontend/src/api.ts` | 修改 `startRecognize` | 帶 `{pages}` JSON body |
| `frontend/src/api.test.ts` | 修改 | `startRecognize` body 測試 |
| `frontend/src/components/Step1Upload.tsx` | 修改 | 縮圖格狀勾選 + 頁碼輸入 + 全選鈕 + 防呆 |

---

## Task 1：`iter_hidpi` 支援選頁並吐出原始頁碼

**Files:**
- Modify: `ocr_lib.py:214-229`
- Modify: `ocr_recognize.py:93`（唯一呼叫端，配合 tuple 解包）
- Test: `backend/tests/test_page_selection.py`（新建）

- [ ] **Step 1: 寫失敗測試**

新建 `backend/tests/test_page_selection.py`：

```python
import sys
import tempfile
from pathlib import Path

import fitz

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import ocr_lib  # noqa: E402


def _blank_pdf(n_pages: int) -> Path:
    """產生 n 頁空白（無文字層）PDF，供掃描路線測試。"""
    doc = fitz.open()
    for _ in range(n_pages):
        doc.new_page(width=300, height=400)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    import os
    os.close(fd)
    doc.save(path)
    doc.close()
    return Path(path)


def test_iter_hidpi_yields_page_no_and_filters():
    pdf = _blank_pdf(5)
    try:
        got = [(no, im.size) for no, im in ocr_lib.iter_hidpi(pdf, 72, pages={2, 4})]
        assert [no for no, _ in got] == [2, 4]
        assert all(w > 0 and h > 0 for _, (w, h) in got)
    finally:
        pdf.unlink()


def test_iter_hidpi_none_yields_all_with_page_no():
    pdf = _blank_pdf(3)
    try:
        nos = [no for no, _ in ocr_lib.iter_hidpi(pdf, 72)]
        assert nos == [1, 2, 3]
    finally:
        pdf.unlink()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v`
Expected: FAIL — 目前 `iter_hidpi` 只 yield image（解包成 `(no, im)` 會壞）、且不接受 `pages` 參數（TypeError）。

- [ ] **Step 3: 修改 `iter_hidpi`**

`ocr_lib.py` 將 `def iter_hidpi(pdf: Path, dpi: int):` 整個函式換成：

```python
def iter_hidpi(pdf: Path, dpi: int, pages=None):
    """逐頁 render（generator）。yield (page_no, image)，page_no 為 1-based 原始頁碼。

    一次只在記憶體中保留「一頁」的影像，呼叫端用完即可釋放。
    `pages` 給定時（1-based 可疊代集合）只渲染這些頁，其餘頁在 get_pixmap 前
    直接跳過——這是「選頁辨識」省時間／省記憶體的來源。
    若某頁在指定 DPI 下會超過 MAX_RENDER_MEGAPIXELS，會自動降比例以控制記憶體。
    """
    want = set(pages) if pages is not None else None
    with fitz.open(pdf) as doc:
        for idx, page in enumerate(doc, start=1):
            if want is not None and idx not in want:
                continue
            scale = dpi / 72.0
            r = page.rect
            mp = (r.width * scale) * (r.height * scale) / 1e6
            if mp > MAX_RENDER_MEGAPIXELS:
                scale *= (MAX_RENDER_MEGAPIXELS / mp) ** 0.5
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            yield idx, Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
```

- [ ] **Step 4: 更新唯一呼叫端（保持全頁行為不變）**

`ocr_recognize.py:93` 將
```python
        for i, im in enumerate(ocr_lib.iter_hidpi(path, dpi), start=1):
```
改為
```python
        for i, im in ocr_lib.iter_hidpi(path, dpi):
```
（`i` 現在是原始頁碼；全頁時 `i` 仍等於位置，行為不變。`page_files` 的 `p{i:04d}.jpg` 命名照舊可用。）

- [ ] **Step 5: 執行測試確認通過**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add ocr_lib.py ocr_recognize.py backend/tests/test_page_selection.py
git commit -m "feat(ocr): iter_hidpi 支援選頁過濾並回傳原始頁碼"
```

---

## Task 2：`recognize` 選頁過濾 + 掃描檔頁碼回填

**Files:**
- Modify: `ocr_recognize.py`（`recognize` 簽章與兩條路線；新增 `_remap_to_original`）
- Test: `backend/tests/test_page_selection.py`（新增測試）

- [ ] **Step 1: 寫失敗測試（文字層過濾 + 掃描回填）**

在 `backend/tests/test_page_selection.py` 末尾追加：

```python
import ocr_recognize  # noqa: E402


def _born_pdf(n_pages: int) -> Path:
    """產生 n 頁、每頁含足量文字層的 PDF（has_text_layer 為真）。"""
    doc = fitz.open()
    for i in range(n_pages):
        page = doc.new_page(width=300, height=400)
        page.insert_text((40, 60),
                         f"page {i + 1} 資產負債表 合計 1234567 現金 8900",
                         fontsize=11)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    import os
    os.close(fd)
    doc.save(path)
    doc.close()
    return Path(path)


def test_remap_to_original_maps_positional_to_selected():
    out = ocr_recognize._remap_to_original({1: "a", 2: "b", 3: "c"}, [3, 5, 8])
    assert out == {3: "a", 5: "b", 8: "c"}


def test_recognize_born_digital_filters_selected_pages():
    pdf = _born_pdf(4)
    try:
        res = ocr_recognize.recognize(pdf, pages=[2, 4])
        assert res["mode"] == "文字層擷取"
        assert sorted(res["pages"].keys()) == [2, 4]
    finally:
        pdf.unlink()


def test_recognize_scanned_remaps_to_original_pages(monkeypatch):
    pdf = _blank_pdf(8)

    def fake_ocr_file(path):
        # 模擬 OCR 依「送進去 PDF 內第幾頁」回位置編號（送了 3 頁 → 1/2/3）
        return {"full_text": "--- 第 1 頁 ---\nA\n--- 第 2 頁 ---\nB\n--- 第 3 頁 ---\nC"}

    monkeypatch.setattr(ocr_lib, "ocr_file", fake_ocr_file)
    monkeypatch.setattr(
        ocr_recognize.llm_correct, "correct_via_deepseek",
        lambda text, key, model, timeout: text)  # 校正回傳原文

    try:
        res = ocr_recognize.recognize(
            pdf, corrector="deepseek", deepseek_key="x", pages=[3, 5, 8])
        assert sorted(res["pages"].keys()) == [3, 5, 8]
        assert res["pages"][3].strip() == "A"
        assert res["pages"][8].strip() == "C"
    finally:
        pdf.unlink()
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v -k "remap or filters or scanned"`
Expected: FAIL — `recognize` 尚不接受 `pages`、`_remap_to_original` 不存在。

- [ ] **Step 3: 新增 `_remap_to_original` 並改 `recognize`**

在 `ocr_recognize.py` 的 `_split_pages` 後新增：

```python
def _remap_to_original(pages_dict: dict, selected) -> dict:
    """把位置編號（1..M）的結果 dict 換回原始頁碼。

    `selected` 為使用者選的原始頁碼；排序後第 k 個位置 → 第 k 個原始頁碼。
    例：selected=[3,5,8]、pages_dict={1:..,2:..,3:..} → {3:..,5:..,8:..}。
    """
    order = sorted(selected)
    out: dict = {}
    for k, v in sorted(pages_dict.items()):
        if 1 <= k <= len(order):
            out[order[k - 1]] = v
    return out
```

將 `recognize` 簽章改為（加入 `pages=None`）：

```python
def recognize(path, corrector: str = "claude", deepseek_key: str = "",
              dpi: int = 700, progress=None, pages=None) -> dict:
```

文字層路線（原 `ocr_lib.extract_text_layer(path)` 之後、return 之前）改為：

```python
        out_pages = ocr_lib.extract_text_layer(path)
        if pages is not None:
            want = set(pages)
            out_pages = {k: v for k, v in out_pages.items() if k in want}
        return {"mode": "文字層擷取", "pages": out_pages, "corrector": "（文字層，未經 LLM）"}
```

掃描路線：把渲染迴圈的 `ocr_lib.iter_hidpi(path, dpi)` 改為帶選頁：

```python
        for i, im in ocr_lib.iter_hidpi(path, dpi, pages=pages):
```

掃描路線結尾（原 `pages = _split_pages(corrected)` 起）改為：

```python
    out_pages = _split_pages(corrected)
    out_pages = ocr_postprocess.post_process(out_pages)
    if pages is not None:
        out_pages = _remap_to_original(out_pages, pages)
    return {"mode": mode, "pages": out_pages, "corrector": cname}
```

（注意：`post_process` 在位置編號（連續 1..M）上執行，回填放在最後，避免非連續頁碼影響後處理跨頁邏輯。）

- [ ] **Step 4: 執行測試確認通過**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 回歸——確認全頁（pages=None）行為不變**

Run: `cd backend && python -m pytest tests/test_jobs.py tests/test_api.py -v`
Expected: PASS（既有測試不受影響）

- [ ] **Step 6: Commit**

```bash
git add ocr_recognize.py backend/tests/test_page_selection.py
git commit -m "feat(ocr): recognize 選頁過濾與掃描檔原始頁碼回填"
```

---

## Task 3：後端 engine / jobs 透傳選頁

**Files:**
- Modify: `backend/app/engine.py:36-41`
- Modify: `backend/app/jobs.py`（`Job`、`start_recognition`、`_run`）
- Test: `backend/tests/test_page_selection.py`（新增 JobStore 測試）

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_page_selection.py` 末尾追加：

```python
import time as _time

from app.jobs import JobStore  # noqa: E402

BORN_FIXTURE = r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"


def test_start_recognition_passes_pages_to_engine():
    store = JobStore()
    job = store.create("file3.pdf", Path(BORN_FIXTURE).read_bytes())
    started = store.start_recognition(job.job_id, pages=[1])
    assert started.selected == [1]
    for _ in range(60):
        if store.get(job.job_id).status in ("done", "error"):
            break
        _time.sleep(0.2)
    cur = store.get(job.job_id)
    assert cur.status == "done"
    assert sorted(cur.pages.keys()) == ["1"]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend && python -m pytest tests/test_page_selection.py::test_start_recognition_passes_pages_to_engine -v`
Expected: FAIL — `start_recognition` 不接受 `pages`、`Job` 無 `selected` 欄位。

- [ ] **Step 3: 改 `engine.recognize` 透傳**

`backend/app/engine.py` 的 `recognize` 改為：

```python
def recognize(path, progress=None, pages=None) -> dict:
    """固定 PaddleOCR+DeepSeek（born-digital 自動文字層）。回傳 {mode, pages:{int:str}}。
    pages 給定時只辨識選到的頁（原始頁碼）。"""
    res = ocr_recognize.recognize(
        str(path), corrector="deepseek",
        deepseek_key=resolve_deepseek_key(), progress=progress, pages=pages)
    return {"mode": res["mode"], "pages": res["pages"]}
```

- [ ] **Step 4: 改 `jobs.py`**

`Job` dataclass 新增欄位（在 `error` 後）：

```python
    selected: Optional[list] = None   # 實際辨識的原始頁碼，如 [3,5,8]
```

`start_recognition` 簽章與內文改為：

```python
    def start_recognition(self, job_id: str, pages=None) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        if job.status in ("running", "done"):
            return job
        job.selected = list(pages) if pages is not None else None
        job.status = "running"
        job.progress = {"message": "準備中…", "percent": 0}
        self._pool.submit(self._run, job_id)
        return job
```

`_run` 中呼叫 engine 處改為：

```python
            res = engine.recognize(job.file_path, progress=_progress,
                                    pages=job.selected)
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd backend && python -m pytest tests/test_page_selection.py::test_start_recognition_passes_pages_to_engine -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine.py backend/app/jobs.py backend/tests/test_page_selection.py
git commit -m "feat(api): engine/jobs 透傳選頁至辨識引擎"
```

---

## Task 4：`/recognize` 端點收選頁 + 驗證

**Files:**
- Modify: `backend/app/schemas.py`（新增 `RecognizeRequest`）
- Modify: `backend/app/main.py:87-92`
- Test: `backend/tests/test_page_selection.py`（新增端點測試）

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_page_selection.py` 末尾追加：

```python
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

_client = TestClient(app)


def _upload_born():
    with open(BORN_FIXTURE, "rb") as f:
        return _client.post(
            "/api/jobs",
            files={"file": ("file3.pdf", f, "application/pdf")}).json()["job_id"]


def test_recognize_rejects_empty_pages():
    jid = _upload_born()
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": []})
    assert r.status_code == 400


def test_recognize_rejects_out_of_range_pages():
    jid = _upload_born()  # 此檔 1 頁
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": [2]})
    assert r.status_code == 400


def test_recognize_accepts_valid_pages():
    jid = _upload_born()
    r = _client.post(f"/api/jobs/{jid}/recognize", json={"pages": [1]})
    assert r.status_code == 200
    assert r.json()["status"] in ("running", "done")
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v -k recognize_`
Expected: FAIL — 端點目前不收 body、不驗證頁碼。

- [ ] **Step 3: 新增 `RecognizeRequest`**

`backend/app/schemas.py` 末尾新增：

```python
class RecognizeRequest(BaseModel):
    pages: List[int]
```

- [ ] **Step 4: 改 `/recognize` 端點**

`backend/app/main.py` 的 `recognize` 端點改為：

```python
@app.post("/api/jobs/{job_id}/recognize")
def recognize(job_id: str, req: schemas.RecognizeRequest) -> dict:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到任務")
    pages = sorted(set(req.pages))
    if not pages:
        raise HTTPException(status_code=400, detail="請至少選擇一頁")
    if pages[0] < 1 or pages[-1] > job.n_pages:
        raise HTTPException(
            status_code=400,
            detail=f"頁碼超出範圍：本檔共 {job.n_pages} 頁")
    job = store.start_recognition(job_id, pages=pages)
    return {"job_id": job.job_id, "status": job.status}
```

- [ ] **Step 5: 執行測試確認通過**

Run: `cd backend && python -m pytest tests/test_page_selection.py -v`
Expected: PASS（全部）

- [ ] **Step 6: 全後端回歸**

Run: `cd backend && python -m pytest -v`
Expected: PASS（既有測試 + 新測試皆綠；注意既有 `test_api.py::test_recognize_then_poll_done` 需同步更新——見下一步）

- [ ] **Step 7: 更新既有端點測試（已不再無 body）**

`backend/tests/test_api.py:45` 將
```python
    r = client.post(f"/api/jobs/{jid}/recognize")
```
改為
```python
    r = client.post(f"/api/jobs/{jid}/recognize", json={"pages": [1]})
```
`backend/tests/test_jobs.py` 中 `store.start_recognition(job.job_id)` 的呼叫維持可用（`pages` 預設 `None` → 全頁），不需改。

Run: `cd backend && python -m pytest -v`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(api): /recognize 收選頁並驗證頁碼範圍"
```

---

## Task 5：前端 `pageRange` 純函式

**Files:**
- Create: `frontend/src/lib/pageRange.ts`
- Test: `frontend/src/lib/pageRange.test.ts`

- [ ] **Step 1: 寫失敗測試**

新建 `frontend/src/lib/pageRange.test.ts`：

```typescript
import { describe, it, expect } from 'vitest'
import { parseRange, formatRange } from './pageRange'

describe('parseRange', () => {
  it('parses commas and ranges', () => {
    expect(parseRange('3,5,8-10', 30)).toEqual([3, 5, 8, 9, 10])
  })
  it('dedupes and sorts', () => {
    expect(parseRange('8,3,3,5', 30)).toEqual([3, 5, 8])
  })
  it('ignores out-of-range and zero', () => {
    expect(parseRange('0,2,99', 5)).toEqual([2])
  })
  it('ignores reversed ranges', () => {
    expect(parseRange('5-3', 30)).toEqual([])
  })
  it('tolerates spaces and trailing commas', () => {
    expect(parseRange(' 1 , 2 , ', 30)).toEqual([1, 2])
  })
  it('empty string yields empty array', () => {
    expect(parseRange('', 30)).toEqual([])
  })
})

describe('formatRange', () => {
  it('collapses consecutive runs', () => {
    expect(formatRange([3, 5, 8, 9, 10])).toBe('3,5,8-10')
  })
  it('single page', () => {
    expect(formatRange([4])).toBe('4')
  })
  it('empty array yields empty string', () => {
    expect(formatRange([])).toBe('')
  })
})
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd frontend && npm run test -- pageRange`
Expected: FAIL — `./pageRange` 模組不存在。

- [ ] **Step 3: 實作 `pageRange.ts`**

新建 `frontend/src/lib/pageRange.ts`：

```typescript
// 頁碼字串 ⇄ 排序去重的頁碼陣列。縮圖打勾與頁碼輸入共用同一份選取狀態。

export function parseRange(input: string, maxPage: number): number[] {
  const set = new Set<number>()
  for (const raw of input.split(',')) {
    const part = raw.trim()
    if (!part) continue
    const m = part.match(/^(\d+)\s*-\s*(\d+)$/)
    if (m) {
      const a = Number(m[1])
      const b = Number(m[2])
      if (a <= b) for (let n = a; n <= b; n++) add(set, n, maxPage)
    } else if (/^\d+$/.test(part)) {
      add(set, Number(part), maxPage)
    }
  }
  return [...set].sort((x, y) => x - y)
}

function add(set: Set<number>, n: number, maxPage: number) {
  if (n >= 1 && n <= maxPage) set.add(n)
}

export function formatRange(pages: number[]): string {
  const s = [...pages].sort((a, b) => a - b)
  const out: string[] = []
  let i = 0
  while (i < s.length) {
    let j = i
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++
    out.push(i === j ? `${s[i]}` : `${s[i]}-${s[j]}`)
    i = j + 1
  }
  return out.join(',')
}
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd frontend && npm run test -- pageRange`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/pageRange.ts frontend/src/lib/pageRange.test.ts
git commit -m "feat(web): pageRange 解析/格式化頁碼選取"
```

---

## Task 6：前端 `selected` 狀態與 actions

**Files:**
- Modify: `frontend/src/state.ts`
- Test: `frontend/src/state.test.ts`

- [ ] **Step 1: 寫失敗測試**

在 `frontend/src/state.test.ts` 追加（沿用該檔現有 import 風格；若無則 import `reducer, initialState`）：

```typescript
import { describe, it, expect } from 'vitest'
import { reducer, initialState } from './state'
import type { JobMeta } from './types'

const META: JobMeta = {
  job_id: 'j1', file_name: 'a.pdf', n_pages: 10,
  is_born_digital: false, status: 'created',
}

describe('selected pages reducer', () => {
  it('TOGGLE_PAGE adds then removes, kept sorted', () => {
    let s = reducer(initialState, { type: 'TOGGLE_PAGE', page: 5 })
    s = reducer(s, { type: 'TOGGLE_PAGE', page: 2 })
    expect(s.selected).toEqual([2, 5])
    s = reducer(s, { type: 'TOGGLE_PAGE', page: 5 })
    expect(s.selected).toEqual([2])
  })
  it('SET_SELECTED replaces selection', () => {
    const s = reducer(initialState, { type: 'SET_SELECTED', pages: [8, 3, 3] })
    expect(s.selected).toEqual([3, 8])
  })
  it('SELECT_ALL fills 1..n', () => {
    const s = reducer({ ...initialState, meta: META },
      { type: 'SELECT_ALL' })
    expect(s.selected).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
  })
  it('CLEAR_SELECTED empties', () => {
    const s = reducer({ ...initialState, selected: [1, 2] },
      { type: 'CLEAR_SELECTED' })
    expect(s.selected).toEqual([])
  })
  it('SET_META clears selection', () => {
    const s = reducer({ ...initialState, selected: [1, 2] },
      { type: 'SET_META', meta: META })
    expect(s.selected).toEqual([])
  })
})
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd frontend && npm run test -- state`
Expected: FAIL — `selected` 與新 actions 不存在（型別與執行皆錯）。

- [ ] **Step 3: 修改 `state.ts`**

`AppState` 介面新增欄位：

```typescript
  selected: number[]
```

`Action` 聯集新增：

```typescript
  | { type: 'TOGGLE_PAGE'; page: number }
  | { type: 'SET_SELECTED'; pages: number[] }
  | { type: 'SELECT_ALL' }
  | { type: 'CLEAR_SELECTED' }
```

`initialState` 新增 `selected: []`：

```typescript
export const initialState: AppState = {
  step: 1, meta: null, status: null, curPage: 1, view: 'text', tables: {},
  selected: [],
}
```

`reducer` 的 `SET_META` 分支改為清空 selected：

```typescript
    case 'SET_META':
      return { ...s, meta: a.meta, status: null, tables: {}, view: 'text', curPage: 1, selected: [] }
```

`RESET` 已回 `initialState`，自然含 `selected: []`，不需改。新增四個分支（放在 `SET_PAGE` 後）：

```typescript
    case 'TOGGLE_PAGE': {
      const has = s.selected.includes(a.page)
      const next = has ? s.selected.filter((p) => p !== a.page)
                       : [...s.selected, a.page].sort((x, y) => x - y)
      return { ...s, selected: next }
    }
    case 'SET_SELECTED':
      return { ...s, selected: [...new Set(a.pages)].sort((x, y) => x - y) }
    case 'SELECT_ALL':
      return {
        ...s,
        selected: s.meta
          ? Array.from({ length: s.meta.n_pages }, (_, i) => i + 1)
          : [],
      }
    case 'CLEAR_SELECTED':
      return { ...s, selected: [] }
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd frontend && npm run test -- state`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state.ts frontend/src/state.test.ts
git commit -m "feat(web): AppState 選頁狀態與 toggle/all/clear actions"
```

---

## Task 7：前端 `startRecognize` 帶選頁 body

**Files:**
- Modify: `frontend/src/api.ts:22-26`
- Test: `frontend/src/api.test.ts`

- [ ] **Step 1: 寫失敗測試**

在 `frontend/src/api.test.ts` 追加（沿用既有 fetch mock 風格）：

```typescript
import { describe, it, expect, vi, afterEach } from 'vitest'
import * as api from './api'

afterEach(() => vi.restoreAllMocks())

describe('startRecognize', () => {
  it('posts pages as JSON body', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ job_id: 'j1', status: 'running' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    await api.startRecognize('j1', [3, 5, 8])
    const [url, opts] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/jobs/j1/recognize')
    expect(opts.method).toBe('POST')
    expect(opts.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(opts.body)).toEqual({ pages: [3, 5, 8] })
  })
})
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `cd frontend && npm run test -- api`
Expected: FAIL — `startRecognize` 目前不收 pages、不帶 body。

- [ ] **Step 3: 修改 `startRecognize`**

`frontend/src/api.ts` 將 `startRecognize` 換成：

```typescript
export async function startRecognize(
  jobId: string, pages: number[],
): Promise<{ job_id: string; status: string }> {
  const r = await fetch(`${BASE}/jobs/${jobId}/recognize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pages }),
  })
  if (!r.ok) {
    let detail = ''
    try { detail = (await r.json()).detail } catch { /* 無 JSON 內容 */ }
    throw new Error(detail || `辨識啟動失敗 (${r.status})`)
  }
  return r.json()
}
```

- [ ] **Step 4: 執行測試確認通過**

Run: `cd frontend && npm run test -- api`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.ts frontend/src/api.test.ts
git commit -m "feat(web): startRecognize 帶選頁 JSON body 與錯誤透傳"
```

---

## Task 8：步驟 1 選頁 UI（縮圖格狀勾選 + 頁碼輸入 + 全選鈕 + 防呆）

**Files:**
- Modify: `frontend/src/components/Step1Upload.tsx`
- Modify: `frontend/src/App.css`（新增格狀與勾選樣式）
- 驗證：型別檢查 + build + 手動驗收（UI 互動不寫單元測試，邏輯已由 Task 5/6/7 覆蓋）

- [ ] **Step 1: 改 `Step1Upload.tsx` 的 `onRecognize` 帶選頁**

將 `onRecognize` 內 `await api.startRecognize(meta.job_id)` 改為：

```typescript
      await api.startRecognize(meta.job_id, state.selected)
```

- [ ] **Step 2: 以選頁 UI 取代原單張縮圖區塊**

把 `{meta && ( ... )}` 內、原本「預覽頁碼下拉 + 單張 thumb + 辨識鈕」整段，換成：

```tsx
      {meta && (
        <>
          <p className="info">
            {meta.is_born_digital
              ? `🔎 內含文字層（born-digital）→ 直接擷取文字層（${meta.n_pages} 頁）。`
              : `🔎 掃描影像／截圖 → PaddleOCR ＋ DeepSeek（${meta.n_pages} 頁）。`}
          </p>

          <div className="selbar">
            <label>
              選擇頁碼：
              <input
                type="text"
                placeholder="例如 3,5,8-10"
                value={formatRange(state.selected)}
                onChange={(e) =>
                  dispatch({ type: 'SET_SELECTED',
                             pages: parseRange(e.target.value, meta.n_pages) })}
                disabled={recognizing}
              />
            </label>
            <button type="button" onClick={() => dispatch({ type: 'SELECT_ALL' })}
                    disabled={recognizing}>全選</button>
            <button type="button" onClick={() => dispatch({ type: 'CLEAR_SELECTED' })}
                    disabled={recognizing}>全不選</button>
            <span className="count">已選 {state.selected.length} / {meta.n_pages} 頁</span>
          </div>

          <div className="thumbgrid">
            {Array.from({ length: meta.n_pages }, (_, i) => i + 1).map((n) => {
              const on = state.selected.includes(n)
              return (
                <button
                  key={n}
                  type="button"
                  className={on ? 'thumbcell on' : 'thumbcell'}
                  onClick={() => dispatch({ type: 'TOGGLE_PAGE', page: n })}
                  disabled={recognizing}
                >
                  <img src={api.pageImageUrl(meta.job_id, n)} alt={`第 ${n} 頁`} />
                  <span className="pno">{n}</span>
                  {on && <span className="tick">✓</span>}
                </button>
              )
            })}
          </div>

          <button className="primary" onClick={onRecognize}
                  disabled={recognizing || state.selected.length === 0}>
            {recognizing ? '辨識中…' : '✅ 開始辨識（已選 ' + state.selected.length + ' 頁）'}
          </button>
          {state.selected.length === 0 && !recognizing && (
            <p className="hint">請至少選擇一頁</p>
          )}
          {recognizing && state.status?.progress && (
            <p className="progress">
              {state.status.progress.message}（{state.status.progress.percent}%）
            </p>
          )}
        </>
      )}
```

- [ ] **Step 3: 補 import**

`Step1Upload.tsx` 頂部新增：

```typescript
import { parseRange, formatRange } from '../lib/pageRange'
```

（原檔已 import `* as api`、`state`、`dispatch`，沿用。`SET_PAGE` 下拉已移除，不再需要 `curPage` 於本元件，但保留 state 其他用途，不動 import。）

- [ ] **Step 4: 加樣式**

`frontend/src/App.css` 末尾新增：

```css
.selbar { display: flex; align-items: center; gap: .75rem; flex-wrap: wrap; margin: .5rem 0; }
.selbar input[type=text] { width: 12rem; }
.selbar .count { color: #555; font-size: .9rem; }
.thumbgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
             gap: .5rem; margin: .5rem 0; max-height: 60vh; overflow: auto; }
.thumbcell { position: relative; padding: 2px; border: 2px solid transparent;
             background: #fafafa; cursor: pointer; }
.thumbcell img { width: 100%; display: block; }
.thumbcell.on { border-color: #2563eb; }
.thumbcell .pno { position: absolute; left: 4px; bottom: 4px; font-size: .75rem;
                  background: rgba(0,0,0,.6); color: #fff; padding: 0 4px; border-radius: 3px; }
.thumbcell .tick { position: absolute; right: 4px; top: 4px; color: #2563eb; font-weight: 700; }
```

- [ ] **Step 5: 型別檢查 + 全前端測試 + build**

Run: `cd frontend && npm run test -- --run && npx tsc --noEmit && npm run build`
Expected: 測試全綠、`tsc` 無錯、build 成功。
（若 `tsc` 報 `curPage`/`SET_PAGE` 未使用，移除 Step 2 已不再引用的相關程式即可。）

- [ ] **Step 6: 手動驗收**

啟動後端 `cd backend && run_api.bat`，前端 `cd frontend && npm run dev`，開 http://localhost:5173 ：
1. 上傳一份多頁檔 → 出現縮圖格狀清單，**預設全未選**、「開始辨識」**禁用**。
2. 勾兩三張縮圖 → 頁碼輸入框同步顯示（如 `3,5,8-10`）；改輸入框 → 縮圖勾選同步。
3. 「全選／全不選」正常；「已選 X / N 頁」即時更新。
4. 選非連續頁辨識 → 步驟 2 只出現選到的頁、**頁碼為原始頁碼**、Excel 工作表頁碼相符。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Step1Upload.tsx frontend/src/App.css
git commit -m "feat(web): 步驟1 選頁 UI（縮圖勾選＋頁碼輸入同步＋防呆）"
```

---

## Self-Review 紀錄

- **Spec 覆蓋**：預設不選（Task 6 initialState/SET_META、Task 8 預設禁用）、縮圖＋輸入同步（Task 5/6/8 共用 `selected`）、上傳上限維持（未改 `create`/上傳檢查）、兩路線都套用（Task 2 文字層過濾＋掃描回填）、保留原始頁碼（Task 2 `_remap_to_original`、文字層原 key）、防呆（Task 4 後端 400＋Task 8 前端禁用）、全選鈕（Task 6 SELECT_ALL＋Task 8）。皆有對應任務。
- **頁碼回填**：Task 2 對掃描檔位置編號 1..M 做 `_remap_to_original`，並以 `test_recognize_scanned_remaps_to_original_pages` 釘住。
- **型別一致**：`startRecognize(jobId, pages)`（Task 7）↔ Step1 呼叫（Task 8）；`pages`/`selected` 命名於 schema/engine/jobs 一致；reducer action 名稱於 Task 6 定義、Task 8 使用一致。
- **回歸**：Task 2 Step 5、Task 4 Step 6-7 明確要求既有測試保持綠（含更新 `test_api.py` 的 recognize 呼叫）。
