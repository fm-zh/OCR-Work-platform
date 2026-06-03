# 進階版辨識網頁（ocr_app_pro）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `E:\OCR-Work-platform` 新建一支進階版辨識網頁 `ocr_app_pro.py`（三步驟分頁：上傳 → 辨識 → 對照編輯），辨識固定走 PaddleOCR＋DeepSeek（born-digital 自動文字層），步驟③左原圖右可編輯結果。

**Architecture:** 純 UI 層，辨識完全委派既有 `ocr_recognize.recognize()`；可單元測試的純函式抽到 `ocr_app_pro_helpers.py`（不 import streamlit），UI 以 Streamlit `AppTest` 做整合測試。與簡單版 `ocr_app.py` 共用辨識核心。

**Tech Stack:** Python 3.14、Streamlit、PyMuPDF、Pillow、OpenCV、（測試）pytest ＋ streamlit.testing.v1.AppTest。

> **環境備註：**
> - 工作目錄為 `E:\OCR-Work-platform`。所有路徑以此為基準。
> - 此資料夾**目前不是 git 倉庫**。若要保留每步 commit，請先在該資料夾執行 `git init`；否則可略過所有「Commit」步驟（不影響功能）。
> - 測試需 pytest：若未安裝，先 `python -m pip install pytest`。測試指令一律用 `python -m pytest`。
> - 測試會用到既有檔案：`E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf`（born-digital）、`E:\PJ_OCR\test\1.資產負債表測試(類型圖檔需OCR).pdf`（影像）。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `ocr_app_pro_helpers.py`（新增） | 純函式：金鑰解析、頁面文字合併、目前頁文字、檔案偵測。不 import streamlit，可單元測試。 |
| `ocr_app_pro.py`（新增） | Streamlit 進階版網頁（三步驟分頁、原圖對照、線上編輯）。 |
| `test_ocr_app_pro.py`（新增） | pytest：helpers 單元測試 ＋ AppTest 整合測試。 |
| `run_pro.bat`（新增） | 啟動 8503 的批次檔。 |
| `README.md`（修改） | 補上進階版說明。 |

---

## Task 1：純函式 helpers（金鑰／合併／目前頁）

**Files:**
- Create: `E:\OCR-Work-platform\ocr_app_pro_helpers.py`
- Test: `E:\OCR-Work-platform\test_ocr_app_pro.py`

- [ ] **Step 1: 先寫失敗測試**

建立 `test_ocr_app_pro.py`：

```python
import os
import sys
sys.path.insert(0, r"E:\OCR-Work-platform")
import ocr_app_pro_helpers as H


def test_resolve_key_uses_override_first():
    assert H.resolve_deepseek_key("  sk-override ") == "sk-override"


def test_resolve_key_uses_env_when_no_override(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
    assert H.resolve_deepseek_key("") == "sk-env"


def test_resolve_key_falls_back_to_builtin(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert H.resolve_deepseek_key("") == H.BUILTIN_DEEPSEEK_KEY


def test_combine_pages_single_returns_plain_text():
    assert H.combine_pages({1: "hello"}) == "hello"


def test_combine_pages_multi_adds_headers():
    out = H.combine_pages({1: "a", 2: "b"})
    assert "===== 第 1 頁 =====" in out and "a" in out
    assert "===== 第 2 頁 =====" in out and "b" in out


def test_current_page_text_prefers_edited():
    assert H.current_page_text({1: "orig"}, {1: "edited"}, 1) == "edited"


def test_current_page_text_falls_back_to_original():
    assert H.current_page_text({1: "orig"}, {}, 1) == "orig"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'ocr_app_pro_helpers'`）

- [ ] **Step 3: 寫最小實作**

建立 `ocr_app_pro_helpers.py`：

