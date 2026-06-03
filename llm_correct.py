"""LLM bridges to Claude CLI for two use-cases:

  1. correct_via_claude_cli(text)        — post-correct a PaddleOCR transcript
  2. ocr_via_claude_vision(pil_image)     — let Claude read the page image itself

Both spawn `claude -p` (one-shot, non-interactive) and read stdout. We launch
via shell=True with the Windows shim `claude.CMD` (or `claude` on POSIX) — the
direct .exe path can fail with Windows `CreateProcess` due to characters in the
npm install path.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

# Fallback if `claude` is not on PATH
_CLAUDE_FALLBACK_WIN_CMD = Path(
    r"C:\Users\AI_SERVER\AppData\Roaming\npm\claude.CMD"
)


def _find_claude_invocation() -> str:
    """Return a path suitable for subprocess invocation.

    Prefer the .CMD shim on Windows (works reliably with cmd.exe / shell=True);
    fall back to .exe direct path (works with shell=False).
    """
    cmd = shutil.which("claude.cmd")
    if cmd:
        return cmd
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    if _CLAUDE_FALLBACK_WIN_CMD.is_file():
        return str(_CLAUDE_FALLBACK_WIN_CMD)
    raise FileNotFoundError(
        "找不到 claude CLI。請確認 Claude Code 已安裝："
        "npm install -g @anthropic-ai/claude-code"
    )


def _run_claude(prompt: str, timeout: int) -> str:
    """Common subprocess wrapper. Raises RuntimeError on non-zero exit."""
    bin_ = _find_claude_invocation()
    is_cmd = bin_.lower().endswith(".cmd") or bin_.lower().endswith(".bat")
    if is_cmd:
        # .CMD files require cmd.exe wrapper; shell=True with quoted path
        # (unquoted unexpectedly invokes the nested .exe wrong on some installs)
        cmd = f'"{bin_}" -p --permission-mode bypassPermissions'
        result = subprocess.run(
            cmd, shell=True,
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
    else:
        # Direct .exe call — use list args, no shell, no quoting needed
        result = subprocess.run(
            [bin_, "-p", "--permission-mode", "bypassPermissions"],
            input=prompt,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False,
        )
    if result.returncode != 0:
        msg = (result.stderr or result.stdout or "").strip()[:500]
        raise RuntimeError(f"claude CLI 退出碼 {result.returncode}：{msg}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Case 1: post-correct an existing OCR transcript
# ---------------------------------------------------------------------------

CORRECT_PROMPT = """這是一份台灣的商業/財務文件（銀行電文、通知書、資產負債表、損益表、發票、報表等）的 OCR 辨識結果，可能包含以下類型的錯誤：

1. 簡體字應為台灣繁體（如：顺→順、号→號、体→體、宽→寬、广→廣、页→頁、负→負、债→債）
2. 視覺相似字混淆（如：0↔O、1↔l/I、5↔S、ze↔ge、0f→of、rn↔m、頁↔真、次↔安、设↔役、备↔各）

【最高優先・合計／總計 絕對保留，嚴禁互換】
- 「合計」與「總計」是兩個不同的詞。OCR 讀到「總計」就**必須**輸出「總計」、讀到「合計」就輸出「合計」，**任何情況都不准互換**。
- 台灣資產負債表小計／合計列大多使用「總計」：流動資產總計、非流動資產總計、資產總計、流動負債總計、非流動負債總計、負債總計、權益總計、負債及權益總計。請忠實保留 OCR 讀到的「總計」，不要改成「合計」。
- 同理「資產總計」「負債及權益總計」等列若 OCR 有輸出該列名稱，請完整保留，不要刪除標籤只留數字。
3. SWIFT 代碼、帳號、金額可能有字元錯位
4. 部分字因模糊或掃描雜訊缺少筆畫

