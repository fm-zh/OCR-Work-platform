import io
import openpyxl
from app import excel


def test_parse_structured_valid():
    raw = '{"columns":["項目","金額"],"rows":[["現金","100"]]}'
    out = excel._parse_structured(raw, "ignored")
    assert out["columns"] == ["項目", "金額"]
    assert out["rows"] == [["現金", "100"]]


def test_parse_structured_fallback_on_bad_json():
    out = excel._parse_structured("not json", "行一\n行二")
    assert out["columns"] == []
    assert out["rows"] == [["行一"], ["行二"]]


def test_parse_structured_coerces_non_strings():
    raw = '{"columns":["c"],"rows":[[1, null, "x"]]}'
    out = excel._parse_structured(raw, "")
    assert out["rows"] == [["1", "", "x"]]


def test_build_workbook_with_columns():
    data = {1: {"columns": ["項目", "金額"], "rows": [["現金", "100"], ["存貨", "200"]]}}
    wb = openpyxl.load_workbook(io.BytesIO(excel.build_workbook(data)))
    assert wb.sheetnames == ["第1頁"]
    ws = wb["第1頁"]
    assert [c.value for c in ws[1]] == ["項目", "金額"]
    assert ws.cell(row=2, column=1).value == "現金"


def test_build_workbook_multi_page_no_columns():
    data = {1: {"columns": [], "rows": [["a"]]}, 2: {"columns": [], "rows": [["b"]]}}
    wb = openpyxl.load_workbook(io.BytesIO(excel.build_workbook(data)))
    assert wb.sheetnames == ["第1頁", "第2頁"]