```python
"""進階版網頁的純函式（不 import streamlit，可單元測試）。"""
from __future__ import annotations

import os

# 與專案測試腳本一致的可用金鑰，作為最後 fallback
BUILTIN_DEEPSEEK_KEY = "sk-dfc52c43969c4457a83928fd3f42a8cb"


def resolve_deepseek_key(override: str = "") -> str:
    """解析 DeepSeek 金鑰：覆寫 → 環境變數 DEEPSEEK_API_KEY → 內建 fallback。"""
    if override and override.strip():
        return override.strip()
    env = os.environ.get("DEEPSEEK_API_KEY", "")
    if env and env.strip():
        return env.strip()
    return BUILTIN_DEEPSEEK_KEY


def combine_pages(pages: dict) -> str:
    """{page_no: text} → 下載用全文。單頁回純文字；多頁加 '===== 第 N 頁 ====='。"""
    keys = sorted(pages)
    if not keys:
        return ""
    if len(keys) == 1:
        return pages[keys[0]]
    return "\n\n".join(f"===== 第 {k} 頁 =====\n{pages[k]}" for k in keys)


def current_page_text(result_pages: dict, edited: dict, pno: int) -> str:
    """回傳某頁目前文字：有編輯過用編輯版，否則用原辨識結果。"""
    if pno in edited:
        return edited[pno]
    return result_pages.get(pno, "")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro_helpers.py test_ocr_app_pro.py
git commit -m "feat(pro): pure helpers for key/combine/current-page"
```

---

## Task 2：檔案偵測 helper（born-digital / 頁數）

**Files:**
- Modify: `E:\OCR-Work-platform\ocr_app_pro_helpers.py`
- Test: `E:\OCR-Work-platform\test_ocr_app_pro.py`

- [ ] **Step 1: 加失敗測試**（附加到測試檔末端）

```python
def test_detect_file_born_digital():
    info = H.detect_file(r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf")
    assert info["is_born_digital"] is True
    assert info["n_pages"] == 1
    assert info["text_chars"] >= 50


def test_detect_file_image_pdf():
    info = H.detect_file(r"E:\PJ_OCR\test\1.資產負債表測試(類型圖檔需OCR).pdf")
    assert info["is_born_digital"] is False
    assert info["text_chars"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: FAIL（`AttributeError: module 'ocr_app_pro_helpers' has no attribute 'detect_file'`）

- [ ] **Step 3: 實作 detect_file**（加到 `ocr_app_pro_helpers.py` 末端）

```python
def detect_file(path) -> dict:
    """偵測上傳檔：是否含文字層（born-digital）、頁數、文字層字元數。"""
    import sys
    if r"E:\OCR-Work-platform" not in sys.path:
        sys.path.insert(0, r"E:\OCR-Work-platform")
    import ocr_lib
    import fitz
    chars = ocr_lib.text_layer_char_count(path)
    with fitz.open(path) as doc:
        n_pages = doc.page_count
    return {"is_born_digital": chars >= 50, "n_pages": n_pages, "text_chars": chars}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: PASS（9 passed）

- [ ] **Step 5: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro_helpers.py test_ocr_app_pro.py
git commit -m "feat(pro): detect_file helper (born-digital / page count)"
```

---

## Task 3：網頁骨架（標題、session、步驟列、三分頁、zoomable 元件）

**Files:**
- Create: `E:\OCR-Work-platform\ocr_app_pro.py`
- Test: `E:\OCR-Work-platform\test_ocr_app_pro.py`

- [ ] **Step 1: 加 AppTest 載入測試**（附加到測試檔末端）

```python
def test_app_loads_with_three_tabs():
    import warnings
    warnings.filterwarnings("ignore")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(r"E:\OCR-Work-platform\ocr_app_pro.py", default_timeout=60)
    at.run(timeout=60)
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("進階版" in t for t in titles)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_app_loads_with_three_tabs -q`
Expected: FAIL（找不到 `ocr_app_pro.py`）

- [ ] **Step 3: 建立骨架 `ocr_app_pro.py`**

```python
"""進階版辨識網頁 — PaddleOCR + DeepSeek，三步驟分頁，含原圖對照與線上編輯。
啟動： streamlit run ocr_app_pro.py --server.port 8503
"""
from __future__ import annotations

import base64
import io
import sys
import tempfile
import time
from pathlib import Path

import streamlit as st

if r"E:\OCR-Work-platform" not in sys.path:
    sys.path.insert(0, r"E:\OCR-Work-platform")
import ocr_lib
import ocr_recognize
from ocr_app_pro_helpers import (
    resolve_deepseek_key, combine_pages, current_page_text, detect_file,
)

