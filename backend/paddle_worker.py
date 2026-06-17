"""本地 PaddleOCR worker（在 `paddleocr` conda 環境 / Python 3.11 執行）。

後端（base 3.13，無法 import paddle）以子程序呼叫本檔：
    <paddleocr-env-python> paddle_worker.py img1.png img2.png ...
每張圖回傳偵測到的文字框（含 bbox 座標），結果以 JSON 印到 stdout：
    {"results": {"img1.png": [{"text","x0","x1","y0","y1","cx","cy","score"}, ...], ...}}

關鍵設定（見記憶 local-paddleocr-table-solution）：
- use_doc_orientation_classify=True：自動把「橫式寬表被 90° 塞進直式頁」的側躺頁轉正。
- enable_mkldnn=False：否則 paddlepaddle 3.3 在 CPU 會 PIR oneDNN crash。
模型只在程序啟動時載入一次，故後端應「一次傳入該任務所有頁」以攤平初始化成本。
"""
import sys
import json


def main(paths):
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(
        use_doc_orientation_classify=True,
        use_doc_unwarping=False,
        use_textline_orientation=True,
        enable_mkldnn=False,
        # PP-OCRv5 server 模型：辨識力明顯優於預設的 PP-OCRv6_medium，能正確讀出
        # 「清晰但被 medium 誤讀」的小字數字/科目名（如 301,938,133、法定盈餘公積）；
        # GPU 上仍約 1–2 秒/頁。det side_len 提高避免密集表被降採樣。
        text_detection_model_name="PP-OCRv5_server_det",
        text_recognition_model_name="PP-OCRv5_server_rec",
        text_det_limit_type="max",
        text_det_limit_side_len=2000,
        lang="chinese_cht",
    )
    results = {}
    for p in paths:
        boxes = []
        try:
            res = ocr.predict(p)[0]
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
        except Exception as exc:  # noqa: BLE001
            print(f"[worker] OCR failed for {p}: {exc}", file=sys.stderr)
        results[p] = boxes
        print(f"[worker] {p}: {len(boxes)} boxes", file=sys.stderr)
    json.dump({"results": results}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
