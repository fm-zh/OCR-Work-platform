"""End-user web app — 財報文件智慧辨識（PaddleOCR + Claude）.

三步驟分頁導引：① 上傳檔案 → ② 進行辨識 → ③ 輸出結果

啟動：  streamlit run ocr_app.py
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import streamlit as st

import ocr_lib
import ocr_recognize

st.set_page_config(page_title="財報文件智慧辨識", page_icon="📄", layout="wide")

ss = st.session_state
ss.setdefault("step", 1)
ss.setdefault("file_path", None)
ss.setdefault("file_name", None)
ss.setdefault("is_born_digital", None)
ss.setdefault("n_pages", None)
ss.setdefault("result", None)

st.title("📄 財報文件智慧辨識系統")
st.caption("辨識方法：PaddleOCR ＋ Claude（內含文字層之 PDF 自動改用文字層擷取，數字 100% 精準）")

# ---------------------------------------------------------------------------
# 進度指示器（分頁導引）
# ---------------------------------------------------------------------------
STEPS = ["①　上傳檔案", "②　進行辨識", "③　輸出結果"]
prog_cols = st.columns(3)
for idx, col in enumerate(prog_cols, start=1):
    name = STEPS[idx - 1]
    if ss.step == idx:
        col.success(f"**{name}**　← 進行中")
    elif ss.step > idx:
        col.info(f"{name}　✅ 已完成")
    else:
        col.markdown(f"<div style='padding:8px;color:#999'>{name}</div>", unsafe_allow_html=True)

st.divider()
tab_upload, tab_run, tab_out = st.tabs(STEPS)


# ===========================================================================
# 步驟 1：上傳檔案
# ===========================================================================
with tab_upload:
    st.subheader("步驟 1　上傳要辨識的檔案")
    st.write("支援 **PDF** 與圖片（**JPG / PNG / WEBP**）。財報、損益表、資產負債表、稅報等皆可。")
    up = st.file_uploader("拖曳或點選上傳檔案", type=["pdf", "jpg", "jpeg", "png", "webp"],
                          key="uploader")
    if up is not None:
        updir = Path(tempfile.gettempdir()) / "ocr_app_uploads"
        updir.mkdir(exist_ok=True)
        dest = updir / up.name
        dest.write_bytes(up.getbuffer())
        # 變更檔案時重置結果
        if ss.file_path != str(dest):
            ss.result = None
        ss.file_path = str(dest)
        ss.file_name = up.name

        try:
            chars = ocr_lib.text_layer_char_count(dest)
            ss.is_born_digital = chars >= 50
        except Exception:
            chars, ss.is_born_digital = 0, False
        try:
            import fitz
            with fitz.open(dest) as doc:
                ss.n_pages = doc.page_count
        except Exception:
            ss.n_pages = 1

        ss.step = max(ss.step, 2)
        st.success(f"✅ 已上傳：**{up.name}**（{ss.n_pages} 頁）")
        if ss.is_born_digital:
            st.info(f"🔎 偵測：此檔內含**文字層（born-digital）**，將直接擷取文字層 "
                    f"→ 數字 100% 精準（文字層字元數：{chars}）。")
        else:
            st.info("🔎 偵測：此檔為**掃描影像／截圖**，將以 **PaddleOCR ＋ Claude** 辨識。")
        st.markdown("➡️ 請點選上方 **②　進行辨識** 分頁繼續。")
    elif ss.file_name:
        st.info(f"目前已上傳：**{ss.file_name}**（重新上傳可更換檔案）")


# ===========================================================================
# 步驟 2：進行辨識
# ===========================================================================
with tab_run:
    st.subheader("步驟 2　進行辨識")
    if not ss.file_path:
        st.warning("請先回到『①　上傳檔案』分頁上傳檔案。")
    else:
        st.write(f"待辨識檔案：**{ss.file_name}**（{ss.n_pages} 頁）")
        if ss.is_born_digital:
            st.success("此檔含文字層，將直接擷取（不需 OCR / LLM，最快最準）。")
            corrector_key, ds_key = "claude", ""
        else:
            corrector = st.radio("LLM 校正引擎", ["Claude（推薦）", "DeepSeek"],
                                  horizontal=True, key="corrector_choice")
            corrector_key = "deepseek" if corrector.startswith("DeepSeek") else "claude"
            ds_key = ""
            if corrector_key == "deepseek":
                ds_key = st.text_input("DeepSeek API Key", type="password", key="ds_key_in")

        disabled = (not ss.is_born_digital and corrector_key == "deepseek" and not ds_key)
        if st.button("🚀 開始辨識", type="primary", disabled=disabled,
                     help="需要 DeepSeek API Key" if disabled else ""):
            bar = st.progress(0, text="準備中…")
            seen = {"n": 0}

            def cb(msg):
                seen["n"] += 1
                bar.progress(min(90, seen["n"] * 22), text=msg)

            t0 = time.time()
            try:
                res = ocr_recognize.recognize(
                    ss.file_path, corrector=corrector_key,
                    deepseek_key=ds_key, progress=cb)
                res["elapsed"] = time.time() - t0
                bar.progress(100, text="完成")
                ss.result = res
                ss.step = 3
                st.success(f"✅ 辨識完成（{res['mode']}，耗時 {res['elapsed']:.1f} 秒）。"
                           "　請點選上方 **③　輸出結果** 分頁查看與下載。")
            except Exception as exc:
                bar.empty()
                st.error(f"❌ 辨識失敗：{type(exc).__name__}: {exc}")
                if corrector_key == "claude":
                    st.caption("若 Claude CLI 無法使用，可改選 DeepSeek 引擎重試。")


# ===========================================================================
# 步驟 3：輸出結果
# ===========================================================================
with tab_out:
    st.subheader("步驟 3　輸出辨識結果")
    if not ss.result:
        st.warning("請先完成『②　進行辨識』。")
    else:
        res = ss.result
        pages = res["pages"]
        st.caption(f"辨識方式：**{res['mode']}**　·　校正：{res['corrector']}　·　"
                   f"頁數：{len(pages)}　·　耗時：{res.get('elapsed', 0):.1f}s")

        if len(pages) > 1:
            combined = "\n\n".join(f"===== 第 {p} 頁 =====\n{pages[p]}"
                                   for p in sorted(pages))
            page_tabs = st.tabs([f"第 {p} 頁" for p in sorted(pages)])
            for ptab, pno in zip(page_tabs, sorted(pages)):
                with ptab:
                    st.text_area(f"第 {pno} 頁", pages[pno], height=460,
                                 label_visibility="collapsed", key=f"out_{pno}")
        else:
            only = sorted(pages)[0]
            combined = pages[only]
            st.text_area("辨識結果", pages[only], height=460,
                         label_visibility="collapsed", key="out_single")

        base = Path(ss.file_name).stem if ss.file_name else "result"
        c1, c2 = st.columns([1, 1])
        with c1:
            st.download_button("⬇ 下載辨識結果（.txt）", combined.encode("utf-8"),
                               file_name=f"{base}.txt", mime="text/plain",
                               type="primary", key="dl_txt")
        with c2:
            if st.button("🔄 辨識新檔案", key="reset"):
                ss.file_path = ss.file_name = ss.result = None
                ss.is_born_digital = ss.n_pages = None
                ss.step = 1
                st.rerun()
