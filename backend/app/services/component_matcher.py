"""组件指纹匹配：一处实现，两处共用。

## 为什么要合并

`api/v1/tasks.py::_match_sdk` 与 `services/sdk_analysis.py::_match` 是同一段逻辑的
两份实现，查询条件一模一样、返回结构不同，于是两处各自演化。更实际的问题是它们
**都不看 `match_mode`**：查询筛了 `EXACT` / `PREFIX`，拿到的却只是 `normalized_value`，
于是**一律按前缀比**。指纹库里的取值形态并不统一——

    PACKAGE_PREFIX / PREFIX   com.baidu.mobstat          （前缀，648 条）
    CLASS          / EXACT    com.sunyard...cameraaty    （完整类名，12 条）
    CLASS          / SUFFIX   weibomultimessage          （纯后缀，55 条）
    MANIFEST_*     / EXACT    com.huawei.hms...bridgeactivity（完整类名，168 条）
    MANIFEST_*     / SUFFIX   assistactivity             （纯后缀，65 条）
    PERMISSION     / EXACT    android.permission.nfc     （完整权限名，760 条）

一律当前缀比，会让 `...cameraatyFoo` 命中为 `...cameraaty` 登记的那条（EXACT 语义
失效）；而 `match_mode` 只放行 EXACT/PREFIX 的那个过滤条件，又让 55 条 `CLASS/SUFFIX`
与 65 条 `MANIFEST_*/SUFFIX` **压根不被加载**——库里存着、界面上看得到、匹配器不读。

## 匹配顺序

先比**层级**（见下），同一层级内再比 match_mode：**取匹配到的最长值**，长度相同按
EXACT > PREFIX > SUFFIX。

## 候选串形态：**必须先剥掉 AppShark 的 `<类: 方法签名>` 外壳**

这是 2026-09-29 才发现的、影响最大的一处：AppShark 事件的 `caller` 长这样

    <com.baidu.location.d.a: void b(com.baidu.location.BDNotifyListener)>

而匹配是 `candidate.startswith(前缀)`——**以 `<` 开头的串永远不可能以
`com.baidu.location` 开头**。实测 app_version 11：

    static_sensitive_api  15284 条   命中率 **0%**   ← 修复前
    static_data_flow       2935 条   命中率 **0%**
    static_component       2448 条   命中率 100%     ← caller 是裸类名，不受影响

修掉外壳后两类分别变成 78.1% / 81.6%，一个样本恢复 14326 条归属。
详见 `normalize_candidate()`。

## 层级

尝试顺序 **清单级 → 代码级**（权限级已在 2026-09-29 移除，理由见文末）：

    _TIER_MANIFEST(1)    MANIFEST_ACTIVITY / _SERVICE / _RECEIVER / _PROVIDER
    _TIER_CODE(0)        PACKAGE_PREFIX / CLASS / NATIVE_SO

清单在前，是因为**两者说的是不同的事**：清单登记 =「这个组件声明使用/暴露了这个
类」，包名前缀 =「这个类定义在谁的命名空间下」。问「谁在采集」，前者更贴题——一个
SDK 完全可能复用别人命名空间下的类并把它登记进自己的清单。

## 重复登记：库里最普遍的数据问题

同一个取值被多个组件登记，库里 **744 处**（`ComponentIndex.duplicate_count` 可体检）。
task 2348 上 4 条争议事件全是这个形状：

    ...tbs.TBSFileViewActivity        腾讯 X5/TBS 与 TBS 文件预览封装组件 都登记了
    ...activity.contacts.ContactsActivity   屹通移动门户业务 Activity 与 屹通通讯录业务模块
    ...flutter.PortalFlutterActivity  屹通移动门户基础模块 与 Flutter 集成模块
    io.flutter...ImagePickerFileProvider    Flutter 与 Flutter Image Picker 插件

**两者登记的是同一个字符串，靠清单本身分不出来。** 判据是**代码级指纹对这个类的
匹配长度**——谁在命名空间上更贴近它，谁更具体。4 条由此全部落到具体组件上。

两个组件都没有代码级证据时，取组件 id 较小的一条——**只保证确定性，不代表更正确**。
最初实现用 `setdefault`（先到先得），谁赢取决于数据库返回的行序，实测把
ImagePickerFileProvider 判给了笼统的「Flutter」。

## 没解决的那一半：权限指纹的归属本身就是含糊的

760 条 PERMISSION 指纹里，同一条权限被多个组件认领的情况很常见。例如
`android.permission.access_fine_location` 同时挂在高德定位 SDK 与百度定位 SDK 上——
**从一条权限声明判不出 App 用的是哪个**，无论怎么定序都只是选一个。

实测对照过另一种实现（不设层级、单池按最长值匹配）：它多出 7 个组件，但那些多出来的
全是「在含糊数据上抛硬币」的结果——例如它把上述权限判给高德，只是因为查询行序恰好
如此，不是因为证据更强。所以选了确定性更好的这一版。

真正的修法在数据侧：重复登记应由上游去重，权限与组件的关联需要更强的证据
（如权限 + 代码级指纹同时命中），不该由匹配器掩盖。

## 实际效果（task 2348，同一批事件）

    旧语义  63 个组件 / 153 条证据（只扫 static_component、一律前缀）
    新语义  66 个组件 / 188 条证据（全事件、三种语义、层级 + 具体性）

4 条争议事件均落到更具体的组件；没有一条事件失去归属（153/153 仍命中）；
新增 ZXing、飞虎互动音视频 SDK、OPPO/HeyTap 推送 SDK 等。

## 候选串从哪来

调用方负责给对候选。事件的 `caller`、`api`、组件名、权限名都直接传进来即可：
不同 `fingerprint_type` 的取值本就分属这些字段，按语义匹配由本模块负责。

## 未纳入的类型，与一条被纠正的建模错误

`API_SIGNATURE`（959 条）的取值是**中文能力标签**（`sqlite/orm/键值存储/加密数据库`），
不是可匹配的签名，任何候选串都无从比起；`MAVEN_COORDINATE`（200 条）需要构建期依赖
坐标，当前管线不从 APK 提取。两者都不在 `MATCHABLE_TYPES` 里——它们是描述性数据，
不是匹配项，**不要把它们接进匹配器**。

`PERMISSION`（760 条）**曾经被接进来，是错的，已移除**。取「某组件声明了权限 P」去
反推「P 在 App 里」在建模上就不成立：权限是**共性**，不是**特征**。库里
`android.permission.INTERNET` 关联着 **229 个组件**、`ACCESS_NETWORK_STATE` 103 个、
`CAMERA` 74 个——从一条权限声明判不出 App 用的是哪一个。实测把 26 条权限指纹接进
匹配后，`ACCESS_FINE_LOCATION` 同时挂在高德定位 SDK 与百度定位 SDK 上，匹配器只能
按组件 id 抛硬币，产出的是**看着像结论的噪声**。

权限与组件的关系**本来就有**正确的存放处：`privacy_kb.component_permission` 表
（760 条关系，与这批指纹一一对应）。它是**关系**，用于展示与「谁需要什么权限」的
分析；要参与归属，必须与更强的证据组合（例如权限 + 代码级指纹同时命中），
不能单凭权限定归属。这条判断在接新指纹类型时都适用：
**先问它能不能指认唯一组件，再问它能不能匹配。**
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.kb import KBComponent, KBComponentFingerprint, KBVendor

# 能参与匹配的指纹类型。加类型前先确认两件事：
#   1) 取值是「可比的字符串」，不是能力标签之类的描述性数据；
#   2) 它**足以指认唯一组件**——共性太强的东西不能当指纹（见 PERMISSION 的教训）。
MATCHABLE_TYPES = (
    "PACKAGE_PREFIX", "CLASS",
    "MANIFEST_ACTIVITY", "MANIFEST_SERVICE",
    "MANIFEST_RECEIVER", "MANIFEST_PROVIDER",
    "NATIVE_SO",
)

# 按语义分派：EXACT 要相等、PREFIX 要比开头、SUFFIX 要比结尾。
MATCH_MODES = ("EXACT", "PREFIX", "SUFFIX")


def normalize_candidate(value: str | None) -> str:
    """把候选串归一成可比形态：**去掉 AppShark 的 `<类: 方法签名>` 外壳**。

    AppShark 事件里 `caller` / `api` 长这样：

        <com.baidu.location.d.a: void b(com.baidu.location.BDNotifyListener)>
        ['<com.tencent.turingface...: void x()>->$r0']

    而匹配是 `candidate.startswith(前缀)`。**以 `<` 开头的串永远不可能以
    `com.baidu.location` 开头**——于是凡是这种形态的事件，包名前缀匹配全军覆没。

    实测（app_version 11）：`static_sensitive_api` 15284 条、`static_data_flow` 2935 条
    **命中率恒为 0%**；而 `static_component`（caller 是裸类名）命中率 100%。
    这两类恰恰是最能说明「谁在采集」的——敏感 API 调用与数据流。

    只去外壳，不改内容：`<A: void b()>` → `a`；`['<A: void b()>->$r0']` → `a`。
    非该形态的原样小写返回（裸类名、`.so` 文件名、权限名都走这条路）。
    """
    c = (value or "").strip()
    if not c:
        return ""
    # `['<...>->$r0']` / `<...>` 两种包装都先剥掉
    c = c.lstrip("[")
    c = c.lstrip("'\"").strip()
    if c.startswith("<"):
        c = c[1:].split(":")[0].strip()
    return c.lower()

# 层级：决定「谁有资格给归属」。数字小的先试，命中即返回。
#
#   代码级 —— 这个类的包名/类名本身就指向该组件，最贴近「这个类是谁的」
#   清单级 —— 该组件在自己的清单里登记了这个类。但这只说明「它声明了这个组件」，
#             同一个类完全可能被两个组件同时登记（库里确有，见 _duplicates）
#   权限级 —— 只能匹配权限名，与类名/包名不同域，放最后
_TIER_CODE, _TIER_MANIFEST = 0, 1
# 尝试顺序：**清单级在前**。清单登记说的是「这个组件声明使用/暴露了这个类」，
# 对「谁在采集」这个问题，这比「这个类定义在谁的命名空间下」更贴题——
# 一个 SDK 完全可能复用别人命名空间下的类并把它登记进自己的清单。
_TIERS = (_TIER_MANIFEST, _TIER_CODE)

TIER_OF = {
    "PACKAGE_PREFIX": _TIER_CODE,
    "CLASS": _TIER_CODE,
    # native 库名与类名/包名不同域（它是 `lib*.so` 的文件名），放代码级即可——
    # 一个 .so 文件名不会被类名前缀命中，反之亦然，实际不会竞争。
    "NATIVE_SO": _TIER_CODE,
    "MANIFEST_ACTIVITY": _TIER_MANIFEST,
    "MANIFEST_SERVICE": _TIER_MANIFEST,
    "MANIFEST_RECEIVER": _TIER_MANIFEST,
    "MANIFEST_PROVIDER": _TIER_MANIFEST,
}


class ComponentIndex:
    """指纹索引。按【层级 × match_mode】分组存放，避免匹配时再逐一比对。

    层级（`_TIERS`）决定谁有资格给归属——见模块文档「层级」一节。同一层级内再按
    match_mode 分派。
    """

    __slots__ = ("_tiers", "size", "_duplicates", "_code_by_component")

    def __init__(self) -> None:
        # tier -> {"exact": {值: [entry, ...]}, "prefix": [(值, entry)], "suffix": [...]}
        self._tiers: dict[int, dict] = {
            t: {"exact": {}, "prefix": [], "suffix": []} for t in _TIERS
        }
        self.size = 0
        # 组件 id -> 它的代码级指纹 [(值, mode)]，用于重复登记时分胜负
        self._code_by_component: dict[int, list[tuple[str, str]]] = {}
        # 同一取值被多个组件登记的记录。知识库里确实存在（同一个 activity 被
        # 两个组件都登记过），这里只统计不修数据——数据质量是上游的事。
        self._duplicates: list[tuple[str, int, int]] = []

    def _add(self, value: str, mode: str, entry: dict) -> None:
        tier = TIER_OF.get(entry["fingerprint_type"])
        if tier is None:                      # 未登记层级的类型一律不收
            return
        # 归一化放这里，不放调用方——匹配时一律用小写比较，取值若带大写就永远匹配不上。
        # 这个假设原先只写在 load_component_index 里，直接调 _add 的调用方会踩空。
        value = (value or "").strip().lower()
        if not value:
            return
        self.size += 1
        slots = self._tiers[tier]
        if mode == "EXACT":
            # **保留全部重复登记**，不在这里分胜负——给哪个组件要看候选串，
            # 索引阶段还不知道候选串是什么（见 _resolve_duplicates）。
            bucket = slots["exact"].setdefault(value, [])
            if all(e["component_id"] != entry["component_id"] for e in bucket):
                if bucket:
                    self._duplicates.append((value, bucket[0]["component_id"], entry["component_id"]))
                bucket.append(entry)
        elif mode == "PREFIX":
            slots["prefix"].append((value, entry))
        elif mode == "SUFFIX":
            slots["suffix"].append((value, entry))
        if tier == _TIER_CODE:
            self._code_by_component.setdefault(entry["component_id"], []).append((value, mode))

    def _freeze(self) -> None:
        for slots in self._tiers.values():
            # 同层级内最长优先：`com.foo.bar` 要压过 `com.foo`；同长时按组件 id 定序，
            # 保证结果不依赖数据库返回行序。
            slots["prefix"].sort(key=lambda x: (len(x[0]), -x[1]["component_id"]), reverse=True)
            slots["suffix"].sort(key=lambda x: (len(x[0]), -x[1]["component_id"]), reverse=True)

    @property
    def duplicate_count(self) -> int:
        """同一取值被多个组件登记的处数。用于体检，不参与匹配。"""
        return len(self._duplicates)

    def _code_specificity(self, component_id: int, c: str) -> int:
        """该组件对候选串的代码级匹配长度；无匹配返回 -1。

        只在重复登记的候选之间用来分胜负，所以扫描范围是该组件自己的指纹，
        不是全表。
        """
        best = -1
        for value, mode in self._code_by_component.get(component_id, ()):
            if mode == "EXACT" and c == value:
                return len(value)
            if mode == "PREFIX" and c.startswith(value):
                best = max(best, len(value))
            elif mode == "SUFFIX" and c.endswith(value):
                best = max(best, len(value))
        return best

    def _resolve_duplicates(self, entries: list[dict], c: str) -> dict:
        """同一取值被多个组件登记时，选「对这个类最具体」的那个。

        判据是**代码级指纹的匹配长度**：谁对这个类名/包名的匹配更长，谁更具体。
        全都不匹配时退到组件 id 最小者——**只保证确定性**，不代表更正确；
        库里这种重复登记有数百处，那是知识库的数据质量问题，不该由匹配器掩盖。
        """
        if len(entries) == 1:
            return entries[0]
        return min(entries, key=lambda e: (-self._code_specificity(e["component_id"], c),
                                           e["component_id"]))

    def _match_in_tier(self, tier: int, c: str) -> dict | None:
        slots = self._tiers[tier]
        exact = slots["exact"].get(c)
        if exact:
            # 精确命中就是最长的可能值（等于候选串全长），无需再比前缀
            return {**self._resolve_duplicates(exact, c), "matched_value": c, "match_mode": "EXACT"}
        for value, entry in slots["prefix"]:
            if c.startswith(value):
                return {**entry, "matched_value": value, "match_mode": "PREFIX"}
        for value, entry in slots["suffix"]:
            if c.endswith(value):
                return {**entry, "matched_value": value, "match_mode": "SUFFIX"}
        return None

    def match(self, *candidates: str | None) -> dict | None:
        """按调用方给的候选串顺序（调用方优先）返回首个命中。

        同一候选串内**先比层级、再比 match_mode**：代码级指纹（包名前缀/类名）优先于
        清单级（MANIFEST_*），后者又优先于权限级。层级内部取匹配到的最长值。

        这条层级规则是实测倒逼的：知识库里同一个类名常被**两个组件同时登记**
        （某个 Activity 既属于某个包装库、又被上游 SDK 的清单登记），此时谁赢本该由
        「谁更具体」决定。实测 4 条争议事件（TBSFileViewActivity、
        ContactsActivity、PortalFlutterActivity、ImagePickerFileProvider）全部是
        这种重复登记，而每次都只有「代码级前缀那条路」给出更具体的组件。
        所以定成：清单级指纹不得覆盖代码级指纹给更细粒度组件定的归属。

        返回值是 entry 的副本外加 `matched_value` 与 `match_mode`，
        调用方不必回头去查命中的是哪条指纹。
        """
        for cand in candidates:
            if not cand:
                continue
            c = normalize_candidate(cand)
            if not c:
                continue
            for tier in _TIERS:
                hit = self._match_in_tier(tier, c)
                if hit:
                    return hit
        return None


def load_component_index(db: Session) -> ComponentIndex:
    """从知识库构建索引。

    不用缓存层：本函数由调用方按需缓存（见 `cached_component_index`），
    这样「什么时候可以复用」这件事留在调用方，不藏在这里。
    """
    rows = (
        db.query(KBComponentFingerprint, KBComponent, KBVendor)
        .join(KBComponent, KBComponentFingerprint.component_id == KBComponent.id)
        .outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id)
        .filter(
            KBComponentFingerprint.fingerprint_type.in_(MATCHABLE_TYPES),
            KBComponentFingerprint.match_mode.in_(MATCH_MODES),
            KBComponentFingerprint.is_negative == False,   # noqa: E712  (库里暂无负指纹，留着防将来)
            KBComponent.is_active == True,                 # noqa: E712
        )
        .all()
    )
    index = ComponentIndex()
    for fp, comp, vendor in rows:
        value = (fp.normalized_value or "").strip().lower()
        if not value:
            continue
        index._add(value, (fp.match_mode or "").upper(), {
            # `id` 与 `component_id` 同值：旧实现返回的 `comp["id"]` 就是组件 id，
            # 事件接口把它直接塞进响应，前端按 `id` 取。保留 `id` 是为了不改前端契约，
            # 新代码请用语义更明确的 `component_id`。
            "id": comp.id,
            "component_id": comp.id,
            "name": comp.name,
            "vendor": vendor.name if vendor else None,
            "component_kind": comp.component_kind,
            "category_l1": comp.category_l1,
            "sensitivity_level": comp.sensitivity_level,
            "fingerprint_id": fp.id,
            "fingerprint_type": fp.fingerprint_type,
            "weight": fp.weight or 0,
        })
    index._freeze()
    return index


_CACHE: dict = {"key": None, "index": None}


def _kb_version(db: Session) -> tuple:
    """知识库的「版本」：两张表各自的最大 updated_at 与行数。

    用它做缓存失效判据，而不是 TTL——指纹改了要立刻生效，等 60 秒会让人以为
    编辑没保存。这个查询走主键外的聚合，但两张表都只有几千行，代价可忽略。
    """
    from sqlalchemy import func

    fp_max, fp_n = db.query(
        func.max(KBComponentFingerprint.updated_at), func.count(KBComponentFingerprint.id)
    ).one()
    comp_max, comp_n = db.query(
        func.max(KBComponent.updated_at), func.count(KBComponent.id)
    ).one()
    return (str(fp_max), fp_n, str(comp_max), comp_n)


def cached_component_index(db: Session) -> ComponentIndex:
    """带失效判据的索引缓存。

    `/tasks/{tid}/events` 每次请求都要匹配一遍全量事件（实测单任务 1700+ 条），
    而知识库在一次会话里基本不变——不缓存等于每次请求重建索引。
    """
    key = _kb_version(db)
    if _CACHE["key"] == key and _CACHE["index"] is not None:
        return _CACHE["index"]
    index = load_component_index(db)
    _CACHE["key"] = key
    _CACHE["index"] = index
    return index
