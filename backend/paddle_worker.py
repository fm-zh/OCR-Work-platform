"""本地 PaddleOCR worker（在 `paddleocr` conda 環境 / Python 3.11 執行）。

後端（base 3.13，無法 import paddle）以子程序呼叫本檔：
    <paddleocr-env-python> paddle_worker.py img1.png img2.png ...
每張圖回傳偵測到的文字框（含 bbox 座標），結果以 JSON 印到 stdout：
    {"results": {"img1.png": [{"text","x0","x1","y0","y1","cx","cy","score"}, ...], ...}}

雙模型擇優（見記憶 local-paddleocr-table-solution）：對每頁同時用
  • PP-OCRv6_medium（預設）— 在「有底線的總計列」等情境較穩
  • PP-OCRv5_server     — 對清晰小字（金額/科目名）辨識力較強
兩者各跑一次，再依「信心分數」逐格擇優合併（信心已驗證能正確指示哪個對）。
為控制 GPU 記憶體，兩模型「逐一載入、跑完釋放再載下一個」。

關鍵設定：
- use_doc_orientation_classify=True：把「橫式寬表被 90° 塞進直式頁」的側躺頁自動轉正。
- enable_mkldnn=False：否則 paddlepaddle 3.3 在 CPU 會 PIR oneDNN crash。
"""
import sys
import json

COMMON = dict(
    use_doc_orientation_classify=True,
    use_doc_unwarping=False,
    use_textline_orientation=True,
    enable_mkldnn=False,
    text_det_limit_type="max",
    text_det_limit_side_len=2000,
    lang="chinese_cht",
)
# 兩個模型設定：預設(medium) 與 server。
MODEL_CONFIGS = [
    {},  # 預設：PP-OCRv6_medium det+rec
    {"text_detection_model_name": "PP-OCRv5_server_det",
     "text_recognition_model_name": "PP-OCRv5_server_rec"},
]


def _extract(res) -> list:
    boxes = []
    for t, poly, sc in zip(res["rec_texts"], res["rec_polys"], res["rec_scores"]):
        xs = [float(pt[0]) for pt in poly]
        ys = [float(pt[1]) for pt in poly]
        boxes.append({
            "text": t,
            "x0": round(min(xs)), "x1": round(max(xs)),
            "y0": round(min(ys)), "y1": round(max(ys)),
            "cx": round(sum(xs) / len(xs)), "cy": round(sum(ys) / len(ys)),
            "score": round(float(sc), 3),
        })
    return boxes


def _same_cell(a: dict, b: dict) -> bool:
    """兩框是否為同一實體儲存格：垂直中心相近且水平區間重疊。"""
    tol = max(a["y1"] - a["y0"], b["y1"] - b["y0"]) * 0.6 + 4
    if abs(a["cy"] - b["cy"]) > tol:
        return False
    ix = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
    return ix > 0.3 * min(a["x1"] - a["x0"], b["x1"] - b["x0"])


def _merge(a_boxes: list, b_boxes: list) -> list:
    """逐格擇優合併兩模型結果：配對到的取信心高者，未配對者皆保留。"""
    merged = []
    used = [False] * len(b_boxes)
    for a in a_boxes:
        cand = [(j, b) for j, b in enumerate(b_boxes)
                if not used[j] and _same_cell(a, b)]
        if cand:
            j, b = max(cand, key=lambda jb: jb[1]["score"])
            used[j] = True
            merged.append(b if b["score"] > a["score"] else a)
        else:
            merged.append(a)
    for j, b in enumerate(b_boxes):
        if not used[j]:
            merged.append(b)
    return merged


def main(paths):
    from paddleocr import PaddleOCR
    import gc
    try:
        import paddle
    except Exception:  # noqa: BLE001
        paddle = None

    per_model = []  # 每個模型對每頁的 boxes：{path: [boxes]}
    for cfg in MODEL_CONFIGS:
        ocr = PaddleOCR(**COMMON, **cfg)
        out = {}
        for p in paths:
            try:
                out[p] = _extract(ocr.predict(p)[0])
            except Exception as exc:  # noqa: BLE001
                print(f"[worker] OCR failed ({cfg}) for {p}: {exc}", file=sys.stderr)
                out[p] = []
        per_model.append(out)
        # 釋放此模型，再載下一個（控制 GPU 記憶體）
        del ocr
        gc.collect()
        if paddle is not None:
            try:
                paddle.device.cuda.empty_cache()
            except Exception:  # noqa: BLE001
                pass

    results = {}
    for p in paths:
        merged = _merge(per_model[0].get(p, []), per_model[1].get(p, []))
        results[p] = merged
        print(f"[worker] {p}: {len(merged)} boxes "
              f"(medium {len(per_model[0].get(p, []))} + server {len(per_model[1].get(p, []))})",
              file=sys.stderr)
    json.dump({"results": results}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
