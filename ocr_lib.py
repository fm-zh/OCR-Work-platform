"""Shared OCR core: API client, PDF rendering, preprocessing, repacking.

Used by both the CLI batch script (ocr_eval.py) and the GUI (ocr_gui.py).
"""
from __future__ import annotations

import concurrent.futures
import contextlib
import json
import mimetypes
import os
import re
import secrets
import ssl
import tempfile
import time
import urllib.request
from dataclasses import dataclass, asdict, field
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageDraw

BASE_URL = "https://ollama_pjapi.theaken.com/v1"
API_KEY = "G9FUoY1VeEfUXWjyrR-9lPtiBlK2K3UCTSLiSIP9ejg"
MODEL = "paddleocr-remote"
DEFAULT_DPI = 400
PREVIEW_DPI = 150
SUBMIT_TIMEOUT = 60
POLL_TIMEOUT = 300
POLL_INTERVAL = 1.0
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# OCR API client
# ---------------------------------------------------------------------------

def _multipart_body(file_path: Path) -> tuple[bytes, str]:
    boundary = "----" + secrets.token_hex(16)
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n"
    ).encode() + file_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="model"\r\n\r\n{MODEL}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="language"\r\n\r\nauto\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    return body, boundary


def submit(file_path: Path) -> str:
    size = file_path.stat().st_size
    if size > MAX_UPLOAD_BYTES:
        raise ValueError(f"file {file_path.name} is {size} bytes, exceeds 20 MB API limit")
    body, boundary = _multipart_body(file_path)
    req = urllib.request.Request(
        f"{BASE_URL}/ocr/submit",
        method="POST",
        data=body,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": _USER_AGENT,
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=SUBMIT_TIMEOUT, context=_SSL_CTX) as r:
        return json.loads(r.read())["job_id"]


