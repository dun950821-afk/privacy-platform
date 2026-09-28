"""AppShark HTML 报告的结构化解析。

fixture 是从证据库里取的真实报告（task 1178 的 `102-Camera_APICall.html`），
不是手写的——引擎报告的结构会随版本变，手写的例子只会验证我自己的假设。
"""
from pathlib import Path

import pytest

from app.services.appshark_report import (
    is_safe_report_name, parse_report, report_name_from_url)

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "report" / "real_report.html"


@pytest.fixture(scope="module")
def parsed():
    return parse_report(FIXTURE.read_text(encoding="utf-8", errors="replace"))


def test_extracts_report_and_rule_fields(parsed):
    """报告里的应用信息与规则元信息都要能取到，且两类分开。"""
    assert parsed["fields"]["PackageName"] == "cn.com.njcb.android.mobilehome.test"
    assert parsed["fields"]["VersionName"] == "3.4.24"
    assert parsed["rule"]["name"] == "Camera_APICall"
    assert parsed["rule"]["detail"] == "调用摄像头"
    # 规则键不该混在应用信息里
    assert "name" not in parsed["fields"]
    assert "complianceCategory" not in parsed["fields"]


def test_extracts_code_with_line_numbers(parsed):
    """代码块是这份产物最有价值的部分：带行号的方法体。"""
    assert parsed["code_blocks"], "应解析出代码块"
    block = parsed["code_blocks"][0]
    assert block["method"].startswith("<com.megvii.livenesslib.util.ICamera")
    lines = {item["line"]: item["text"] for item in block["lines"]}
    assert lines[1] == "r0 := @this: com.megvii.livenesslib.util.ICamera"
    assert any("android.hardware.Camera" in text for text in lines.values()), \
        "应包含真实的 API 调用语句"


def test_code_is_text_not_html(parsed):
    """解析结果里不得残留 HTML 标签——它会被前端当文本渲染。"""
    for block in parsed["code_blocks"]:
        for item in block["lines"]:
            assert "<script" not in item["text"].lower()
            assert "<style" not in item["text"].lower()
    # 类名里的尖括号是 Jimple 语法，不是标签，必须保留
    assert parsed["code_blocks"][0]["method"].startswith("<")


def test_style_and_script_content_is_dropped():
    """引擎报告顶部有一大段 CSS，混进正文会让展示一塌糊涂。"""
    parsed = parse_report(FIXTURE.read_text(encoding="utf-8", errors="replace"))
    joined = " ".join(item["text"] for block in parsed["code_blocks"] for item in block["lines"])
    assert "background-color" not in joined
    assert "hljs.initHighlightingOnLoad" not in joined


def test_marker_is_captured_when_present():
    """污点路径上的行带 [Source]/[Sink] 标记，要在展示上区分出来。"""
    html_with_marker = (
        "<html><body>vulnerability detail<br>Name: x<br>"
        "vulnerability postition:<br>&lt;com.a.B: void c()&gt;{<br>"
        "1: r0 := @this: com.a.B<br>"
        "2:->[Source] $r1 = virtualinvoke $r0.&lt;android.x: java.lang.String y()&gt;()<br>"
        "3:->[Sink] $r2 = staticinvoke &lt;android.util.Log: int d()&gt;($r1)<br>"
        "}</body></html>")
    blocks = parse_report(html_with_marker)["code_blocks"]
    markers = {item["line"]: item["marker"] for item in blocks[0]["lines"]}
    assert markers[2] == "Source"
    assert markers[3] == "Sink"
    assert markers[1] is None


def test_unparsable_html_degrades_to_empty():
    """结构对不上时返回空结构，不抛错——引擎换版本不能让接口 500。"""
    assert parse_report("<html><body>nonsense</body></html>")["code_blocks"] == []
    assert parse_report("")["fields"] == {}