PREVIEW_DPI = 150

st.set_page_config(page_title="財報文件智慧辨識（進階版）", page_icon="🛠️", layout="wide")

ss = st.session_state
ss.setdefault("step", 1)
ss.setdefault("file_path", None)
ss.setdefault("file_name", None)
ss.setdefault("is_born_digital", None)
ss.setdefault("n_pages", None)
ss.setdefault("result", None)
ss.setdefault("edited", {})
ss.setdefault("preview", None)
ss.setdefault("cur_page", 1)

st.title("🛠️ 財報文件智慧辨識（進階版）")
st.caption("PaddleOCR ＋ DeepSeek 校正 · 原圖對照 · 結果可線上編輯"
           "（內含文字層之 PDF 自動走文字層擷取）")

STEPS = ["①　上傳檔案", "②　進行辨識", "③　對照編輯"]
_cols = st.columns(3)
for _i, _c in enumerate(_cols, start=1):
    _name = STEPS[_i - 1]
    if ss.step == _i:
        _c.success(f"**{_name}**　← 進行中")
    elif ss.step > _i:
        _c.info(f"{_name}　✅")
    else:
        _c.markdown(f"<div style='padding:8px;color:#999'>{_name}</div>",
                    unsafe_allow_html=True)
st.divider()
tab_upload, tab_run, tab_out = st.tabs(STEPS)


def zoomable_image(pil_img, key: str, height: int = 560) -> None:
    """滾輪縮放／拖曳平移／雙擊還原的圖片元件（iframe 隔離）。"""
    import streamlit.components.v1 as components
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="PNG", optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode()
    html = (
        '<div id="zc" style="width:100%;height:' + str(height) + 'px;'
        'overflow:hidden;border:1px solid #ddd;border-radius:4px;'
        'position:relative;cursor:grab;user-select:none;background:#fafafa;">'
        '<img id="zi" src="data:image/png;base64,' + b64 + '" draggable="false" '
        'style="width:100%;transform-origin:0 0;pointer-events:none;'
        'position:absolute;top:0;left:0;display:block;" />'
        '<div id="zinfo" style="position:absolute;bottom:6px;right:8px;'
        'background:rgba(0,0,0,.55);color:#fff;font:11px sans-serif;'
        'padding:2px 6px;border-radius:3px;pointer-events:none;">'
        '1.00x — 滾輪縮放 · 拖曳平移 · 雙擊還原</div></div>'
        '<script>'
        '(function(){'
        'const c=document.getElementById("zc");'
        'const i=document.getElementById("zi");'
        'const info=document.getElementById("zinfo");'
        'let s=1,tx=0,ty=0,drag=false,sx=0,sy=0;'
        'function apply(){i.style.transform="translate("+tx+"px,"+ty+"px) scale("+s+")";'
        'info.textContent=s.toFixed(2)+"x — 滾輪縮放 · 拖曳平移 · 雙擊還原";}'
        'c.addEventListener("wheel",function(e){e.preventDefault();'
        'const r=c.getBoundingClientRect();'
        'const mx=e.clientX-r.left,my=e.clientY-r.top;'
        'const ns=Math.max(0.5,Math.min(20,s*(1-e.deltaY*0.002)));'
        'const k=ns/s;tx=mx-(mx-tx)*k;ty=my-(my-ty)*k;s=ns;apply();},{passive:false});'
        'c.addEventListener("mousedown",function(e){drag=true;sx=e.clientX-tx;sy=e.clientY-ty;c.style.cursor="grabbing";});'
        'c.addEventListener("mousemove",function(e){if(!drag)return;tx=e.clientX-sx;ty=e.clientY-sy;apply();});'
        'window.addEventListener("mouseup",function(){drag=false;c.style.cursor="grab";});'
        'c.addEventListener("dblclick",function(){s=1;tx=0;ty=0;apply();});'
        '})();</script>'
    )
    components.html(html, height=height + 6, scrolling=False)


with tab_upload:
    st.info("（步驟①內容於 Task 4 實作）")
with tab_run:
    st.info("（步驟②內容於 Task 5 實作）")
