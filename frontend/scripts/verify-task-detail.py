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

    # 展开一张卡，确认折叠态可展开、且不报错
    await cards.locator(".el-collapse-item__header").first.click()
    await page.wait_for_timeout(600)
    ck.check("卡片可展开", await cards.locator(".card-body").first.is_visible())


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
