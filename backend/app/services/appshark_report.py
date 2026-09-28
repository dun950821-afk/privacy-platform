"""AppShark 逐条命中的 HTML 报告：定位与结构化解析。

AppShark 为每条命中生成一份 HTML，里面有**带行号的 Jimple 语句**与 `[Source]`/`[Sink]`
标记——这是它相比其他引擎最有价值的产物（平台此前只是一张扁平观察表，这 1200 多份
报告躺在证据库里没人用过）。

**只提取文本，不把 HTML 交给前端渲染**：报告内容来自被检 APK（类名、方法名、字符串），
是不可信输入。直接把引擎生成的 HTML 送进浏览器，等于把 XSS 面开给样本——样本可以构造
类名带上脚本。所以这里解析成结构化数据，由前端用自家组件渲染。
"""
import html
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Evidence

# 报告里带行号的语句：`8:->[Source] $r5 = virtualinvoke ...` / `3:  $r1 = staticinvoke ...`
CODE_LINE_RE = re.compile(r"^(\d+):(?:->?\[([A-Za-z0-9_]+)\])?\s*(.*)$")
# 方法头。引擎有两种版式：APIMode 报告写成 `<com.a.B: void c(int)>{`，
# 数据流报告写成不带花括号的 `<com.a.B: void c(int)>`。两者都要认。
# 注意别把污点值行（`<com.a.B: ...>->$r5`，以 `>` 结尾但后面还有内容）误判成方法头。
METHOD_HEAD_RE = re.compile(r"^<[^>]+>\{?$")
# 方法内的跳转标签（`LABEL2:`），保留下来读者才看得懂 `goto LABEL2`
LABEL_RE = re.compile(r"^LABEL[0-9]+:$")
_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):\s*(.*)$")
_STYLE_RE = re.compile(r"(?is)<(style|script)\b.*?</\1>")
_TAG_RE = re.compile(r"<[^>]+>")

# 代码段的起始标记。引擎有两种版式（都已见于真实产物）：
#   APIMode 报告：`vulnerability postition:`（引擎自身的拼写，勿"修正"）
#   数据流报告：  `code detail:`
CODE_SECTION_MARKERS = ("vulnerability postition", "code detail")
DETAIL_SECTION_MARKER = "vulnerability detail"

# 这些键属于规则自身的元信息（小写开头），其余是报告/应用信息
RULE_KEYS = ("name", "category", "detail", "complianceCategory",
             "complianceCategoryDetail", "scanTime", "engineVersion")


def to_text_lines(raw_html: str) -> list[str]:
    """HTML → 纯文本行。先摘掉 style/script，再去标签，最后反转义。"""
    cleaned = _STYLE_RE.sub("\n", raw_html)
    text = html.unescape(_TAG_RE.sub("\n", cleaned))
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_report(raw_html: str) -> dict:
    """解析成 `{fields, rule, code_blocks}`。

    `code_blocks` 是前端展示代码用的：每个方法一块，每行带行号与污点标记
    （Source/Sink/或数据流步序号），标记为空表示该行只是上下文。
    """
    lines = to_text_lines(raw_html)
    try:
        start = lines.index(DETAIL_SECTION_MARKER) + 1
    except ValueError:
        return {"fields": {}, "rule": {}, "code_blocks": []}

    # 报告分两段：字段区（应用信息 + 规则元信息）与代码区（各方法的带行号语句）。
    # 代码区以 "vulnerability postition" 起头（引擎自身的拼写），到文件尾。
    code_start = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith(CODE_SECTION_MARKERS):
            code_start = i + 1
            break

    fields: dict[str, str] = {}
    for line in lines[start:code_start]:
        match = _FIELD_RE.match(line)
        if match:
            fields[match.group(1)] = match.group(2)

    code_blocks: list[dict] = []
    current: dict | None = None
    for line in lines[code_start:]:
        if METHOD_HEAD_RE.match(line):
            current = {"method": line.rstrip("{"), "lines": []}
            code_blocks.append(current)
            continue
        match = CODE_LINE_RE.match(line)
        if match:
            if current is None:      # 报告没写方法头时也不丢代码
                current = {"method": None, "lines": []}
                code_blocks.append(current)
            current["lines"].append({"line": int(match.group(1)),
                                     "marker": match.group(2),
                                     "text": match.group(3)})
            continue
        if current is None:
            continue
        if line == "}":
            current = None
            continue
        if LABEL_RE.match(line):
            # 跳转标签：不是语句，但 `goto LABEL2` 需要它才读得懂
            current["lines"].append({"line": None, "marker": None, "text": line})

    rule = {key: fields.pop(key) for key in list(fields) if key in RULE_KEYS}
    return {"fields": fields, "rule": rule, "code_blocks": code_blocks}


def is_safe_report_name(name: str) -> bool:
    """报告文件名必须是纯文件名——它最终会拼进证据目录路径。"""
    return bool(name) and "/" not in name and "\\" not in name \
        and not name.startswith(".") and ".." not in name


def candidate_paths(artifact_path: str | None, report_name: str) -> list[Path]:
    """从一条证据记录推出报告可能在哪。

    证据行记录的是引擎产出的**文件**（`results.json` / `stdout.log`），不是目录，
    所以既要试它本身，也要试它所在目录；逐条报告在 `vulnerability/` 子目录下
    （也有引擎版本直接摊在目录里），两个位置都试。
    """
    if not artifact_path:
        return []
    entry = Path(artifact_path)
    bases = [entry.parent, entry]
    candidates = []
    for base in bases:
        candidates.append(base / "vulnerability" / report_name)
        candidates.append(base / report_name)
    return candidates


def find_report_file(db: Session, task_id: int, report_name: str) -> Path | None:
    """在任务的引擎证据里找到这份报告。

    以 payload.url 的文件名去配——引擎产物落盘时用的是自己的工作目录
    （`/tmp/appshark_out_<task>/...`），存下来的却是证据路径，两者只有文件名对得上。
    """
    if not is_safe_report_name(report_name):
        return None
    rows = db.query(Evidence).filter(
        Evidence.task_id == task_id, Evidence.evidence_type == "engine_output").all()
    for row in rows:
        for candidate in candidate_paths(row.artifact_path, report_name):
            if candidate.is_file():
                return candidate
    return None


def report_name_from_url(url) -> str | None:
    """从观察的 payload.url 取出报告文件名。"""
    if not isinstance(url, str) or not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None
