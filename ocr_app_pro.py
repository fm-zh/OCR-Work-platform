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
    load_env_file, resolve_deepseek_key, combine_pages, current_page_text,
    detect_file,
)

# 啟動時讀取同資料夾的 .env（DeepSeek 金鑰等），真實環境變數優先。
load_env_file(Path(__file__).resolve().parent / ".env")

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
with tab_run:
    st.subheader("步驟 2　進行辨識（PaddleOCR ＋ DeepSeek）")
    if not ss.file_path:
        st.warning("請先在『①　上傳檔案』分頁上傳檔案。")
    else:
        st.write(f"待辨識檔案：**{ss.file_name}**（{ss.n_pages} 頁）")
        if ss.is_born_digital:
            st.success("此檔含文字層，將直接擷取（不需 OCR / LLM，最快最準）。")
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
                    deepseek_key=resolve_deepseek_key(),
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
                st.caption("若為 DeepSeek 金鑰／網路問題，請確認專案 .env 內的 "
                           "DEEPSEEK_API_KEY 有效後重試。")
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
