#!/usr/bin/env python3
"""任务详情页「问题清单」主视图验收脚本（task 6 / 计划 §5.1 + §5.2）。

重放方式（Playwright 只装在项目的 python venv 里，无 node 版）：

    /home/user/privacy-platform/.venv/bin/python \\
        frontend/scripts/verify-task-detail.py --task 810
    /home/user/privacy-platform/.venv/bin/python \\
        frontend/scripts/verify-task-detail.py --task 3107 --task 1244

前置：前端 vite 在 --base 上跑着、后端 8000 可达（vite 会把 /api 代理到 8000）。

脚本自己登录拿 token（不依赖 /tmp 下的临时令牌文件），然后断言两件事：

  正向路径  —— 主视图无 tab；结论条计数；卡片数与接口一致；按 severity 排序；
              构成说明只在 L2/L3 有值时出现（L4 不进、summary 为 null 不出现）；
              「证据 N 处」取自 observation_count；全程无 console error。
  证据块    —— §5.3 代码证据：按 observation 逐条列出 location 方法签名原文
              （含 location 为空时写「没有」而非空行）；「查看完整路径」打开
              EngineReportViewer 且带逐字标注「以下为 IR 代码（smali 风格），非 Java 源码」；
              没有 payload.url 的观察按钮置灰（点了才会 404）。
              §5.4 网络证据：按 host 平铺且与接口同序；测试服务器残留高亮；
              逐字标注「端点与规则的精确关联暂未建立，以上为 App 全部端点」；
              available:false 显示「该任务没有端点数据」而不是空列表；
              confidence=low 的归属用 .is-lead（与 high 的 .is-solid 不同）并显示 note；
              attribution 为空的 host 不渲染归属（不猜）。
  失败路径  —— 拦掉 platform-findings 返回 500 后，必须出现可重试的失败态，
              且**不得**出现「本次未形成平台结论」（失败不能冒充「确实没有结论」）；
              点「重试」后恢复。

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


def expected_composition(finding: dict) -> str | None:
    """无 summary（或只有 L4）时返回 None —— 卡片上整行不渲染，不显示「0 条」。"""
    summary = finding.get("provider_level_summary") or {}
    parts = [f"{summary[k]} 条{LEVEL_CN[k]}" for k in CARD_LEVELS if summary.get(k)]
    return f"由 {' + '.join(parts)}构成" if parts else None


def severity_rank(finding: dict) -> int:
    return SEVERITY_RANK.get(str(finding.get("severity", "")).lower(), 9)


def sorted_findings(findings: list[dict]) -> list[dict]:
    """页面上的顺序：severity 升序（high 在前），同 severity 保持接口顺序。
    list.sort / sorted 稳定，所以这同时是「排序键」与「稳定序」的期望值。"""
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


class Checker:
    def __init__(self) -> None:
        self.failed: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{f' — {detail}' if detail else ''}")
        if not ok:
            self.failed.append(name)


async def fetch_findings(page, base: str, token: str, task_id: int) -> dict:
    """直接打接口，作为 DOM 断言的期望值来源。"""
    resp = await page.request.get(
        f"{base}/api/v1/tasks/{task_id}/platform-findings",
        headers={"Authorization": f"Bearer {token}"},
    )
    body = await resp.json()
    assert body.get("code") == 0, body
    return body["data"]


async def fetch_json(page, base: str, token: str, path: str) -> dict:
    resp = await page.request.get(f"{base}/api/v1{path}",
                                  headers={"Authorization": f"Bearer {token}"})
    body = await resp.json()
    assert body.get("code") == 0, body
    return body["data"]


# ── 证据块（§5.3 + §5.4）期望值 ────────────────────────────────────────────────
# 两条标注是**逐字**要求（简报 Global Constraints 2 / 3），脚本按同一份字面量断言，
# 前端改了字就会在这里挂——这正是要拦的。
IR_NOTICE = "以下为 IR 代码（smali 风格），非 Java 源码"
ENDPOINT_NOTICE = "端点与规则的精确关联暂未建立，以上为 App 全部端点"
NO_ENDPOINT = "该任务没有端点数据"
NO_LOCATION = "（该条观察无方法签名）"
# 代码证据的长列表首屏只渲染这么多（与 CodeEvidenceBlock.PAGE 一致）
OBS_PAGE = 20


def obs_location(obs: dict) -> str:
    """与 CodeEvidenceBlock.locationOf 同一口径：缺失时是「没有」，不是空行。"""
    return obs.get("location") or NO_LOCATION


def has_report(obs: dict) -> bool:
    """后端按 payload.url 定位报告文件；没有 url 的观察没有 IR 报告可开。"""
    payload = obs.get("payload")
    return bool(payload.get("url")) if isinstance(payload, dict) else False


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


async def verify_happy_path(page, base: str, token: str, task_id: int, ck: Checker) -> None:
    print(f"\n[正向路径] task {task_id}")
    data = await fetch_findings(page, base, token, task_id)
    findings = data.get("items") or []
    print(f"  接口：total={data.get('total')} items={len(findings)}")

    # 等首屏落定；等不到不算异常，交给下面的断言报 FAIL（否则脚本会崩在 traceback 上，
    # 失去「哪条断言不过」的信息）
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
        return

    # 结论条：high / medium 计数
    high = sum(1 for f in findings if str(f.get("severity", "")).lower() == "high")
    medium = sum(1 for f in findings if str(f.get("severity", "")).lower() == "medium")
    digest = (await page.locator(".digest").inner_text()).replace("\n", " ")
    ck.check("结论条显示 high/medium 计数",
             digest.split()[:4] == [str(high), "高危", str(medium), "中危"],
             f"dom={digest!r} api=high:{high} medium:{medium}")

    heads = await cards.locator(".card-head").all_inner_texts()
    heads = [" | ".join(h.split("\n")) for h in heads]

    # 排序：DOM 顺序必须等于「severity 升序 + 同档保持接口顺序」
    want_order = [f["title"] for f in sorted_findings(findings)]
    got_order = [head_title(h) for h in heads]
    got_rank = [SEVERITY_RANK.get(h.split("|")[0].strip().replace("高危", "high").replace("中危", "medium"), 9)
                for h in heads]
    ck.check("按 severity 排序（high 在前、同档稳定）",
             got_order == want_order and got_rank == sorted(got_rank),
             f"ranks={got_rank}")

    # 逐条比对构成说明 / 证据条数（DOM 是排序后的，期望值也要按同一规则排序）
    comp_bad, ev_bad = [], []
    for f, head in zip(sorted_findings(findings), heads):
        want = expected_composition(f)
        if want and want not in head:
            comp_bad.append(f"id={f['id']} 期望 {want!r}")
        if not want:
            # 无 summary 或只有 L4：不能出现「构成」也不该出现「0 条」
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

    # 展开第一张卡：它的展开区里应当出现代码证据 + 网络证据两块
    first_finding_id = sorted_findings(findings)[0]["id"]
    await cards.locator(".el-collapse-item__header").first.click()
    await page.wait_for_timeout(800)
    ck.check("卡片可展开", await cards.locator(".card-body").first.is_visible())
    await verify_evidence(page, base, token, task_id, first_finding_id, ck)


async def verify_evidence(page, base: str, token: str, task_id: int, fid: int,
                          ck: Checker) -> None:
    """§5.3 代码证据块 + §5.4 网络证据块（卡片展开区）。"""
    print(f"  [证据块] finding {fid}")
    card = page.locator(".cards .el-collapse-item").first

    # ── §5.3 代码证据：逐条列出 observation 的方法签名原文 ──
    detail = await fetch_json(page, base, token, f"/tasks/{task_id}/platform-findings/{fid}")
    obs = detail.get("observations") or []
    try:
        await card.locator(".code-evidence .obs").first.wait_for(timeout=15000)
    except PWTimeout:
        pass

    rows = card.locator(".code-evidence .obs")
    got_n = await rows.count()
    ck.check("代码证据按 observation 逐条渲染",
             got_n == min(len(obs), OBS_PAGE),
             f"dom={got_n} api={len(obs)} 首屏={min(len(obs), OBS_PAGE)}")

    # 逐条比对方法签名原文（含 null 的「没有」）
    locs = [s.strip() for s in await rows.locator(".obs-loc").all_inner_texts()]
    want_locs = [obs_location(o) for o in obs[:OBS_PAGE]]
    ck.check("代码证据展示 location 方法签名原文", locs == want_locs,
             f"首条 dom={locs[:1]!r} api={want_locs[:1]!r} 不符={sum(1 for a, b in zip(locs, want_locs) if a != b)} 条")
    null_n = sum(1 for o in obs if not o.get("location"))
    print(f"  观察 {len(obs)} 条，其中 location 为空 {null_n} 条")

    # 「查看完整路径」的可用性必须与「有没有报告」一致：无 url 的观察不该可点
    btns = rows.locator("button", has_text="查看完整路径")
    want_enabled = [has_report(o) for o in obs[:OBS_PAGE]]
    got_disabled = [await btns.nth(i).is_disabled() for i in range(await btns.count())]
    ck.check("无引擎报告的观察「查看完整路径」置灰（点了才会 404）",
             got_disabled == [not e for e in want_enabled],
             f"disabled={got_disabled} 期望={[not e for e in want_enabled]}")

    # 长列表：展开全部后应等于接口返回条数
    if len(obs) > OBS_PAGE:
        more = card.locator(".code-evidence button", has_text="展开其余")
        ck.check("长列表提供「展开其余 N 条」", await more.count() == 1)
        if await more.count():
            await more.click()
            await page.wait_for_timeout(400)
            ck.check("展开其余后条数 == 接口条数",
                     await rows.count() == len(obs),
                     f"dom={await rows.count()} api={len(obs)}")

    # ── §5.3「查看完整路径」→ EngineReportViewer（IR 代码）+ 逐字标注 ──
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
        # 页面上还有别的 drawer（AppSharkPanel 等），`.el-drawer__close-btn` 会命中多个；
        # Escape 是 Element Plus drawer 的默认关闭方式，且只作用于最上层
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)

    # ── §5.4 网络证据块 ──
    ep = await fetch_json(page, base, token, f"/tasks/{task_id}/endpoints")
    hosts = ep.get("hosts") or []
    net = card.locator(".net-evidence")
    ck.check("网络证据块存在", await net.count() == 1)

    ep_note = (await net.locator(".net-note").inner_text()).strip() \
        if await net.locator(".net-note").count() else "(没有标注)"
    ck.check("网络块有逐字标注", ep_note == ENDPOINT_NOTICE, f"dom={ep_note!r}")

    if not ep.get("available"):
        absent = (await net.locator(".net-absent").inner_text()).strip() \
            if await net.locator(".net-absent").count() else "(没有说明)"
        ck.check("available:false 显示「该任务没有端点数据」", absent == NO_ENDPOINT, f"dom={absent!r}")
        ck.check("available:false 不渲染空 host 列表",
                 await net.locator(".host").count() == 0)
        return

    names = [s.strip() for s in await net.locator(".host-name").all_inner_texts()]
    ck.check("网络块按 host 平铺且条数与接口一致",
             names == [h["host"] for h in hosts],
             f"dom={len(names)} api={len(hosts)}")
    ck.check("host 按 url_count 降序（后端已排好）",
             names == [h["host"] for h in sorted(hosts, key=lambda h: (-h["url_count"], h["host"]))])

    # 测试服务器残留：黄色高亮 + 标签
    test_dom = await net.locator(".host.is-test").count()
    test_api = sum(1 for h in hosts if h["is_test_residue"])
    ck.check("测试服务器残留高亮行数一致", test_dom == test_api, f"dom={test_dom} api={test_api}")
    if test_api:
        flagged = await net.locator(".host.is-test .is-test-flag").all_inner_texts()
        ck.check("残留行带「测试服务器残留」标签",
                 all(t.strip() == "测试服务器残留" for t in flagged), f"{flagged[:3]}")

    # 归属：high/medium 与 low 必须视觉可区分，且 low 要显示 note
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
    # 留空的不猜：没有 attribution 的 host 不得渲染 .attr
    attr_hosts = sum(1 for h in hosts if h.get("attribution"))
    ck.check("attribution 为空的 host 不渲染归属（不猜）",
             await net.locator(".host .attr").count() == attr_hosts,
             f"dom={await net.locator('.host .attr').count()} api={attr_hosts}")


async def verify_failure_path(page, base: str, token: str, task_id: int, ck: Checker,
                              out: str) -> list[str]:
    """返回失败路径期间的 console 条目（含浏览器对 500 的资源级噪音）。"""
    print(f"\n[失败路径] task {task_id}（platform-findings 返回 500）")

    async def fail(route):
        await route.fulfill(
            status=500,
            content_type="application/json",
            body=json.dumps({"detail": "模拟后端故障"}),
        )

    hits: list[str] = []
    page.on("request", lambda r: hits.append(r.url) if "platform-findings" in r.url else None)

    # 失败路径期间单独收一份 console
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
        # 趁失败态还在，留一张证据截图（重试之后这个态就没了）
        await page.screenshot(path=f"{out}/verify_{task_id}_failure.png")

        # 恢复正常后点「重试」，应当拿到清单
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
    # 无 catch 时的 unhandled rejection 会以 pageerror 出现，必须为 0
    ck.check("失败路径无 pageerror（rejected promise 被 catch 住）",
             not [e for e in failure_console if "[pageerror]" in e],
             "; ".join(e for e in failure_console if "[pageerror]" in e))
    ck.check("失败路径无应用级 console error",
             not app_errors(failure_console), "; ".join(app_errors(failure_console))[:400])
    return failure_console


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:5173")
    ap.add_argument("--task", type=int, action="append", default=None,
                    help="可重复；默认 810（含 null summary / L4-only）+ 3107")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="admin123")
    ap.add_argument("--out", default="/tmp/shots", help="截图目录")
    ap.add_argument("--skip-failure", action="store_true")
    args = ap.parse_args()
    task_ids = args.task or [810, 3107]

    ck = Checker()
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
            await verify_happy_path(page, args.base, token, tid, ck)
            await page.screenshot(path=f"{args.out}/verify_{tid}_fold.png")
            ck.check(f"task {tid} 正向路径无 console error", not console, "; ".join(console[:5]))

        if not args.skip_failure:
            await verify_failure_path(page, args.base, token, task_ids[0], ck, args.out)
            await page.screenshot(path=f"{args.out}/verify_{task_ids[0]}_recovered.png")

        await browser.close()

    print(f"\n{'ALL PASS' if not ck.failed else 'FAILED: ' + '; '.join(ck.failed)}")
    return 1 if ck.failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