with tab_out:
    st.info("（步驟③內容於 Task 6 實作）")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_app_loads_with_three_tabs -q`
Expected: PASS

- [ ] **Step 5: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro.py
git commit -m "feat(pro): app skeleton (stepper, tabs, zoomable_image)"
```

---

## Task 4：步驟① 上傳檔案

**Files:**
- Modify: `E:\OCR-Work-platform\ocr_app_pro.py`（取代 `with tab_upload:` 區塊）

- [ ] **Step 1: 取代 `with tab_upload:` 區塊為完整實作**

把骨架裡的：

```python
with tab_upload:
    st.info("（步驟①內容於 Task 4 實作）")
```

改成：

```python
with tab_upload:
    st.subheader("步驟 1　上傳要辨識的檔案")
    st.write("支援 **PDF** 與圖片（**JPG / PNG / WEBP**）。")
    up = st.file_uploader("拖曳或點選上傳", type=["pdf", "jpg", "jpeg", "png", "webp"],
                          key="uploader")
    if up is not None:
        updir = Path(tempfile.gettempdir()) / "ocr_pro_uploads"
        updir.mkdir(exist_ok=True)
        dest = updir / up.name
        dest.write_bytes(up.getbuffer())
        if ss.file_path != str(dest):
            ss.result = None
            ss.edited = {}
            ss.preview = None
            ss.cur_page = 1
        ss.file_path = str(dest)
        ss.file_name = up.name
        info = detect_file(str(dest))
        ss.is_born_digital = info["is_born_digital"]
        ss.n_pages = info["n_pages"]
        ss.step = max(ss.step, 2)
        st.success(f"✅ 已上傳：**{up.name}**（{ss.n_pages} 頁）")
        if ss.is_born_digital:
            st.info(f"🔎 內含文字層（born-digital）→ 將直接擷取文字層"
                    f"（字元數 {info['text_chars']}）。")
        else:
            st.info("🔎 掃描影像／截圖 → 將以 PaddleOCR ＋ DeepSeek 辨識。")
        st.markdown("➡️ 請點選上方 **②　進行辨識** 分頁繼續。")
    elif ss.file_name:
        st.info(f"目前已上傳：**{ss.file_name}**（重新上傳可更換）")
```

- [ ] **Step 2: 跑既有測試確認沒壞**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: PASS（所有測試；app 仍正常載入，`st.file_uploader` 不會報錯）

