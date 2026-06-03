"""進階版辨識網頁 — PaddleOCR + DeepSeek，兩步驟分頁（會自動跳轉）。
步驟1：選擇檔案 → 預覽確認 → 進行辨識；步驟2：辨識結果與對照編輯。
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
    load_env_file, resolve_deepseek_key, combine_pages, current_page_text,
    detect_file,
)

# 啟動時讀取同資料夾的 .env（DeepSeek 金鑰等），真實環境變數優先。
load_env_file(Path(__file__).resolve().parent / ".env")

PREVIEW_DPI = 150
THUMB_BOX = (400, 560)  # 步驟1 檔案縮圖的規定範圍（寬, 高，px），等比縮放後置入此框內

st.set_page_config(page_title="OCR-Work-platform", page_icon="🛠️", layout="wide")

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

st.title("🛠️ OCR-Work-platform")
st.caption("PaddleOCR ＋ DeepSeek 校正 · 預覽確認 · 原圖對照 · 結果可線上編輯"
           "（內含文字層之 PDF 自動走文字層擷取）")


# ---------------------------------------------------------------------------
# 步驟分頁列（可控、完成後自動跳轉）
# ---------------------------------------------------------------------------
STEP_LABELS = ["①　選擇檔案 / 預覽 / 辨識", "②　結果與對照編輯"]
_nav = st.columns(2)
for _i, _col in enumerate(_nav, start=1):
    _cur = (ss.step == _i)
    _reachable = (_i == 1) or (ss.result is not None)
    if _col.button(STEP_LABELS[_i - 1], key=f"nav{_i}",
                   type=("primary" if _cur else "secondary"),
                   use_container_width=True,
                   disabled=(not _reachable and not _cur)):
        if _reachable and not _cur:
            ss.step = _i
            st.rerun()
st.divider()


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


def _ensure_preview() -> None:
    """渲染原圖預覽（快取於 session）。"""
    if ss.preview is None and ss.file_path:
        with st.spinner("載入原圖預覽…"):
            imgs = ocr_lib.render_hidpi(Path(ss.file_path), PREVIEW_DPI)
            ss.preview = {i + 1: im for i, im in enumerate(imgs)}


# ===========================================================================
# 步驟 1：選擇檔案 → 預覽確認 → 進行辨識
# ===========================================================================
if ss.step == 1:
    st.subheader("步驟 1　選擇檔案 → 預覽確認 → 進行辨識")
    up = st.file_uploader("拖曳或點選上傳（PDF / JPG / PNG / WEBP）",
                          type=["pdf", "jpg", "jpeg", "png", "webp"], key="uploader")
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

    if not ss.file_path:
        st.info("請先上傳要辨識的檔案。")
    else:
        if ss.is_born_digital:
            st.info("🔎 此檔內含文字層（born-digital）→ 將直接擷取文字層（數字 100% 精準）。")
        else:
            st.info("🔎 此檔為掃描影像／截圖 → 將以 PaddleOCR ＋ DeepSeek 辨識。")

        _ensure_preview()
        if ss.n_pages and ss.n_pages > 1:
            pnos = list(range(1, ss.n_pages + 1))
            idx = pnos.index(ss.cur_page) if ss.cur_page in pnos else 0
            ss.cur_page = st.selectbox("預覽頁碼", pnos, index=idx, key="prev_page")
        st.caption(f"檔案縮圖預覽（第 {ss.cur_page} / {ss.n_pages} 頁）")
        img = (ss.preview or {}).get(ss.cur_page)
        if img is not None:
            thumb = img.convert("RGB").copy()
            thumb.thumbnail(THUMB_BOX)  # 等比縮放至 THUMB_BOX 範圍內
            st.image(thumb)

        st.markdown("確認上方為要辨識的檔案後，按下方按鈕開始辨識（完成後會自動跳到步驟 2）。")
        if st.button("✅ 確認無誤，開始辨識", type="primary", key="run_recognize"):
            bar = st.progress(0, text="準備中…")
            seen = {"n": 0}

            def _cb(msg):
                seen["n"] += 1
                bar.progress(min(90, seen["n"] * 22), text=msg)

            t0 = time.time()
            try:
                res = ocr_recognize.recognize(
                    ss.file_path, corrector="deepseek",
                    deepseek_key=resolve_deepseek_key(), progress=_cb)
                res["elapsed"] = time.time() - t0
                bar.progress(100, text="完成")
                ss.result = res
                ss.edited = {}
                ss.cur_page = 1
                ss.step = 2
                st.rerun()
            except Exception as exc:
                bar.empty()
                st.error(f"❌ 辨識失敗：{type(exc).__name__}: {exc}")
                st.caption("若為 DeepSeek 金鑰／網路問題，請確認專案 .env 內的 "
                           "DEEPSEEK_API_KEY 有效後重試。")


# ===========================================================================
# 步驟 2：辨識結果與對照編輯
# ===========================================================================
else:
    st.subheader("步驟 2　辨識結果與對照編輯")
    if not ss.result:
        st.warning("尚未有辨識結果，請回『①　選擇檔案 / 預覽 / 辨識』。")
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

        _ensure_preview()
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
