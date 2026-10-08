#!/usr/bin/env python3
"""任务详情页验收脚本（task 6 §5.1+§5.2 / task 7 §5.3+§5.4 / task 8 §5.1 侧滑面板+整改）。

重放方式（Playwright 只装在项目的 python venv 里，无 node 版）：

    /home/user/privacy-platform/.venv/bin/python \\
        frontend/scripts/verify-task-detail.py --task 810
    /home/user/privacy-platform/.venv/bin/python \\
        frontend/scripts/verify-task-detail.py --task 3107 --task 810 --task 1244

前置：前端 vite 在 --base 上跑着、后端 8000 可达（vite 会把 /api 代理到 8000）。

脚本自己登录拿 token（不依赖 /tmp 下的临时令牌文件），然后断言：

  正向路径  —— 主视图无 tab；结论条计数；卡片数与接口一致；按 severity 排序；
              构成说明只在 L2/L3 有值时出现（L4 不进、summary 为 null 不出现）；
              「证据 N 处」取自 observation_count；全程无 console error。
  代码证据  —— §5.3：按 observation 逐条列出 location 方法签名原文；「查看完整路径」
              打开 EngineReportViewer 且带逐字标注「以下为 IR 代码（smali 风格），非 Java 源码」；
              没有 payload.url 的观察按钮置灰。
  网络证据  —— §5.4：**在 App 背景面板里**（不再随卡片重复）：按 host 平铺且与接口同序；
              测试服务器残留高亮；逐字标注；available:false 显示「该任务没有端点数据」；
              confidence=low 用 .is-lead 且显示 note；attribution 为空不渲染归属。
  背景面板  —— task 8 §5.1：右上角按钮打开 480px 面板；六块齐全；「安全加固」五段
              按序展示，missing 段落写「本任务没有这段数据」；secrets（414 条）限高 +
              首屏只渲染前 N 条；端点与网络块在面板里只出现一次。
  整改操作  —— task 8 §二：卡片上能改 triage_status / assigned_to / due_date，
              刷新后值还在；后端 400 时前端给出可读错误。
  整改概览  —— task 8 §三：四态汇总与接口一致；复检记录两个方向分开显示
              （--inject-retest 时插两条临时记录，跑完即删）。
  失败路径  —— 拦掉 platform-findings 返回 500 后，必须出现可重试的失败态，
              且**不得**出现「本次未形成平台结论」；点「重试」后恢复。

退出码：全部通过 0，任一断言失败 1。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from playwright.async_api import TimeoutError as PWTimeout, async_playwright

# 卡片构成说明只列 L2 + L3（隐私维度）。L4 是安全缺陷，归 App 背景面板的「安全加固」块。
LEVEL_CN = {"L2": "敏感 API 调用", "L3": "数据流"}
CARD_LEVELS = ("L2", "L3")
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
FINDINGS_ROUTE = "**/platform-findings*"
RETEST_ROUTE = "**/retest-records*"

# 安全加固五段：顺序即展示顺序（与后端 tasks.py: SECURITY_SECTIONS 一致）
SECURITY_SECTIONS = [
    ("appsec", "应用安全评分"),
    ("manifest_analysis.manifest_findings", "清单问题"),
    ("secrets", "硬编码密钥"),
    ("certificate_analysis", "签名与证书"),
    ("sbom", "依赖清单"),
]
NO_SECTION = "本任务没有这段数据"

# 面板六块（data-block 顺序）
PANEL_BLOCKS = [
    ("basic", "App 基本信息"),
    ("security", "安全加固"),
    ("network", "端点与网络"),
    ("profile", "合规画像"),
    ("sdk", "SDK 组件"),
    ("permission", "权限"),
]
PANEL_WIDTH = 480
# 大列表首屏渲染上限（与 AppBackgroundPanel.RAW_LIMIT 一致）
RAW_LIMIT = 50

TRIAGE_LABEL = {"needs_review": "待审阅", "fixing": "整改中", "fixed": "已修复", "ignored": "已忽略"}
TRIAGE_ORDER = ["needs_review", "fixing", "fixed", "ignored"]


def expected_composition(finding: dict) -> str | None:
    """无 summary（或只有 L4）时返回 None —— 卡片上整行不渲染，不显示「0 条」。"""
    summary = finding.get("provider_level_summary") or {}
    parts = [f"{summary[k]} 条{LEVEL_CN[k]}" for k in CARD_LEVELS if summary.get(k)]
    return f"由 {' + '.join(parts)}构成" if parts else None


def severity_rank(finding: dict) -> int:
    return SEVERITY_RANK.get(str(finding.get("severity", "")).lower(), 9)


def sorted_findings(findings: list[dict]) -> list[dict]:
    """页面上的顺序：severity 升序（high 在前），同 severity 保持接口顺序。"""
    return sorted(findings, key=severity_rank)


def head_title(head: str) -> str:
    """卡片首行是 `[严重度] | 规则名 | [构成说明] | 证据 N 处 | [状态]`，规则名在第二段。"""
    parts = [s.strip() for s in head.split("|")]
    return parts[1] if len(parts) > 1 else ""


# 浏览器对任何非 2xx 资源都会自己补一条 "Failed to load resource"，它描述的正是
# 失败路径里被注入的那个 500，不是应用缺陷。失败路径放行这一条；pageerror 与
# 其它 console error 照旧算错 —— 缺 catch 时留下的 unhandled rejection 会以
# pageerror 形式出现，正是要拦住的东西。
BROWSER_RESOURCE_NOISE = "Failed to load resource"


def app_errors(entries: list[str]) -> list[str]:
    return [e for e in entries if BROWSER_RESOURCE_NOISE not in e]


def trim_resource_noise(console: list[str], mark: int) -> None:
    """只放行 `console[mark:]` 里的资源级噪音，保留这段窗口内其它 console 条目。

    正向路径的判定是严格的（`not console`）。但整改 400、复检 500 是**故意注入**的，
    浏览器必然补一条 "Failed to load resource"。宽容只收敛到注入点周围，
    而不是全局放宽——否则三个任务的正向路径从此不再拦任何资源级失败。
    """
    console[mark:] = [e for e in console[mark:] if BROWSER_RESOURCE_NOISE not in e]



class Checker:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")
        if not ok:
            self.failed.append(name)


async def fetch_findings(page, base: str, token: str, task_id: int) -> dict:
    return await fetch_json(page, base, token, f"/tasks/{task_id}/platform-findings")


async def fetch_json(page, base: str, token: str, path: str) -> dict:
    resp = await page.request.get(f"{base}/api/v1{path}",
                                  headers={"Authorization": f"Bearer {token}"})
    body = await resp.json()
    assert body.get("code") == 0, body
    return body["data"]


async def goto_task(page, base: str, token: str, task_id: int) -> None:
    await page.goto(f"{base}/login")
    await page.evaluate(
        """t => {
            localStorage.setItem('token', t);
            localStorage.setItem('privacy-user', JSON.stringify({token: t, refreshToken: ''}));
        }""",
        token,
    )
    await page.goto(f"{base}/tasks/{task_id}")


# ── 证据块（§5.3 + §5.4）期望值 ────────────────────────────────────────────────
IR_NOTICE = "以下为 IR 代码（smali 风格），非 Java 源码"
ENDPOINT_NOTICE = "端点与规则的精确关联暂未建立，以上为 App 全部端点"
NO_ENDPOINT = "该任务没有端点数据"
NO_LOCATION = "（该条观察无方法签名）"
OBS_PAGE = 20  # 与 CodeEvidenceBlock.PAGE 一致


def obs_location(obs: dict) -> str:
    return obs.get("location") or NO_LOCATION


def has_report(obs: dict) -> bool:
    payload = obs.get("payload")
    return bool(payload.get("url")) if isinstance(payload, dict) else False


def panel_of(page):
    """App 背景面板本体（用 .bg-block 与其它 drawer 区分）。"""
    return page.locator(".el-drawer").filter(has=page.locator(".bg-block"))


async def open_panel(page, ck: Checker) -> None:
    await page.locator(".task-head-actions button", has_text="App 背景").click()


# ════════════════════════════════════════════════════════════════════════════
async def verify_happy_path(page, base: str, token: str, task_id: int, ck: Checker,
                            console: list[str]) -> None:
    print(f"\n[正向路径] task {task_id}")
    data = await fetch_findings(page, base, token, task_id)
    findings = data.get("items") or []
    print(f"  接口：total={data.get('total')} items={len(findings)}")

    try:
        if findings:
            await page.wait_for_selector(".cards .el-collapse-item", timeout=15000)
        else:
            await page.wait_for_selector(".el-empty", timeout=15000)
    except PWTimeout:
        pass

    ck.check("主视图不再有 el-tabs", await page.locator(".el-tabs").count() == 0)

    cards = page.locator(".cards .el-collapse-item")
    ck.check("卡片数 == 接口条数", await cards.count() == len(findings),
             f"dom={await cards.count()} api={len(findings)}")

    if not findings:
        ck.check("无结论时不渲染结论条", await page.locator(".digest").count() == 0)
        ck.check("无结论时显示空态",
                 await page.locator(".el-empty", has_text="本次未形成平台结论").count() == 1)
        ck.check("无结论时不是失败态", await page.locator(".load-error").count() == 0)
    else:
        await verify_cards(page, findings, ck)
        first_id = sorted_findings(findings)[0]["id"]
        await verify_code_evidence(page, base, token, task_id, first_id, ck)
        await verify_remediation(page, base, token, task_id, first_id, ck, console)

    # 网络证据是任务级数据，现在只活在面板里
    ck.check("网络证据块不再出现在任何卡片里",
             await page.locator(".cards .net-evidence").count() == 0,
             f"dom={await page.locator('.cards .net-evidence').count()}")

    await verify_panel(page, base, token, task_id, ck)
    await verify_overview(page, base, token, task_id, ck, console)
    await page.keyboard.press("Escape")  # 关掉可能还开着的东西


async def verify_cards(page, findings: list[dict], ck: Checker) -> None:
    cards = page.locator(".cards .el-collapse-item")
    high = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")
    medium = sum(1 for f in findings if str(f.get("severity", "")).lower() == "medium")
    digest = (await page.locator(".digest").inner_text()).replace("\n", " ")
    ck.check("结论条显示 high/medium 计数",
             digest.split()[:4] == [str(high), "高危", str(medium), "中危"],
             f"dom={digest!r} api=high:{high} medium:{medium}")

    heads = await cards.locator(".card-head").all_inner_texts()
    heads = [" | ".join(h.split("\n")) for h in heads]

    want_order = [f["title"] for f in sorted_findings(findings)]
    got_order = [head_title(h) for h in heads]
    got_rank = [SEVERITY_RANK.get(h.split("|")[0].strip().replace("高危", "high").replace("中危", "medium"), 9)
                for h in heads]
    ck.check("按 severity 排序（high 在前、同档稳定）",
             got_order == want_order and got_rank == sorted(got_rank),
             f"ranks={got_rank}")

    comp_bad, ev_bad = [], []
    for f, head in zip(sorted_findings(findings), heads):
        want = expected_composition(f)
        if want and want not in head:
            comp_bad.append(f"id={f['id']} 期望 {want!r}")
        if not want:
            if "构成" in head or "0 条" in head:
                comp_bad.append(f"id={f['id']} 不该有构成说明：{head!r}")
        want_ev = f"证据 {f.get('observation_count') or 0} 处"
        if want_ev not in head:
            ev_bad.append(f"id={f['id']} 期望 {want_ev!r}")

    null_summary = sum(1 for f in findings if not (f.get("provider_level_summary") or {}).get("L2")
                       and not (f.get("provider_level_summary") or {}).get("L3"))
    print(f"  构成说明应为空的（无 L2/L3）：{null_summary} / {len(findings)} 条")
    ck.check("构成说明逐条正确（L4 不进、null 不出现）", not comp_bad, "; ".join(comp_bad))
    ck.check("证据条数逐条取自 observation_count", not ev_bad, "; ".join(ev_bad))

    await cards.locator(".el-collapse-item__header").first.click()
    await page.wait_for_timeout(800)
    ck.check("卡片可展开", await cards.locator(".card-body").first.is_visible())


async def verify_code_evidence(page, base: str, token: str, task_id: int, fid: int,
                               ck: Checker) -> None:
    """§5.3 代码证据块（卡片展开区）。网络证据已搬到面板，见 verify_panel。"""
    print(f"  [代码证据] finding {fid}")
    card = page.locator(".cards .el-collapse-item").first
    detail = await fetch_json(page, base, token, f"/tasks/{task_id}/platform-findings/{fid}")
    obs = detail.get("observations") or []
    try:
        await card.locator(".code-evidence .obs").first.wait_for(timeout=15000)
    except PWTimeout:
        pass

    rows = card.locator(".code-evidence .obs")
    ck.check("代码证据按 observation 逐条渲染",
             await rows.count() == min(len(obs), OBS_PAGE),
             f"dom={await rows.count()} api={len(obs)} 首屏={min(len(obs), OBS_PAGE)}")

    locs = [s.strip() for s in await rows.locator(".obs-loc").all_inner_texts()]
    want_locs = [obs_location(o) for o in obs[:OBS_PAGE]]
    ck.check("代码证据展示 location 方法签名原文", locs == want_locs,
             f"首条 dom={locs[:1]!r} api={want_locs[:1]!r}")
    null_n = sum(1 for o in obs if not o.get("location"))
    print(f"  观察 {len(obs)} 条，其中 location 为空 {null_n} 条")

    btns = rows.locator("button", has_text="查看完整路径")
    want_enabled = [has_report(o) for o in obs[:OBS_PAGE]]
    got_disabled = [await btns.nth(i).is_disabled() for i in range(await btns.count())]
    ck.check("无引擎报告的观察「查看完整路径」置灰（点了才会 404）",
             got_disabled == [not e for e in want_enabled],
             f"disabled={got_disabled}")

    if len(obs) > OBS_PAGE:
        more = card.locator(".code-evidence button", has_text="展开其余")
        ck.check("长列表提供「展开其余 N 条」", await more.count() == 1)
        if await more.count():
            await more.click()
            await page.wait_for_timeout(400)
            ck.check("展开其余后条数 == 接口条数", await rows.count() == len(obs),
                     f"dom={await rows.count()} api={len(obs)}")

    pick = next((i for i, o in enumerate(obs[:OBS_PAGE]) if has_report(o)), None)
    if pick is None:
        ck.check("存在可打开 IR 的观察", False, "首屏 20 条都没有 payload.url")
    else:
        await rows.nth(pick).locator("button", has_text="查看完整路径").click()
        try:
            await page.locator(".el-drawer .ir-note").wait_for(timeout=10000)
        except PWTimeout:
            pass
        note = (await page.locator(".el-drawer .ir-note").inner_text()).strip() \
            if await page.locator(".el-drawer .ir-note").count() else "(没有标注)"
        ck.check("IR 代码块有逐字标注", note == IR_NOTICE, f"dom={note!r}")
        ck.check("「查看完整路径」打开引擎报告（EngineReportViewer）",
                 await page.locator(".el-drawer .report-viewer").count() == 1)
        code_lines = await page.locator(".el-drawer .report-viewer .code-line").count()
        print(f"  IR 代码行 {code_lines} 行")
        ck.check("IR 代码块渲染出代码行", code_lines > 0)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)


# ── task 8 §二：整改操作（卡片内嵌） ─────────────────────────────────────────
async def pick_select(page, scope, label: str, option_text: str) -> None:
    """点开卡片里的某个 el-select，选中指定文案的选项（选项下拉是 teleport 到 body 的）。"""
    sel = scope.locator(".act", has_text=label).locator(".el-select").first
    await sel.click()
    await page.wait_for_timeout(300)
    await page.locator(".el-select-dropdown:visible .el-select-dropdown__item",
                       has_text=option_text).first.click()
    await page.wait_for_timeout(300)


async def verify_remediation(page, base: str, token: str, task_id: int, fid: int,
                             ck: Checker, console: list[str]) -> None:
    """task 8 §二：卡片上能改 triage_status / assigned_to / due_date，刷新后值还在。"""
    print(f"  [整改操作] finding {fid}")
    card = page.locator(".cards .el-collapse-item").first
    users = await fetch_json(page, base, token, "/system/users?page_size=100")
    user = (users or [{}])[0]
    uname = user.get("full_name") or user.get("username") or ""
    uid = user.get("id")

    ck.check("卡片上有整改操作区（两个下拉 + 日期 + 保存）",
             await card.locator(".card-actions").count() == 1
             and await card.locator(".card-actions .el-select").count() == 2
             and await card.locator(".card-actions .el-date-editor").count() == 1
             and await card.locator(".card-actions button", has_text="保存").count() == 1)

    # 记录原始值。这是**真业务库**：恢复必须落在 finally 里 —— 中途 Playwright 超时
    # 抛出时（不是 ck.check 失败），不能让 fixing/1/2026-12-31 留在库里。
    origin = next((f for f in (await fetch_findings(page, base, token, task_id))["items"]
                   if f["id"] == fid), {})
    due = "2026-12-31"

    try:
        await pick_select(page, card, "整改状态", TRIAGE_LABEL["fixing"])
        if uid:
            await pick_select(page, card, "负责人", uname)
        # 日期：直接在输入框里键入再回车，element-plus 会按 value-format 解析
        date_input = card.locator(".card-actions .el-date-editor input").first
        await date_input.click()
        await date_input.fill(due)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)

        await card.locator(".card-actions button", has_text="保存").click()
        try:
            await page.locator(".el-message--success").first.wait_for(timeout=8000)
        except PWTimeout:
            pass
        ck.check("保存后出现成功提示", await page.locator(".el-message--success").count() > 0)

        # 落库核对：直接打接口看服务端是否真的改了
        after = next((f for f in (await fetch_findings(page, base, token, task_id))["items"]
                      if f["id"] == fid), {})
        ck.check("triage_status 落库为 fixing", after.get("triage_status") == "fixing",
                 f"api={after.get('triage_status')}")
        if uid:
            ck.check("assigned_to 落库", after.get("assigned_to") == uid,
                     f"api={after.get('assigned_to')}")
        ck.check("due_date 落库", after.get("due_date") == due, f"api={after.get('due_date')}")

        # 刷新后界面上的值还在
        await goto_task(page, base, token, task_id)
        await page.wait_for_selector(".cards .el-collapse-item", timeout=15000)
        card = page.locator(".cards .el-collapse-item").first
        head = (await card.locator(".card-head").inner_text()).replace("\n", " | ")
        ck.check("刷新后卡片标签仍显示「整改中」", TRIAGE_LABEL["fixing"] in head, f"dom={head!r}")
        await card.locator(".el-collapse-item__header").click()
        await page.wait_for_timeout(600)
        body = (await card.locator(".card-body").inner_text()).replace("\n", " | ")
        ck.check("刷新后负责人/截止日期仍在",
                 (not uid or uname in body) and due in body, f"dom={body[:200]!r}")

        # 后端 400 时前端给出可读错误。这次 400 是故意注入的，只放行它带来的
        # 资源级噪音（mark 之后的窗口），正向路径其余 console 条目仍然严格判定。
        async def bad(route):
            await route.fulfill(
                status=400, content_type="application/json",
                body=json.dumps({"detail": "triage_status 只能是 needs_review / fixing / fixed / ignored"}))
        mark = len(console)
        await page.route("**/platform-findings/*/status", bad)
        try:
            await card.locator(".card-actions button", has_text="保存").click()
            try:
                await page.locator(".el-message--error").first.wait_for(timeout=8000)
            except PWTimeout:
                pass
            err = (await page.locator(".el-message--error").first.inner_text()).strip() \
                if await page.locator(".el-message--error").count() else "(没有错误提示)"
            ck.check("后端 400 时前端显示可读错误", "只能" in err, f"dom={err!r}")
        finally:
            await page.unroute("**/platform-findings/*/status")
            await page.wait_for_timeout(300)
            trim_resource_noise(console, mark)
    finally:
        # 恢复原始值，别把测试值留在库里（无论上面怎么退出都要执行）
        try:
            await page.request.put(
                f"{base}/api/v1/tasks/{task_id}/platform-findings/{fid}/status",
                headers={"Authorization": f"Bearer {token}"},
                data={"triage_status": origin.get("triage_status") or "needs_review",
                      "assigned_to": origin.get("assigned_to"),
                      "due_date": origin.get("due_date")},
            )
        except Exception as e:  # noqa: BLE001
            ck.check("整改用例结束前恢复原值", False, f"恢复失败，库里可能残留测试值：{e}")


# ── task 8 §一：App 背景侧滑面板 ────────────────────────────────────────────
async def verify_panel(page, base: str, token: str, task_id: int, ck: Checker) -> None:
    print(f"  [App 背景面板] task {task_id}")
    await open_panel(page, ck)
    panel = panel_of(page)
    try:
        await panel.locator(".bg-block").first.wait_for(timeout=10000)
    except PWTimeout:
        pass

    ck.check("右上角按钮打开面板", await panel.count() == 1)
    box = await panel.bounding_box()
    ck.check(f"面板宽度 {PANEL_WIDTH}px", bool(box) and abs(box["width"] - PANEL_WIDTH) < 1,
             f"width={box['width'] if box else None}")

    # 六块齐全且各有内容
    titles = [t.strip() for t in await panel.locator(".bg-block .bg-title").all_inner_texts()]
    blocks = await panel.locator(".bg-block").count()
    ck.check("面板六块齐全", blocks == len(PANEL_BLOCKS), f"dom={blocks}")
    for (_, label) in PANEL_BLOCKS:
        ck.check(f"「{label}」块有内容",
                 any(label in t for t in titles)
                 and await panel.locator(f".bg-block:has-text('{label}')").first.inner_text() != "")

    # §安全加固：五段按序 + missing 与空列表区分
    sec = await fetch_json(page, base, token, f"/tasks/{task_id}/security-findings")
    items_by_section = {it["section"]: it for it in sec.get("items") or []}
    missing = set(sec.get("missing") or [])
    dom_sections = await panel.locator(".sec-seg").evaluate_all(
        "els => els.map(e => e.getAttribute('data-section'))")
    ck.check("安全加固五段按固定顺序展示",
             dom_sections == [p for p, _ in SECURITY_SECTIONS], f"dom={dom_sections}")

    bad_missing = []
    for path, _label in SECURITY_SECTIONS:
        seg = panel.locator(f".sec-seg[data-section='{path}']")
        has_missing = await seg.locator(".sec-missing").count() > 0
        if path in missing and not has_missing:
            bad_missing.append(f"{path} 应写「{NO_SECTION}」")
        if path not in items_by_section and not has_missing:
            bad_missing.append(f"{path} 接口没给，应写「{NO_SECTION}」")
        if path in items_by_section and has_missing:
            txt = (await seg.locator(".sec-missing").first.inner_text()).strip()
            bad_missing.append(f"{path} 有数据却显示 {txt!r}")
    ck.check("missing 段落写「本任务没有这段数据」且与空列表区分", not bad_missing,
             "; ".join(bad_missing))

    # secrets 414 条不能撑爆：首屏只渲染前 N 条 + 限高，点开可见全部
    sec_payload = (items_by_section.get("secrets") or {}).get("payload") or []
    if sec_payload:
        seg = panel.locator(".sec-seg[data-section='secrets']")
        n = await seg.locator(".raw-item").count()
        ck.check(f"secrets 首屏只渲染前 {RAW_LIMIT} 条",
                 n == min(len(sec_payload), RAW_LIMIT), f"dom={n} api={len(sec_payload)}")
        h = await seg.locator(".raw-body").evaluate(
            "el => ({client: el.clientHeight, max: getComputedStyle(el).maxHeight})")
        ck.check("secrets 列表限高（不撑爆面板）",
                 h["max"] not in ("none", "") and h["client"] <= 360, f"{h}")
        more = seg.locator(".raw-more")
        if len(sec_payload) > RAW_LIMIT:
            ck.check("secrets 提供「显示全部」",
                     await more.count() == 1 and "显示全部" in (await more.inner_text()))
            await more.click()
            await page.wait_for_timeout(300)
            ck.check("展开后 secrets 条数 == 接口条数",
                     await seg.locator(".raw-item").count() == len(sec_payload),
                     f"dom={await seg.locator('.raw-item').count()} api={len(sec_payload)}")

    # §端点与网络：在面板里且只有一份
    ck.check("端点与网络块在面板里且只出现一次",
             await panel.locator(".net-evidence").count() == 1,
             f"dom={await panel.locator('.net-evidence').count()}")
    await verify_network(page, base, token, task_id, panel.locator(".net-evidence"), ck)

    # §合规画像 / SDK / 权限 三块各自到位
    ck.check("合规画像块渲染出画像组件",
             await panel.locator(".bg-block[data-block='profile'] .profile").count() == 1)
    ck.check("合规画像块内不再重复 SDK（避免与 SDK 块重复）",
             await panel.locator(".bg-block[data-block='profile'] .sdk-panel").count() == 0)
    ck.check("SDK 组件块渲染出 SdkPanel",
             await panel.locator(".bg-block[data-block='sdk'] .sdk-panel").count() == 1)
    await verify_permission_block(page, base, token, task_id, panel, ck)

    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)


async def verify_permission_block(page, base: str, token: str, task_id: int, panel,
                                  ck: Checker) -> None:
    """权限块必须是**现成展示**，不能是被重写的残版。

    简报 §一 对该块的要求是「沿用现成展示」。手写一张窄表会丢掉筛选栏
    （含「申请但未见使用」）、每行的 compliance_focus / method_count，
    以及「N 项权限的映射未覆盖，平台暂时无法判定是否被调用」这条披露——
    它是本项目「不假装有数据」的核心表述。这里逐条把它钉住。
    """
    prof = await fetch_json(page, base, token, f"/tasks/{task_id}/compliance-profile")
    perms = prof.get("permissions") or []
    judgeable = [p for p in perms if p.get("guard_mapped")]
    unmapped = [p for p in perms if not p.get("guard_mapped")]
    blocking = [p for p in judgeable if p.get("call_site_count", 0) == 0]

    block = panel.locator(".bg-block[data-block='permission']")
    ck.check("权限块沿用现成展示（筛选栏在）", await block.locator(".filter-bar").count() == 1)
    ck.check("权限块渲染的是现成权限卡片（#sec-permission）",
             await block.locator("#sec-permission").count() == 1)

    rows = await block.locator(".el-table__row").count()
    ck.check("权限表行数 == 可判定权限数（现成筛选口径）", rows == len(judgeable),
             f"dom={rows} api={len(judgeable)} total={len(perms)}")

    if blocking:
        ck.check("保留「申请但未见使用」筛选",
                 await block.locator(".el-radio-button", has_text="申请但未见使用").count() == 1)
    if unmapped:
        head = (await block.locator(".unmapped-head").inner_text()).strip() \
            if await block.locator(".unmapped-head").count() else "(没有披露条)"
        ck.check("保留「映射未覆盖」披露条",
                 f"{len(unmapped)} 项权限的映射未覆盖" in head, f"dom={head!r}")
    if judgeable:
        ck.check("权限行保留能力/合规说明（capability / compliance_focus）",
                 await block.locator(".compliance-focus, .sub-line").count() > 0)


async def verify_network(page, base: str, token: str, task_id: int, net, ck: Checker) -> None:
    """§5.4 网络证据块断言（作用域由调用方给：现在是面板里的那份）。"""
    ep = await fetch_json(page, base, token, f"/tasks/{task_id}/endpoints")
    hosts = ep.get("hosts") or []

    ep_note = (await net.locator(".net-note").inner_text()).strip() \
        if await net.locator(".net-note").count() else "(没有标注)"
    ck.check("网络块有逐字标注", ep_note == ENDPOINT_NOTICE, f"dom={ep_note!r}")

    if not ep.get("available"):
        absent = (await net.locator(".net-absent").inner_text()).strip() \
            if await net.locator(".net-absent").count() else "(没有说明)"
        ck.check("available:false 显示「该任务没有端点数据」", absent == NO_ENDPOINT, f"dom={absent!r}")
        ck.check("available:false 不渲染空 host 列表", await net.locator(".host").count() == 0)
        return

    names = [s.strip() for s in await net.locator(".host-name").all_inner_texts()]
    ck.check("网络块按 host 平铺且条数与接口一致",
             names == [h["host"] for h in hosts], f"dom={len(names)} api={len(hosts)}")
    ck.check("host 按 url_count 降序（后端已排好）",
             names == [h["host"] for h in sorted(hosts, key=lambda h: (-h["url_count"], h["host"]))])

    test_dom = await net.locator(".host.is-test").count()
    test_api = sum(1 for h in hosts if h["is_test_residue"])
    ck.check("测试服务器残留高亮行数一致", test_dom == test_api, f"dom={test_dom} api={test_api}")
    if test_api:
        flagged = await net.locator(".host.is-test .is-test-flag").all_inner_texts()
        ck.check("残留行带「测试服务器残留」标签",
                 all(t.strip() == "测试服务器残留" for t in flagged), f"{flagged[:3]}")

    low_api = [h for h in hosts if (h.get("attribution") or {}).get("confidence") == "low"]
    solid_api = [h for h in hosts if h.get("attribution") and
                 h["attribution"].get("confidence") != "low"]
    ck.check("低确信归属用 .is-lead 渲染（与 high 的 .is-solid 不同类）",
             await net.locator(".attr.is-lead").count() == len(low_api),
             f"dom={await net.locator('.attr.is-lead').count()} api={len(low_api)}")
    ck.check("高/中确信归属用 .is-solid 渲染",
             await net.locator(".attr.is-solid").count() == len(solid_api),
             f"dom={await net.locator('.attr.is-solid').count()} api={len(solid_api)}")
    if low_api:
        lead = net.locator(".attr.is-lead").first
        note = (await lead.locator(".attr-note").inner_text()).strip()
        ck.check("低确信归属显示依据/疑虑说明（note）",
                 len(note) > 10 and note == (low_api[0]["attribution"].get("note") or "").strip(),
                 f"dom={note[:60]!r}")
        ck.check("低确信归属标为「归属线索」不是「归属」",
                 (await lead.locator(".attr-label").inner_text()).strip() == "归属线索")
    attr_hosts = sum(1 for h in hosts if h.get("attribution"))
    ck.check("attribution 为空的 host 不渲染归属（不猜）",
             await net.locator(".host .attr").count() == attr_hosts,
             f"dom={await net.locator('.host .attr').count()} api={attr_hosts}")


# ── task 8 §三：整改概览 ────────────────────────────────────────────────────
async def verify_overview(page, base: str, token: str, task_id: int, ck: Checker,
                          console: list[str]) -> None:
    print(f"  [整改概览] task {task_id}")
    header = page.locator(".secondary-card .el-collapse-item__header", has_text="整改概览")
    ck.check("有「整改概览」折叠区（在底部）", await header.count() == 1)
    if not await header.count():
        return
    await header.click()
    await page.wait_for_timeout(800)
    ov = page.locator(".remediation")

    findings = (await fetch_findings(page, base, token, task_id))["items"]
    want = {k: sum(1 for f in findings if (f.get("triage_status") or "needs_review") == k)
            for k in TRIAGE_ORDER}
    got = [int(s.strip()) for s in await ov.locator(".tri-num").all_inner_texts()]
    ck.check("四态汇总与接口一致",
             got == [want[k] for k in TRIAGE_ORDER] and len(got) == 4,
             f"dom={got} api={[want[k] for k in TRIAGE_ORDER]}")
    caps = [s.strip() for s in await ov.locator(".tri-cap").all_inner_texts()]
    ck.check("四态中文标签", caps == [TRIAGE_LABEL[k] for k in TRIAGE_ORDER], f"dom={caps}")

    ret = await fetch_json(page, base, token, f"/tasks/{task_id}/retest-records")
    cols = ov.locator(".retest-col")
    ck.check("复检记录两个方向分开显示", await cols.count() == 2)
    t0 = await cols.nth(0).inner_text()
    t1 = await cols.nth(1).inner_text()
    ck.check("方向一：本任务的结论被复检", "本任务的结论被复检" in t0, t0.replace("\n", " ")[:60])
    ck.check("方向二：本任务作为复检任务", "本任务作为复检任务" in t1, t1.replace("\n", " ")[:60])

    own, as_retest = ret.get("items") or [], ret.get("as_retest") or []
    ck.check("方向一计数 == 接口 items",
             (await cols.nth(0).locator(".col-count").inner_text()).strip() == str(len(own)))
    ck.check("方向二计数 == 接口 as_retest",
             (await cols.nth(1).locator(".col-count").inner_text()).strip() == str(len(as_retest)))
    ck.check("方向一行数 == items 条数", await cols.nth(0).locator(".mini tbody tr").count() == len(own))
    ck.check("方向二行数 == as_retest 条数", await cols.nth(1).locator(".mini tbody tr").count() == len(as_retest))
    if not own:
        ck.check("方向一空态是「尚无复检记录」而非空表",
                 await cols.nth(0).locator(".col-empty").count() == 1)
    if not as_retest:
        ck.check("方向二空态不是空表", await cols.nth(1).locator(".col-empty").count() == 1)

    await verify_retest_failure(page, task_id, header, ck, console)


async def verify_retest_failure(page, task_id: int, header, ck: Checker,
                                console: list[str]) -> None:
    """复检取数挂了，不能渲染成「本任务的结论尚无复检记录」。

    「没有复检记录」是一句有结论意义的话，不能由一次失败冒充 —— 与问题清单的
    load-error、面板的 bg-error 同一原则。
    """
    await header.click()  # 收起 → v-if 卸载组件
    await page.wait_for_timeout(400)

    async def fail(route):
        await route.fulfill(status=500, content_type="application/json",
                            body=json.dumps({"detail": "模拟复检接口故障"}))

    mark = len(console)
    await page.route(RETEST_ROUTE, fail)
    try:
        await header.click()  # 展开 → 重新挂载并取数
        try:
            await page.locator(".retest-error").wait_for(timeout=10000)
        except PWTimeout:
            pass
        ck.check("复检取数失败时显示错误态", await page.locator(".retest-error").count() == 1,
                 (await page.locator(".retest-error").inner_text()).replace("\n", " ")
                 if await page.locator(".retest-error").count() else "(没有错误态)")
        ck.check("复检取数失败时**不**显示「尚无复检记录」",
                 await page.locator(".remediation", has_text="尚无复检记录").count() == 0)
        ck.check("复检取数失败时**不**显示「不是任何结论的复检任务」",
                 await page.locator(".remediation", has_text="不是任何结论的复检任务").count() == 0)
        ck.check("复检取数失败时不渲染空表/计数行",
                 await page.locator(".remediation .col-empty").count() == 0
                 and await page.locator(".remediation .retest-col").count() == 0)
    finally:
        await page.unroute(RETEST_ROUTE)
        await page.wait_for_timeout(300)
        trim_resource_noise(console, mark)

    retry = page.locator(".retest-error button", has_text="重试")
    if await retry.count():
        await retry.click()
        await page.wait_for_timeout(1500)
    ck.check("点重试后复检记录恢复",
             await page.locator(".retest-error").count() == 0
             and await page.locator(".remediation .retest-col").count() == 2)


async def verify_failure_path(page, base: str, token: str, task_id: int, ck: Checker,
                              out: str) -> list[str]:
    print(f"\n[失败路径] task {task_id}（platform-findings 返回 500）")

    async def fail(route):
        await route.fulfill(status=500, content_type="application/json",
                            body=json.dumps({"detail": "模拟后端故障"}))

    hits: list[str] = []
    page.on("request", lambda r: hits.append(r.url) if "platform-findings" in r.url else None)

    failure_console: list[str] = []
    listener = lambda m: failure_console.append(f"[{m.type}] {m.text}") if m.type in ("error", "warning") else None
    page.on("console", listener)
    page.on("pageerror", lambda e: failure_console.append(f"[pageerror] {e}"))

    await page.route(FINDINGS_ROUTE, fail)
    try:
        await goto_task(page, base, token, task_id)
        try:
            await page.wait_for_selector(".load-error", timeout=15000)
        except PWTimeout:
            pass

        err = (await page.locator(".load-error").inner_text()).replace("\n", " ") \
            if await page.locator(".load-error").count() else "(没有失败态)"
        ck.check("失败时出现失败态", await page.locator(".load-error").count() == 1, err)
        ck.check("失败态文案可区分（不是空态文案）", "问题清单加载失败" in err)
        ck.check("失败时显示重试按钮",
                 await page.locator(".load-error button", has_text="重试").count() == 1)
        ck.check("失败时**不**渲染「本次未形成平台结论」",
                 await page.locator(".el-empty", has_text="本次未形成平台结论").count() == 0)
        ck.check("失败时不渲染结论条与卡片",
                 await page.locator(".digest").count() == 0
                 and await page.locator(".cards .el-collapse-item").count() == 0)
        await page.screenshot(path=f"{out}/verify_{task_id}_failure.png")

        await page.unroute(FINDINGS_ROUTE)
        retry = page.locator(".load-error button", has_text="重试")
        if await retry.count():
            await retry.click()
            try:
                await page.wait_for_selector(".cards .el-collapse-item", timeout=15000)
            except PWTimeout:
                pass
            ck.check("点重试后恢复", await page.locator(".load-error").count() == 0
                     and await page.locator(".cards .el-collapse-item").count() > 0)
        else:
            ck.check("点重试后恢复", False, "页面上没有可点的重试按钮")
    finally:
        await page.unroute(FINDINGS_ROUTE)
        page.remove_listener("console", listener)

    print(f"  失败路径期间 platform-findings 请求 {len(hits)} 次：{hits}")
    noise = [e for e in failure_console if BROWSER_RESOURCE_NOISE in e]
    print(f"  浏览器资源级噪音（放行，见 BROWSER_RESOURCE_NOISE）{len(noise)} 条")
    ck.check("失败路径无 pageerror（rejected promise 被 catch 住）",
             not [e for e in failure_console if "[pageerror]" in e],
             "; ".join(e for e in failure_console if "[pageerror]" in e))
    ck.check("失败路径无应用级 console error",
             not app_errors(failure_console), "; ".join(app_errors(failure_console))[:400])
    return failure_console


# ── 可选的复检记录夹具：库里 retest_records 目前 0 行，两个方向都不会有内容。
#    想真正验「两个方向分开显示」时用 --inject-retest，跑完立刻删除。 ────────────
DB_URL = "postgresql://privacy:privacy123@localhost:5432/privacy_platform"


def inject_retest(task_id: int) -> list[int]:
    """插两条临时记录：一条「本任务的结论被复检」，一条「本任务作为复检任务」。"""
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("select id from platform_findings where task_id = %s order by id limit 1", (task_id,))
    mine = cur.fetchone()
    cur.execute("select id from platform_findings where task_id <> %s order by id limit 1", (task_id,))
    other = cur.fetchone()
    cur.execute("select id from detection_tasks where id <> %s order by id limit 1", (task_id,))
    other_task = cur.fetchone()[0]
    cur.execute("select id from users order by id limit 1")
    uid = cur.fetchone()[0]

    ids: list[int] = []
    if mine:  # 方向一：original_finding_id 属于本任务
        cur.execute(
            "insert into retest_records (original_finding_id, retest_task_id, result, notes,"
            " tested_by, tested_at) values (%s, %s, 'pass', '夹具：结论被复检', %s, now()) returning id",
            (mine[0], other_task, uid),
        )
        ids.append(cur.fetchone()[0])
    if other:  # 方向二：本任务是某条结论的复检任务
        cur.execute(
            "insert into retest_records (original_finding_id, retest_task_id, result, notes,"
            " tested_by, tested_at) values (%s, %s, 'fail', '夹具：本任务是复检任务', %s, now()) returning id",
            (other[0], task_id, uid),
        )
        ids.append(cur.fetchone()[0])
    conn.close()
    return ids


def remove_retest(ids: list[int]) -> None:
    if not ids:
        return
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = True
    conn.cursor().execute("delete from retest_records where id = any(%s)", (ids,))
    conn.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--task", type=int, action="append", default=None,
                    help="可重复；默认 810（含 null summary / L4-only）+ 3107")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--out", default="/tmp/shots", help="截图目录")
    ap.add_argument("--skip-failure", action="store_true")
    ap.add_argument("--inject-retest", action="store_true",
                    help="临时插两条复检记录以验证「两个方向分开显示」（跑完即删）")
    args = ap.parse_args()
    task_ids = args.task or [810, 3107]

    injected: list[int] = []
    if args.inject_retest:
        injected = inject_retest(task_ids[0])
        print(f"[夹具] 为 task {task_ids[0]} 插入复检记录 {injected}")

    ck = Checker()
    try:
        return await run(args, task_ids, ck)
    finally:
        remove_retest(injected)
        if injected:
            print(f"[夹具] 已删除复检记录 {injected}")


async def run(args, task_ids: list[int], ck: Checker) -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000},
                                        device_scale_factor=1)
        page = await ctx.new_page()
        console: list[str] = []
        page.on("console", lambda m: console.append(f"[{m.type}] {m.text}")
                if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: console.append(f"[pageerror] {e}"))

        await page.goto(f"{args.base}/login")
        resp = await page.request.post(f"{args.base}/api/v1/auth/login",
                                       data={"username": args.user, "password": args.password})
        body = await resp.json()
        if body.get("code") != 0:
            print(f"登录失败：{body}", file=sys.stderr)
            return 1
        token = body["data"]["access_token"]

        for tid in task_ids:
            console.clear()
            await goto_task(page, args.base, token, tid)
            await page.wait_for_timeout(4000)
            await verify_happy_path(page, args.base, token, tid, ck, console)
            await page.screenshot(path=f"{args.out}/verify_{tid}_fold.png")
            # 严格判定：故意注入的 400/500 已经在各自的作用域里被 trim_resource_noise
            # 就地放行，这里不再做任何全局宽容，资源级失败照样算错。
            ck.check(f"task {tid} 正向路径无 console error", not console, "; ".join(console[:5]))

        if not args.skip_failure:
            await verify_failure_path(page, args.base, token, task_ids[0], ck, args.out)
            await page.screenshot(path=f"{args.out}/verify_{task_ids[0]}_recovered.png")

        await browser.close()

    print(f"\n{'ALL PASS' if not ck.failed else 'FAILED: ' + '; '.join(ck.failed)}")
    return 1 if ck.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