def poll(job_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT
    while True:
        req = urllib.request.Request(
            f"{BASE_URL}/ocr/jobs/{job_id}",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "User-Agent": _USER_AGENT,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
            data = json.loads(r.read())
        if data["status"] in ("done", "error"):
            return data
        if time.time() > deadline:
            raise TimeoutError(f"OCR job {job_id} not finished within {POLL_TIMEOUT}s")
        time.sleep(POLL_INTERVAL)


def ocr_file(file_path: Path) -> dict:
    job_id = submit(file_path)
    result = poll(job_id)
    if result["status"] == "error":
        raise RuntimeError(result.get("error") or "OCR API returned error status")
    return result


# ---------------------------------------------------------------------------
# Preprocessing parameters and pipeline
# ---------------------------------------------------------------------------

@dataclass
class PreprocessParams:
    do_remove_stamps: bool = False
    stamp_color: str = "red"        # "red" | "blue" | "any"
    stamp_sat_threshold: int = 60   # HSV saturation threshold (0-255)
    do_gray: bool = True
    do_bilateral: bool = True
    bilateral_sigma_color: int = 50
    bilateral_sigma_space: int = 50
    do_clahe: bool = True
    clahe_clip_limit: float = 2.0
    do_unsharp: bool = True
    unsharp_weight: float = 1.6
    do_otsu: bool = True
    do_crop_content: bool = False
    crop_padding: int = 50          # pixels (in render-DPI space)
    crop_white_threshold: int = 250  # pixels brighter than this are treated as background


def remove_colored_pixels(arr: np.ndarray, color: str = "red",
                          sat_threshold: int = 60) -> np.ndarray:
    """Replace colored pixels with white, preserving black/grayscale content.

    `color`:
      - "red"  : hues in {0..10, 170..180}
      - "blue" : hues in {100..130}
      - "any"  : all sufficiently-saturated pixels regardless of hue
    `sat_threshold`: HSV S value above which a pixel is considered colored.
    """
    if arr.ndim != 3:
        return arr  # already grayscale, nothing colored to remove
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    h, s, _v = cv2.split(hsv)
    sat_mask = s > sat_threshold
    if color == "red":
        hue_mask = (h <= 10) | (h >= 170)
    elif color == "blue":
        hue_mask = (h >= 100) & (h <= 130)
    elif color == "any":
        hue_mask = np.ones_like(h, dtype=bool)
    else:
        raise ValueError(f"unknown stamp color: {color}")
    mask = sat_mask & hue_mask
    result = arr.copy()
    result[mask] = [255, 255, 255]
    return result


def crop_to_content(img: Image.Image, padding: int = 50,
                    white_threshold: int = 250) -> Image.Image:
    """Crop `img` to the bounding box of non-white pixels, with `padding` px around.

    `white_threshold`: pixels with intensity >= this (after grayscale conversion)
    are considered background. Default 250 tolerates very light gray.
    """
    arr = np.asarray(img)
    if arr.ndim == 3:
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    else:
        gray = arr
    mask = gray < white_threshold
    if not mask.any():
        return img  # blank page — leave it alone
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    rmin, rmax = int(np.argmax(rows)), int(len(rows) - 1 - np.argmax(rows[::-1]))
    cmin, cmax = int(np.argmax(cols)), int(len(cols) - 1 - np.argmax(cols[::-1]))
    h, w = arr.shape[:2]
    rmin = max(0, rmin - padding)
    rmax = min(h, rmax + padding + 1)
    cmin = max(0, cmin - padding)
    cmax = min(w, cmax + padding + 1)
    return img.crop((cmin, rmin, cmax, rmax))


def render_hidpi(pdf: Path, dpi: int) -> list[Image.Image]:
    images: list[Image.Image] = []
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    with fitz.open(pdf) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            images.append(img)
    return images


# ---------------------------------------------------------------------------
# Born-digital PDF text layer (skip OCR when the PDF already has real text)
# ---------------------------------------------------------------------------

def text_layer_char_count(pdf: Path) -> int:
    """Total non-whitespace characters in the PDF's embedded text layer.

    0 (or near-0) ⇒ scanned/image PDF that genuinely needs OCR. A large value
    ⇒ born-digital PDF whose text can be extracted losslessly (digit-perfect),
    which image OCR can never match on long numbers.
    """
    total = 0
    with fitz.open(pdf) as doc:
        for page in doc:
            total += len(page.get_text().strip())
    return total


def has_text_layer(pdf: Path, min_chars: int = 50) -> bool:
    """True if the PDF carries a usable embedded text layer (born-digital)."""
    return text_layer_char_count(pdf) >= min_chars


def _rows_from_page(page, gap_pt: float = 15.0) -> str:
    """Reconstruct tab-separated rows from a page's embedded text.

    Groups text lines whose vertical centres fall within ~0.6× the median line
    height into one row, sorts each row left→right, and tab-joins the cells.
    Turns a multi-column table (code / name / amount) back into rows without
    OCR. Falls back to plain reading-order text if the page has no line dict.
    """
    dct = page.get_text("dict")
    lines = []
    for block in dct.get("blocks", []):
        for ln in block.get("lines", []):
            txt = "".join(s["text"] for s in ln.get("spans", [])).strip()
            if not txt:
                continue
            x0 = ln["bbox"][0]
            y_center = (ln["bbox"][1] + ln["bbox"][3]) / 2
            height = ln["bbox"][3] - ln["bbox"][1]
            lines.append((y_center, x0, height, txt))
    if not lines:
        return page.get_text().strip()
    lines.sort(key=lambda r: (r[0], r[1]))
    median_h = sorted(l[2] for l in lines)[len(lines) // 2]
    tol = max(1.0, median_h * 0.6)
    rows: list[list[tuple[float, str]]] = []
    cur: list[tuple[float, str]] = []
    cy = None
    for y_center, x0, _h, txt in lines:
        if cy is None or abs(y_center - cy) <= tol:
            cur.append((x0, txt))
            cy = y_center if cy is None else (cy + y_center) / 2
        else:
            rows.append(cur)
            cur = [(x0, txt)]
            cy = y_center
    if cur:
        rows.append(cur)
    out_lines = []
    for row in rows:
        row.sort(key=lambda c: c[0])
        out_lines.append("\t".join(t for _x, t in row))
    return "\n".join(out_lines)


def extract_text_layer(pdf: Path) -> dict[int, str]:
    """Return {page_no: text} from a born-digital PDF's embedded text layer,
    with table rows reconstructed (see _rows_from_page). 1-based page numbers."""
    result: dict[int, str] = {}
    with fitz.open(pdf) as doc:
        for i, page in enumerate(doc):
            result[i + 1] = _rows_from_page(page)
    return result


def preprocess_images(images: list[Image.Image], params: PreprocessParams) -> list[Image.Image]:
    """Apply the configurable preprocessing pipeline to each page."""
    clahe = cv2.createCLAHE(clipLimit=params.clahe_clip_limit, tileGridSize=(8, 8))
    out: list[Image.Image] = []
    for img in images:
        arr = np.asarray(img)
        # Step 0: stamp removal (must run on RGB, before grayscale)
        if params.do_remove_stamps:
            arr = remove_colored_pixels(arr, params.stamp_color,
                                        params.stamp_sat_threshold)
        pixel_steps = (params.do_gray or params.do_bilateral or params.do_clahe
                       or params.do_unsharp or params.do_otsu)
        if pixel_steps:
            work = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
            if params.do_bilateral:
                work = cv2.bilateralFilter(
                    work, d=7,
                    sigmaColor=params.bilateral_sigma_color,
                    sigmaSpace=params.bilateral_sigma_space,
                )
            if params.do_clahe:
                work = clahe.apply(work)
            if params.do_unsharp:
                blurred = cv2.GaussianBlur(work, (0, 0), sigmaX=1.5)
                w = params.unsharp_weight
                work = cv2.addWeighted(work, w, blurred, -(w - 1.0), 0)
            if params.do_otsu:
                _, work = cv2.threshold(work, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            mode = "L" if work.ndim == 2 else "RGB"
            result = Image.fromarray(work, mode=mode)
        else:
            # Use `arr` (may have been modified by stamp removal)
            result = Image.fromarray(arr) if params.do_remove_stamps else img.copy()
        # Final step: crop to content bbox (works on any mode)
        if params.do_crop_content:
            result = crop_to_content(result, padding=params.crop_padding,
                                     white_threshold=params.crop_white_threshold)
        out.append(result)
    return out


def _is_binary(img: Image.Image) -> bool:
    """True if image only contains pure-black/pure-white pixels."""
    if img.mode == "1":
        return True
    if img.mode != "L":
        return False
    uniq = np.unique(np.asarray(img))
    return uniq.size <= 2 and set(int(v) for v in uniq).issubset({0, 255})


def pack_to_pdf(images: list[Image.Image], dest, resolution: int = DEFAULT_DPI):
    """Pack images into a multi-page PDF.

    Compression choice:
      - All pages binary (pure black/white) -> mode "1" -> Pillow uses CCITT G4
        (lossless, ~95% smaller than JPEG).
      - Otherwise -> mode "RGB" -> Pillow uses JPEG (lossy but compact for photos).

    `dest` may be a Path (str / pathlib.Path) or a writable binary file-like object.
    Returns `dest` unchanged.
    """
    if not images:
        raise ValueError("no images to pack")
    all_binary = all(_is_binary(im) for im in images)
    target_mode = "1" if all_binary else "RGB"
    converted = [im.convert(target_mode) for im in images]
    first, rest = converted[0], converted[1:]
    first.save(dest, "PDF", save_all=True, append_images=rest, resolution=resolution)
    return dest


@contextlib.contextmanager
def augmented_pdf(pdf: Path, dpi: int, params: PreprocessParams | None):
    """Yield a temp PDF: re-rendered (and optionally preprocessed) pages of `pdf`.

    If `params` is None, only re-render at `dpi` (the old "strategy B" behavior).
    """
    images = render_hidpi(pdf, dpi)
    if params is not None:
        images = preprocess_images(images, params)
    fd, tmp_str = tempfile.mkstemp(prefix=f"{pdf.stem}.", suffix=".pdf")
    tmp = Path(tmp_str)
    try:
        os.close(fd)
        pack_to_pdf(images, tmp, resolution=dpi)
        yield tmp
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# OCR txt parsing (used by GUI to load baseline)
# ---------------------------------------------------------------------------

_PAGE_HEADER_RE = re.compile(r"^-----\s*page\s+(\d+)\s*\(confidence=([^\)]+)\)\s*-----\s*$")


def parse_per_page_text(txt_path: Path) -> dict[int, dict]:
    """Parse a `<stem>.ocr/*.txt` file and return {page_no: {'text': str, 'confidence': str}}.

    Reads the '## per-page detail' section produced by ocr_eval._format_output.
    Returns empty dict if no per-page detail section is found.
    """
    text = txt_path.read_text(encoding="utf-8")
    if "## per-page detail" not in text:
        return {}
    _, detail = text.split("## per-page detail", 1)
    result: dict[int, dict] = {}
    current_page: int | None = None
    current_conf: str = ""
    current_lines: list[str] = []
    for line in detail.splitlines():
        m = _PAGE_HEADER_RE.match(line)
        if m:
            if current_page is not None:
                result[current_page] = {
                    "text": "\n".join(current_lines).strip(),
                    "confidence": current_conf,
                }
            current_page = int(m.group(1))
            current_conf = m.group(2)
            current_lines = []
        elif current_page is not None:
            current_lines.append(line)
    if current_page is not None:
        result[current_page] = {
            "text": "\n".join(current_lines).strip(),
            "confidence": current_conf,
        }
    return result


def params_metadata_block(params: PreprocessParams, dpi: int) -> list[str]:
    """Return list of `# key: value` lines describing the current settings.

    Used by GUI when generating a downloadable txt of an OCR run.
    """
    lines = [f"# dpi           : {dpi}"]
    for k, v in asdict(params).items():
        lines.append(f"# {k:<14}: {v}")
    return lines


# ---------------------------------------------------------------------------
# Strip-split OCR: bypass server-side downsampling on tall pages
# ---------------------------------------------------------------------------

@dataclass
class StripInfo:
    image: Image.Image       # the strip's pixels
    page_idx: int            # 0-based index into the original PDF page list
    strip_idx: int           # 0-based index within the page (top→bottom)
    y_start: int             # vertical position in the source page (pixels)
    y_end: int               # vertical position in the source page (pixels)
    overlaps_next: bool      # True ↔ this strip's tail overlaps next strip's head


def _find_whitespace_row(gray: np.ndarray, y_target: int,
                         search_ratio: float, white_threshold: int) -> int | None:
    """Return the y of a row within ±search_ratio*h of y_target where every
    pixel >= white_threshold (a pure-blank horizontal line). None if no row found."""
    h = gray.shape[0]
    r = max(1, int(h * search_ratio))
    y_min, y_max = max(0, y_target - r), min(h, y_target + r)
    if y_min >= y_max:
        return None
    is_white_row = (gray[y_min:y_max] >= white_threshold).all(axis=1)
    if not is_white_row.any():
        return None
    candidates = np.where(is_white_row)[0] + y_min
    best = candidates[int(np.argmin(np.abs(candidates - y_target)))]
    return int(best)


def split_into_strips(image: Image.Image, n_strips: int = 3,
                      search_ratio: float = 0.1, overlap_px: int = 80,
                      white_threshold: int = 250) -> list[StripInfo]:
    """Vertically split `image` into n_strips, preferring clean whitespace rows.

    For each of the n_strips-1 boundaries near y = h*k/n_strips:
      - search for a pure-white row within ±search_ratio*h
      - if found → split cleanly there (no overlap)
      - else → split at y_target with `overlap_px` of vertical overlap between
        the adjacent strips, so callers can dedup text later
    """
    if n_strips < 2:
        return [StripInfo(image, 0, 0, 0, image.height, False)]
    arr = np.asarray(image)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
    h = gray.shape[0]

    # Decide each boundary: (y_split, needs_overlap)
    boundaries: list[tuple[int, bool]] = []
    for k in range(1, n_strips):
        y_target = h * k // n_strips
        y_white = _find_whitespace_row(gray, y_target, search_ratio, white_threshold)
        if y_white is not None:
            boundaries.append((y_white, False))
        else:
            boundaries.append((y_target, True))

    # Materialize strip y-ranges
    strips: list[StripInfo] = []
    y_cursor = 0
    half = overlap_px // 2
    for i, (y_split, needs_overlap) in enumerate(boundaries):
        y_end = min(h, y_split + half) if needs_overlap else y_split
        strip_img = image.crop((0, y_cursor, image.width, y_end))
        strips.append(StripInfo(strip_img, 0, i, y_cursor, y_end, needs_overlap))
        y_cursor = max(0, y_split - half) if needs_overlap else y_split
    # Tail strip
    strip_img = image.crop((0, y_cursor, image.width, h))
    strips.append(StripInfo(strip_img, 0, len(boundaries), y_cursor, h, False))
    return strips


def draw_split_lines(image: Image.Image, strips: list[StripInfo],
                     clean_color=(0, 200, 0), overlap_color=(255, 80, 80),
                     line_width: int = 4) -> Image.Image:
    """Draw green/red horizontal lines on a copy of `image` to visualize splits.

    Green = clean split (no overlap), red = overlap region midline.
    """
    out = image.convert("RGB").copy()
    draw = ImageDraw.Draw(out)
    for i in range(len(strips) - 1):
        s = strips[i]
        if s.overlaps_next:
            y_mid = (s.y_end + strips[i + 1].y_start) // 2
            draw.line([(0, y_mid), (out.width, y_mid)], fill=overlap_color, width=line_width)
        else:
            draw.line([(0, s.y_end), (out.width, s.y_end)], fill=clean_color, width=line_width)
    return out


def _ocr_one_strip(strip_image: Image.Image, dpi: int) -> dict:
    """Pack one strip as a single-page PDF and OCR it."""
    fd, tmp_str = tempfile.mkstemp(prefix="strip_", suffix=".pdf")
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        pack_to_pdf([strip_image], tmp, resolution=dpi)
        return ocr_file(tmp)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def ocr_strips_parallel(strips: list[StripInfo], dpi: int) -> list[dict]:
    """Submit OCR for all strips concurrently; return results in input order."""
    if not strips:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(strips)) as ex:
        futures = [ex.submit(_ocr_one_strip, s.image, dpi) for s in strips]
        return [f.result() for f in futures]


def _dedup_overlap_head(prev_text: str, next_text: str,
                        max_check_lines: int = 6,
                        min_ratio: float = 0.6) -> str:
    """Strip leading lines from `next_text` that fuzzy-match the tail of `prev_text`.

    Tries every (j tail lines × k head lines) pair within `max_check_lines`;
    if best fuzzy similarity ≥ min_ratio, drop the first matched k head lines.
    """
    prev_lines = [ln for ln in prev_text.splitlines() if ln.strip()]
    next_lines = next_text.splitlines()
    if not prev_lines or not next_lines:
        return next_text
    best_k = 0
    best_ratio = min_ratio
    for k in range(1, min(max_check_lines, len(next_lines)) + 1):
        head = "\n".join(next_lines[:k])
        for j in range(1, min(max_check_lines, len(prev_lines)) + 1):
            tail = "\n".join(prev_lines[-j:])
            ratio = SequenceMatcher(None, tail, head).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_k = k
    return "\n".join(next_lines[best_k:]) if best_k else next_text


_LEADING_PAGE_MARKER_RE = re.compile(r"^\s*---\s*第\s*\d+\s*頁\s*---\s*\n?")


def _clean_strip_text(text: str) -> str:
    """Drop the API-injected '--- 第 N 頁 ---' wrapper from a strip's full_text."""
    return _LEADING_PAGE_MARKER_RE.sub("", text or "", count=1).strip()


def merge_strip_results(strips: list[StripInfo], results: list[dict]) -> dict:
    """Re-stitch per-strip OCR results into a single API-shaped dict.

    Per-page confidence is weighted by char count (a strip with 5 chars at
    confidence 0.5 should not drag down a strip with 500 chars at 0.97).
    """
    from collections import defaultdict
    by_page: dict[int, list[tuple[StripInfo, dict]]] = defaultdict(list)
    for s, r in zip(strips, results):
        by_page[s.page_idx].append((s, r))

    final_pages = []
    grand_weighted_sum = 0.0
    grand_total_chars = 0
    for page_idx in sorted(by_page):
        items = sorted(by_page[page_idx], key=lambda x: x[0].strip_idx)
        merged_text = ""
        weighted_sum = 0.0
        char_total = 0
        for i, (strip, result) in enumerate(items):
            piece = _clean_strip_text(result.get("full_text") or "")
            if i > 0 and items[i - 1][0].overlaps_next:
                piece = _dedup_overlap_head(merged_text, piece)
            piece_chars = len(piece)
            try:
                c = float(result.get("confidence") or 0)
            except (TypeError, ValueError):
                c = 0.0
            if c > 0 and piece_chars > 0:
                weighted_sum += c * piece_chars
                char_total += piece_chars
            merged_text = (merged_text + "\n" + piece).strip("\n") if merged_text else piece
        page_conf = (weighted_sum / char_total) if char_total else 0.0
        final_pages.append({
            "page": page_idx + 1,
            "text": merged_text,
            "confidence": page_conf,
        })
        grand_weighted_sum += weighted_sum
        grand_total_chars += char_total

    full_text = "\n".join(f"--- 第 {p['page']} 頁 ---\n{p['text']}" for p in final_pages)
    total_chars = sum(len(p["text"]) for p in final_pages)
    avg_conf = (grand_weighted_sum / grand_total_chars) if grand_total_chars else 0.0
    return {
        "status": "done",
        "total_pages": len(final_pages),
        "total_chars": total_chars,
        "confidence": avg_conf,
        "full_text": full_text,
        "pages": final_pages,
    }


def _scale_strip(img: Image.Image, scale: float) -> Image.Image:
    """Upscale (or pass-through) a strip image with LANCZOS interpolation.

    If the input was already binary (mode '1' or L-mode with only 0/255), the
    upscaled output is re-thresholded back to pure black/white so the final
    pack_to_pdf still picks the CCITT G4 path.
    """
    if scale == 1.0 or scale <= 0:
        return img
    new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    was_binary = (img.mode == "1") or _is_binary(img)
    resized = img.resize(new_size, Image.Resampling.LANCZOS)
    if was_binary:
        resized = resized.convert("L").point(lambda v: 255 if v >= 128 else 0, mode="L")
    return resized


def ocr_with_strips(pdf_path: Path, dpi: int, params: PreprocessParams | None,
                    n_strips: int = 3, overlap_px: int = 80,
                    white_threshold: int = 250,
                    search_ratio: float = 0.1,
                    strip_scale: float = 1.0) -> dict:
    """High-level: render → preprocess → split each page → (optional) upscale
    each strip → parallel OCR → merge."""
    images = render_hidpi(pdf_path, dpi)
    if params is not None:
        images = preprocess_images(images, params)
    all_strips: list[StripInfo] = []
    for page_idx, img in enumerate(images):
        page_strips = split_into_strips(img, n_strips=n_strips,
                                        search_ratio=search_ratio,
                                        overlap_px=overlap_px,
                                        white_threshold=white_threshold)
        for s in page_strips:
            s.page_idx = page_idx
            if strip_scale and strip_scale != 1.0:
                s.image = _scale_strip(s.image, strip_scale)
        all_strips.extend(page_strips)
    # Send strips at the *effective* DPI so PDF page-box size scales with image
    effective_dpi = int(dpi * (strip_scale if strip_scale else 1.0))
    results = ocr_strips_parallel(all_strips, effective_dpi)
    return merge_strip_results(all_strips, results)