**附註（明細）號碼還原**：
- 財務報表的附註號碼是由上而下大致遞增的（附註四、附註六、附註七…附註十一、附註十二）。
- 若某列的附註號碼被掃描截斷（OCR 只看到「附十」「附註十」這種殘缺、末尾數字掉了），請依「上下相鄰列的附註號碼」推回最合理的完整號碼：
  - 例：某列 OCR 為「其他應付款（附十」，其下方一兩列出現「（附註十二）」，則該截斷列極可能是「（附註十一）」。
  - 只在號碼明顯被截斷時推補，且必須與上下文遞增順序一致；若無相鄰號碼可參考則保留原樣。

**台灣商業文件常見格式詞，OCR 容易誤判，請優先還原成這些標準用語**：
- 頁次（OCR 可能誤讀為「真安」「页次」「页實」「夏次」）
- 製表 / 製表人 / 製作人
- 日期 / 月份 / 年度
- 項目 / 金額 / 摘要 / 備註
- 資產 / 負債 / 權益
- 流動資產 / 流動負債 / 非流動資產
- 庫存現金 / 零用金 / 週轉金（零用金/週轉金 是配對術語）
- 銀行存款 / 應付票據 / 應收帳款 / 預收款項
- 資本（或股本） / 保留盈餘（或累積虧損）
- 本期損益 / 累積盈虧 / 其他權益
- 資產總額 / 負債總額 / 權益總額

**印章/壓蓋遮擋的字元還原規則**：
- 台灣財報常在標題附近蓋紅色公司印章（篆書方章），可能完全遮蓋公司名中間的一兩個字
- 處理原則：若 OCR 標題行出現「XX[斷裂或亂字]股份有限公司」且該頁是綜合損益表 / 資產負債表 / 現金流量表
  - 例如：「可力生」+ 缺字 + 「股份有限公司」→「**可力生醫股份有限公司**」（台灣已知生技公司）
  - 例如：「可力寶」+ 缺字 + 「股份有限公司」→「**可力寶實業股份有限公司**」
  - 通則：補回中間被遮擋的字（醫、實、生技、科技、資訊等）
- 若公司名出現在多頁同份報表，請使用同樣的公司名
- 若無把握，**保留 OCR 原樣**，不要瞎猜

**公司名/商號常見字混淆（極重要）**：
- 「舖」（店舖、商號常用）↔ 「辅/輔」：視覺幾乎相同
- 商業文件中「XX小舖」「XX舖」這類字樣**永遠是「舖」**（店舖 / 商號 / 鋪面），絕對不是「輔」（輔助）
- 規則：OCR 看到「[X][X]小[辅/輔]有限公司」**一律修成「[X][X]小舖有限公司」**
- 範例：「新新小辅」→「新新小舖」、「三民小辅」→「三民小舖」、「便利小辅」→「便利小舖」
- 簡體「辅」→繁體**優先選「舖」**（除非上下文明確是輔助、輔導、輔具等）

**負值還原規則（兩種台灣慣例，請依 OCR 原文格式區分）**：

格式 A — 「-」負號（一般財務報表用、紅字標記常用）：
- 若 OCR **已輸出**一個正數金額（如「3,200」），且該行下方/旁邊的百分比是負（如「-0.18%」），請在金額前加「-」（變成「-3,200」）
- 業主往來、其他權益、累計虧損 等項目常為負

格式 B — 「(X)」括弧（會計師查核報告、傳統表單用）：
- 若 OCR **已輸出**「數字)」但前面沒「(」（OCR 看到「(」前的大空白把它當雜訊丟掉），請補回「(」變成「(數字)」
- 範例：「588)」→「(588)」、「2,729)」→「(2,729)」、「$ 588)」→「($588)」或「(588)」
- 同樣只補一個括弧，**不要把 OCR 原本是「-X」格式硬改成「(X)」**

**選擇規則（極重要）**：
- 如果 OCR 原文有 ")" 字元 → 保留括弧格式、補上「(」
- 如果 OCR 原文沒有任何括弧、只是缺負號 → 用「-」前綴
- **絕對不要把「-3,200」硬改成「(3,200)」**，反之亦然
- 若 OCR 已給「-X」就維持「-X」、已給「X)」就補成「(X)」