@pytest.mark.parametrize("name,ok", [
    ("117-unZipSlip.html", True),
    ("102-Camera_APICall.html", True),
    ("../../etc/passwd", False),
    ("a/b.html", False),
    ("..", False),
    (".hidden", False),
    ("", False),
])
def test_report_name_must_be_a_plain_filename(name, ok):
    """文件名会被拼进证据目录路径，必须挡住目录穿越与隐藏文件。"""
    assert is_safe_report_name(name) is ok


def test_report_name_from_url_uses_basename():
    assert report_name_from_url("/tmp/appshark_out_553/vulnerability/117-unZipSlip.html") \
        == "117-unZipSlip.html"
    assert report_name_from_url(None) is None
    assert report_name_from_url("") is None
    # MobSF 的 payload.url 是对象而不是字符串，不能因此崩
    assert report_name_from_url({"path": "x", "urls": []}) is None


# ---------- 第二种版式（数据流报告）----------
# 引擎有两种报告版式，都来自真实产物：
#   APIMode：`vulnerability postition:` + `<方法>{ ... }`
#   数据流：`code detail:` + 不带花括号的方法头 + `LABELn:` 跳转标签
FIXTURE_FLOW = Path(__file__).parent / "fixtures" / "appshark" / "report" / "real_report_dataflow.html"


@pytest.fixture(scope="module")
def flow_parsed():
    return parse_report(FIXTURE_FLOW.read_text(encoding="utf-8", errors="replace"))


def test_dataflow_layout_is_parsed(flow_parsed):
    """数据流版式也要解析出代码。

    注意这份真实报告的 `code detail:` 段**不含方法头**——方法名在 `call stack:` 段
    （这份报告里是空的），而观察的 payload 已经带了 `caller`/`entry_method`。
    所以 `method` 允许为 None：展示时用 payload 里的方法名，不必再从报告里抠一遍。
    """
    assert flow_parsed["code_blocks"], "数据流报告应解析出代码块"
    numbered = [i for b in flow_parsed["code_blocks"] for i in b["lines"] if i["line"]]
    assert len(numbered) > 20, "应解析出较多带行号的语句，实际 %d" % len(numbered)
    for block in flow_parsed["code_blocks"]:
        if block["method"]:
            assert block["method"].startswith("<")


def test_dataflow_layout_keeps_source_marker(flow_parsed):
    """数据流报告里 `N:->[Source] ...` 的标记要保住——那是污点源。"""
    markers = {i["marker"] for b in flow_parsed["code_blocks"] for i in b["lines"]}
    assert "Source" in markers


def test_jump_labels_are_kept_but_not_numbered(flow_parsed):
    """`LABELn:` 不是语句，却决定 `goto LABELn` 读不读得懂：保留，但不占行号。"""
    labels = [i for b in flow_parsed["code_blocks"] for i in b["lines"]
              if i["line"] is None and i["text"].startswith("LABEL")]
    assert labels, "应保留跳转标签"
    assert all(i["marker"] is None for i in labels)


def test_taint_value_lines_are_not_mistaken_for_method_headers(flow_parsed):
    """污点值行形如 `<com.a.B: void c()>->$r5`，不是方法头。"""
    for block in flow_parsed["code_blocks"]:
        if block["method"]:
            assert not block["method"].endswith("->$"), block["method"]


def test_candidate_paths_cover_file_and_directory_evidence(tmp_path):
    """证据记录的是引擎产出的**文件**，但报告在它旁边的 vulnerability/ 目录里。

    线上正是这么错的：只按「证据路径是目录」找，结果一份都找不到。
    """
    from app.services.appshark_report import candidate_paths

    engine_dir = tmp_path / "task_1178" / "appshark"
    (engine_dir / "vulnerability").mkdir(parents=True)
    report = engine_dir / "vulnerability" / "988-DeviceId_FileWrite.html"
    report.write_text("<html></html>")
    (engine_dir / "results.json").write_text("{}")

    # 证据行指向文件
    from_file = candidate_paths(str(engine_dir / "results.json"), report.name)
    assert report in from_file
    # 也兼容指向目录的旧记录
    from_dir = candidate_paths(str(engine_dir), report.name)
    assert report in from_dir
    # 空路径不炸
    assert candidate_paths(None, report.name) == []
