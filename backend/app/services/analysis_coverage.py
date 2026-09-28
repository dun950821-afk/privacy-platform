"""分析有效性判定：这次静态分析到底有没有覆盖到这个应用。

设计见 `docs/analysis-coverage-design.md`。要解决的问题是：

    引擎跑完了 ≠ 这个 App 被分析过了

实测（360 加固样本）：AppShark 报告 `completed`、0 个漏洞，而它分析的是加固壳——
该 APK 的 `classes.dex` 只声明 4 个类，manifest 却声明了 225 个组件。
平台当时把这种结果呈现为「扫描完成，未发现风险」，违反 Global Constraint
「不得把分析失败解释成「未发现风险」」。

三个取值，**默认是 UNKNOWN 而不是 FULL**：缺判定数据时把结果当成有效，正是上述故障的成因。
"""

FULL = "FULL"          # 判定依据充分，且分析覆盖到了应用代码
DEGRADED = "DEGRADED"  # 已判定：本次分析没有覆盖到应用代码，结果不可用于判断风险
UNKNOWN = "UNKNOWN"    # 缺少判定所需数据，不得当成 FULL


def artifact_verdict(summary: dict | None) -> tuple[str, dict]:
    """输入侧判定：这个 APK 的代码在不在 DEX 里。

    主判据是**结构性矛盾**，不需要阈值：manifest 里声明的每个组件都要有实现类，
    因此「声明的组件类**一个都不在** DEX 声明的类中」说明 DEX 里没有这个应用的代码
    （加固/壳）。

    用「全部缺失」而不是「类数少于组件数」：后者的反例是 `activity-alias`
    （多个组件指向同一个类）与动态特性包，会造成个别缺失；实测正常样本的缺失数为
    0/153 与 1/23、4/25，而加固样本是 225/225，两种形态分得很开。
    """
    if not summary:
        return UNKNOWN, {"reason": "缺少该 APK 的输入端统计（未启用 Androguard 时无法判定）"}

    total = summary.get("component_class_total")
    missing = summary.get("component_class_missing")
    if total is None or not total or missing is None:
        # 读不出 DEX 类名表 / 没有声明组件 → 判不了，不是"没问题"
        return UNKNOWN, {"reason": "未能读出 DEX 声明的类名或该应用未声明组件",
                         "component_class_total": total, "component_class_missing": missing}

    detail = {
        "criterion": "component_classes_all_missing" if missing == total else "component_classes_present",
        "component_class_total": total,
        "component_class_missing": missing,
        "class_count": summary.get("class_count"),
        "method_count": summary.get("method_count"),
    }
    if missing == total:
        detail["missing_sample"] = summary.get("component_class_missing_sample")
        return DEGRADED, detail
    return FULL, detail


def engine_verdict(engine_type: str, summary: dict | None, artifact: str) -> tuple[str, dict]:
    """引擎侧判定：在输入正常的前提下，这个引擎自己有没有跑到分析阶段。

    只处理引擎**自报**了覆盖量的情况。自报缺失或为零，说明它没跑到调用图阶段——
    历史数据里有 `event_count=0` 且连 `scan_stats` 都没有的执行，当时状态是 `completed`。
    """
    if artifact == DEGRADED:
        return DEGRADED, {"reason": "APK 侧已判定分析未覆盖应用代码，本引擎结果同样不可用",
                          "artifact": artifact}
    if artifact == UNKNOWN:
        return UNKNOWN, {"reason": "APK 侧无法判定，本引擎结果的有效性无从确认", "artifact": artifact}

    if engine_type == "appshark":
        stats = (summary or {}).get("scan_stats") or {}
        if not stats:
            return DEGRADED, {"criterion": "engine_scan_stats_missing"}
        if not stats.get("availableMethods") or not stats.get("availableClasses"):
            return DEGRADED, {"criterion": "engine_reported_zero_code",
                              "availableClasses": stats.get("availableClasses"),
                              "availableMethods": stats.get("availableMethods")}
        return FULL, {"criterion": "engine_reported_code",
                      "availableClasses": stats.get("availableClasses"),
                      "availableMethods": stats.get("availableMethods")}
    return FULL, {"criterion": "engine_has_no_self_reported_coverage"}


def task_verdict(verdicts: list[str]) -> str:
    """任务级：只要有引擎没覆盖到就是 DEGRADED；都没问题但信息不全则是 UNKNOWN。"""
    if DEGRADED in verdicts:
        return DEGRADED
    if not verdicts or UNKNOWN in verdicts:
        return UNKNOWN
    return FULL