⛔ **絕對禁止**：
- **不要編造 OCR 原文裡完全沒有的數字** —— 如果某一列的金額完全缺失（連數字都沒有），請保持空行或留空，不要憑空填入
- 不要根據百分比反推應有金額
- 只能修正 OCR 確實有輸出的數字（加負號、補括弧、修正錯字、調整空格）
- **絕對不要使用 markdown 語法**（`**粗體**`、`# 標題`、程式區塊等）—— 純文字輸出
- **不要把 OCR 原文的詞改成同義詞**（不要把「總計」改成「合計」、「附註十一」改成「附註十二」）；保留 OCR 原樣
- 不要在每個區塊前加標題或粗體

**標題補回（強制）**：
台灣財報每頁開頭固定有：公司名 + 報表名 + 日期 + 單位
若任一頁開頭缺這幾行（例如 page 1 OCR 開頭直接是「單位：新台幣千元」、沒看到公司名跟報表名），請**強制**在該頁第 1-3 行補回：
- 第 1 行：公司名（從其他頁推得）
- 第 2 行：該頁的報表名（依內容判斷：有「資產」「負債」「權益」→ 資產負債表；有「營業收入」「淨損」→ 綜合損益表；有「現金流量」「投資活動」→ 現金流量表）
- 第 3 行：日期（從其他頁推得，例：「民國113年12月31日」、「民國113年10月22日（設立日）至12月31日」）

**判別範例**：
- OCR page 1 開頭：「單位：新台幣千元 / 113年12月31日 / 金 / % / 流動資產 / ...」→ 缺前 3 行
  - 補：「可力生醫股份有限公司 / 資產負債表 / 民國113年12月31日 / 單位：新台幣千元 / ...」
- OCR page 2 開頭：「可力生 / 綜合損益表 / 民國113年10月22日（設立日）至12月31日 / ...」→ 公司名被印章遮中間
  - 補：把「可力生」修成「可力生醫股份有限公司」

**頁尾簽署欄還原（強制）**：
台灣財務報表（資產負債表 / 綜合損益表 / 現金流量表）頁尾固定有三個並列簽署欄位，依序固定為：
「負責人」「經理人」「主辦會計」（後面常各跟一個冒號與紅色印章，印章會使 OCR 殘缺）。
- 若頁尾出現其中任一或殘缺片段（如只 OCR 到「理人」「責人」「會計」「钟食计」「主辦」），請**強制補齊為三個完整詞**，各自獨立成行或同一行以空白分隔：
  負責人　經理人　主辦會計
- 三者順序固定不可調換；不要多補、也不要漏掉「經理人」。

**權益區缺漏項目名稱還原**：
- 權益（股東權益）區若在「股本 / 普通股股本」之後、「權益總計 / 權益合計」之前，OCR 出現一個括號負值（如「(588)」「(1,234)」）卻**沒有對應的項目名稱**，這通常是「待彌補虧損」（累積虧損）被掃描漏字，請補上項目名稱「待彌補虧損」。
- 若該值為正且缺名稱，補「保留盈餘」；不確定則保留原樣。

請以台灣繁體中文修正並輸出全文，遵守：
- 保留原始版面（換行、縮排、特殊符號、雙星號、空格對齊）
- 不確定的位置維持原樣，不要刪除或補造內容
- **直接輸出修正後的全文，不要加任何說明、標題、引言、分隔符或結語**
- 不要用 markdown 程式區塊包起來

OCR 原文：
=====
{text}
====="""


def correct_via_claude_cli(ocr_text: str, timeout: int = 180) -> str:
    """Post-correct an OCR transcript via Claude. Returns corrected text."""
    if not ocr_text or not ocr_text.strip():
        return ocr_text
    return _run_claude(CORRECT_PROMPT.format(text=ocr_text), timeout=timeout)


# ---------------------------------------------------------------------------
# Case 2: vision OCR — send image directly, skip PaddleOCR
# ---------------------------------------------------------------------------

VISION_PROMPT = """請閱讀以下圖片並完整逐字轉錄成文字：
{image_path}

