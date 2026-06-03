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


def test_detect_file_born_digital():
    info = H.detect_file(r"E:\PJ_OCR\test\3.資產負債表測試-此為可複製文字之PDF.pdf")
    assert info["is_born_digital"] is True
    assert info["n_pages"] == 1
    assert info["text_chars"] >= 50


def test_detect_file_image_pdf():
    info = H.detect_file(r"E:\PJ_OCR\test\1.資產負債表測試(類型圖檔需OCR).pdf")
    assert info["is_born_digital"] is False
    assert info["text_chars"] == 0


def test_app_loads_with_two_step_nav():
    import warnings
    warnings.filterwarnings("ignore")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(r"E:\OCR-Work-platform\ocr_app_pro.py", default_timeout=60)
    at.run(timeout=60)
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("進階版" in t for t in titles)
    keys = {b.key for b in at.button}
    assert "nav1" in keys and "nav2" in keys


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
    # 完成辨識後應自動跳轉到步驟 2
    assert at.session_state["step"] == 2


def test_step2_shows_editable_text_and_download():
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
    at.session_state["step"] = 2
    at.run(timeout=120)
    assert not at.exception
    edit = [t for t in at.text_area if t.key == "edit_1"]
    assert edit and edit[0].value == "原始文字"
    edit[0].set_value("修改後文字").run(timeout=120)
    assert at.session_state["edited"][1] == "修改後文字"


def test_load_env_file_sets_unset_vars(tmp_path, monkeypatch):
    monkeypatch.delenv("MY_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("MY_TEST_KEY=hello\n# a comment\nNOEQUALS\n", encoding="utf-8")
    loaded = H.load_env_file(str(env))
    assert loaded.get("MY_TEST_KEY") == "hello"
    assert os.environ["MY_TEST_KEY"] == "hello"
    assert "NOEQUALS" not in loaded


def test_load_env_file_does_not_override_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_TEST_KEY2", "real")
    env = tmp_path / ".env"
    env.write_text("MY_TEST_KEY2=fromfile\n", encoding="utf-8")
    H.load_env_file(str(env))
    assert os.environ["MY_TEST_KEY2"] == "real"


def test_load_env_file_missing_returns_empty(tmp_path):
    assert H.load_env_file(str(tmp_path / "nope.env")) == {}
