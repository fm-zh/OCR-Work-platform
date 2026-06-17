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