要求：
- 使用台灣繁體中文
- 保留原始版面（換行、縮排、特殊符號、星號、空格對齊）
- 不確定的字維持原樣，不要刪除或補造內容
- 直接輸出文字，不要加任何說明、標題、引言或 markdown 程式區塊
"""


def ocr_via_claude_vision(pil_image: Image.Image, timeout: int = 240) -> str:
    """Run Claude vision OCR on a single PIL image. Returns the transcription."""
    if pil_image is None:
        raise ValueError("pil_image is required")
    # Persist the image so Claude's Read tool can pick it up
    fd, tmp_str = tempfile.mkstemp(prefix="claude_vision_", suffix=".png")
    os.close(fd)
    tmp = Path(tmp_str)
    try:
        pil_image.convert("RGB").save(tmp, "PNG")
        return _run_claude(
            VISION_PROMPT.format(image_path=str(tmp)),
            timeout=timeout,
        )
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Case 3: text-only post-correction via DeepSeek (OpenAI-compatible REST)
# ---------------------------------------------------------------------------

DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"


MERGE_PREAMBLE = """以下提供「同一頁」用兩種不同解析度做 OCR 的兩份結果（內容大致相同，但各自有不同的漏字或誤判）。
請先在心中把兩份對照、互補，取兩者中**較完整且較合理**的內容，合併成一份最正確的版本，再依後續規則修正。
合併原則：
- 某份漏掉的字／數字，若另一份有，請採用有的那份。
- 數字（金額、百分比、附註號碼）若兩份不同，採用較完整、位數較合理、與上下文加總一致的那份。
- 標題、項目名稱、附註號碼以較清晰的一份為準。
- 不要把兩份內容重複輸出，最後只輸出**一份**合併修正後的全文。

===== 解析度 A 的 OCR =====
{text_a}
===== 解析度 B 的 OCR =====
{text_b}
=====

接下來是修正規則："""


def correct_via_deepseek_merge(text_a: str, text_b: str, api_key: str,
                               model: str = "deepseek-chat",
                               timeout: int = 240) -> str:
    """Merge two OCR transcripts of the SAME page (different DPIs) and correct.

    Feeds both transcripts plus the full CORRECT_PROMPT rules to DeepSeek so it
    can pick the more complete reading per line before applying corrections.
    """
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a and not b:
        return ""
    if not a or not b:
        return correct_via_deepseek(a or b, api_key, model, timeout)
    merged_prompt = (
        MERGE_PREAMBLE.format(text_a=a, text_b=b)
        + "\n" + CORRECT_PROMPT.format(text="（見上方兩份 OCR）")
    )
    return _deepseek_chat(merged_prompt, api_key, model, timeout)


def _deepseek_chat(prompt: str, api_key: str, model: str, timeout: int) -> str:
    """Low-level DeepSeek chat call returning stripped content."""
    if not api_key or not api_key.strip():
        raise ValueError("DeepSeek API key is required")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{DEEPSEEK_API_BASE}/chat/completions",
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DeepSeek API HTTP {e.code}: {err_body[:400]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"DeepSeek API 連線錯誤: {e}") from e
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"DeepSeek API 回應格式異常: {data!r}") from e
    return (text or "").strip()


def correct_via_deepseek(ocr_text: str, api_key: str,
                          model: str = "deepseek-chat",
                          timeout: int = 180) -> str:
    """Post-correct OCR text using DeepSeek's chat API.

    `model`: 'deepseek-chat' (V3.x, fast) or 'deepseek-reasoner' (R1, slower
    but stronger on disambiguation).
    """
    if not ocr_text or not ocr_text.strip():
        return ocr_text
    return _deepseek_chat(CORRECT_PROMPT.format(text=ocr_text), api_key, model, timeout)