- [ ] **Step 3: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro.py
git commit -m "feat(pro): step 1 upload + file detection"
```

---

## Task 5：步驟② 進行辨識（PaddleOCR＋DeepSeek）

**Files:**
- Modify: `E:\OCR-Work-platform\ocr_app_pro.py`（取代 `with tab_run:` 區塊）
- Test: `E:\OCR-Work-platform\test_ocr_app_pro.py`

- [ ] **Step 1: 加 AppTest 辨識測試**（born-digital，最快、免 LLM）（附加到測試檔末端）

```python
def test_recognize_born_digital_via_app():
    import warnings
    warnings.filterwarnings("ignore")
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(r"E:\OCR-Work-platform\ocr_app_pro.py", default_timeout=120)
    at.session_state["file_path"] = str(
        Path(r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"))
    at.session_state["file_name"] = "3.資產負債表測試-此為可複製文字之PDF.pdf"
    at.session_state["is_born_digital"] = True
    at.session_state["n_pages"] = 1
    at.run(timeout=120)
    btn = [b for b in at.button if b.key == "run_recognize"]
    assert btn, "找不到 run_recognize 按鈕"
    btn[0].click()
    at.run(timeout=120)
    assert not at.exception
    res = at.session_state["result"]
    assert res is not None
    assert res["mode"] == "文字層擷取"
    assert 1 in res["pages"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_recognize_born_digital_via_app -q`
Expected: FAIL（找不到 `run_recognize` 按鈕）

- [ ] **Step 3: 取代 `with tab_run:` 區塊為完整實作**

把：

```python
with tab_run:
    st.info("（步驟②內容於 Task 5 實作）")
```

改成：

```python
with tab_run:
    st.subheader("步驟 2　進行辨識（PaddleOCR ＋ DeepSeek）")
    if not ss.file_path:
        st.warning("請先在『①　上傳檔案』分頁上傳檔案。")
    else:
        st.write(f"待辨識檔案：**{ss.file_name}**（{ss.n_pages} 頁）")
        if ss.is_born_digital:
            st.success("此檔含文字層，將直接擷取（不需 OCR / LLM，最快最準）。")
        with st.expander("進階設定（選填）"):
            override = st.text_input("DeepSeek API Key（留空用預設）",
                                     type="password", key="ds_override")
        if st.button("🚀 開始辨識", type="primary", key="run_recognize"):
            bar = st.progress(0, text="準備中…")
            seen = {"n": 0}

            def _cb(msg):
                seen["n"] += 1
                bar.progress(min(90, seen["n"] * 22), text=msg)

            t0 = time.time()
            try:
                res = ocr_recognize.recognize(
                    ss.file_path, corrector="deepseek",
                    deepseek_key=resolve_deepseek_key(
                        st.session_state.get("ds_override", "")),
                    progress=_cb)
                res["elapsed"] = time.time() - t0
                bar.progress(100, text="完成")
                ss.result = res
                ss.edited = {}
                ss.preview = None
                ss.cur_page = 1
                ss.step = 3
                st.success(f"✅ 辨識完成（{res['mode']}，{res['elapsed']:.1f} 秒）。"
                           "請點選上方 **③　對照編輯** 分頁查看。")
            except Exception as exc:
                bar.empty()
                st.error(f"❌ 辨識失敗：{type(exc).__name__}: {exc}")
                st.caption("若為 DeepSeek 金鑰／網路問題，請在『進階設定』填入有效金鑰後重試。")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_recognize_born_digital_via_app -q`
Expected: PASS

- [ ] **Step 5: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro.py test_ocr_app_pro.py
git commit -m "feat(pro): step 2 recognize via shared engine"
```

---

## Task 6：步驟③ 對照編輯（左原圖／右可編輯＋下載）

**Files:**
- Modify: `E:\OCR-Work-platform\ocr_app_pro.py`（取代 `with tab_out:` 區塊）
- Test: `E:\OCR-Work-platform\test_ocr_app_pro.py`

- [ ] **Step 1: 加 AppTest 對照編輯測試**（附加到測試檔末端）

```python
def test_step3_shows_editable_text_and_download():
    import warnings
    warnings.filterwarnings("ignore")
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(r"E:\OCR-Work-platform\ocr_app_pro.py", default_timeout=120)
    at.session_state["file_path"] = str(
        Path(r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf"))
    at.session_state["file_name"] = "3.資產負債表測試-此為可複製文字之PDF.pdf"
    at.session_state["is_born_digital"] = True
    at.session_state["n_pages"] = 1
    at.session_state["result"] = {"mode": "文字層擷取",
                                  "pages": {1: "原始文字"}, "corrector": "x",
                                  "elapsed": 0.0}
    at.session_state["step"] = 3
    at.run(timeout=120)
    assert not at.exception
    edit = [t for t in at.text_area if t.key == "edit_1"]
    assert edit and edit[0].value == "原始文字"
    # 模擬使用者編輯
    edit[0].set_value("修改後文字").run(timeout=120)
    assert at.session_state["edited"][1] == "修改後文字"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_step3_shows_editable_text_and_download -q`
Expected: FAIL（找不到 `edit_1` text_area）

- [ ] **Step 3: 取代 `with tab_out:` 區塊為完整實作**

把：

```python
with tab_out:
    st.info("（步驟③內容於 Task 6 實作）")
```

改成：

```python
with tab_out:
    st.subheader("步驟 3　對照編輯")
    if not ss.result:
        st.warning("請先完成『②　進行辨識』。")
    else:
        pages = ss.result["pages"]
        pnos = sorted(pages)
        st.caption(f"辨識方式：**{ss.result['mode']}** · 頁數 {len(pnos)} · "
                   f"耗時 {ss.result.get('elapsed', 0):.1f}s")
        if len(pnos) > 1:
            idx = pnos.index(ss.cur_page) if ss.cur_page in pnos else 0
            ss.cur_page = st.selectbox("選擇頁碼", pnos, index=idx, key="page_sel")
        else:
            ss.cur_page = pnos[0]

        if ss.preview is None and ss.file_path:
            with st.spinner("載入原圖…"):
                imgs = ocr_lib.render_hidpi(Path(ss.file_path), PREVIEW_DPI)
                ss.preview = {i + 1: im for i, im in enumerate(imgs)}

        col_left, col_right = st.columns(2)
        with col_left:
            st.caption(f"原圖（第 {ss.cur_page} 頁）· 滾輪縮放／拖曳／雙擊還原")
            img = (ss.preview or {}).get(ss.cur_page)
            if img is not None:
                zoomable_image(img, key=f"z{ss.cur_page}")
            else:
                st.info("此檔無可顯示之原圖。")
        with col_right:
            st.caption(f"辨識結果（第 {ss.cur_page} 頁）· 可直接編輯")
            cur = current_page_text(pages, ss.edited, ss.cur_page)
            new = st.text_area("編輯", value=cur, height=520,
                               key=f"edit_{ss.cur_page}", label_visibility="collapsed")
            ss.edited[ss.cur_page] = new

        base = Path(ss.file_name).stem if ss.file_name else "result"
        final_pages = {p: current_page_text(pages, ss.edited, p) for p in pnos}
        c1, c2 = st.columns([1, 1])
        with c1:
            st.download_button("⬇ 下載辨識結果（.txt）",
                               combine_pages(final_pages).encode("utf-8"),
                               file_name=f"{base}.txt", mime="text/plain",
                               type="primary", key="dl_txt")
        with c2:
            if st.button("🔄 辨識新檔案", key="reset"):
                ss.file_path = ss.file_name = ss.result = None
                ss.is_born_digital = ss.n_pages = None
                ss.edited = {}
                ss.preview = None
                ss.cur_page = 1
                ss.step = 1
                st.rerun()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py::test_step3_shows_editable_text_and_download -q`
Expected: PASS

- [ ] **Step 5: 跑全部測試**

Run: `cd /d E:\OCR-Work-platform && python -m pytest test_ocr_app_pro.py -q`
Expected: PASS（全部）

- [ ] **Step 6: Commit（非 git 倉庫則略過）**

```bash
git add ocr_app_pro.py test_ocr_app_pro.py
git commit -m "feat(pro): step 3 compare + inline edit + download"
```

---

## Task 7：打包（啟動檔、README）與實機啟動

**Files:**
- Create: `E:\OCR-Work-platform\run_pro.bat`
- Modify: `E:\OCR-Work-platform\README.md`

- [ ] **Step 1: 建立 `run_pro.bat`**

```bat
@echo off
REM 啟動財報文件智慧辨識（進階版）
cd /d "%~dp0"
python -m streamlit run ocr_app_pro.py --server.port 8503
```

- [ ] **Step 2: README 補上進階版段落**

在 `README.md` 的「啟動」段落後，新增：

```markdown
## 進階版（ocr_app_pro.py）

比簡單版多「原圖對照」與「結果線上編輯」；辨識固定走 PaddleOCR ＋ DeepSeek
（born-digital 自動文字層）。三步驟分頁：① 上傳 → ② 辨識 → ③ 對照編輯（左原圖、右可編輯）。

啟動：`streamlit run ocr_app_pro.py --server.port 8503`，或執行 `run_pro.bat`，
瀏覽器開 http://localhost:8503 。
```

- [ ] **Step 3: 實機啟動確認（背景）**

Run: `cd /d E:\OCR-Work-platform && start "" python -m streamlit run ocr_app_pro.py --server.headless true --server.port 8503`
等約 8 秒後 Run: `curl -s -o NUL -w "%{http_code}" http://localhost:8503`
Expected: `200`

- [ ] **Step 4: Commit（非 git 倉庫則略過）**

```bash
git add run_pro.bat README.md
git commit -m "chore(pro): launch script + README"
```

---

## 完成後（舊網頁退役）

- 舊 `E:\PJ_OCR\ocr_gui.py`（調參工作台）依規格退役：不再啟動。若使用者確認要刪除實體檔，再另行處理（本計畫不刪）。
