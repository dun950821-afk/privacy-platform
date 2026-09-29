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

对每个候选串依次尝试三种语义，**取匹配到的最长值**；长度相同时按
**EXACT > PREFIX > SUFFIX** 定夺。

「最长优先」不是随手定的，是实测倒逼的：先按「EXACT 一律优先于 PREFIX」实现，
在真实样本（task 2348）上比对新旧结果，发现会**丢掉 4 个原本归属正确的组件**——
一个精确登记的短值压过了更长的前缀登记，把归属改判到别的组件上。归属错误在
「谁在采集」这条主线上比漏报代价更高，所以沿用原来的「最长优先」，语义只在长度
相同时用来分胜负。

实际效果（task 2348，同一批事件，仅换匹配语义）：

    旧语义  63 个组件 / 153 条证据（只扫 static_component，一律前缀）
    新语义  67 个组件 / 188 条证据（全事件，三种语义）

**有 4 条事件改了归属，别把这件事说成「无变化」。** 它们是原本按包名前缀命中的
模块，现在被显式登记的 `MANIFEST_*/EXACT`（完整类名）接管：

    ...tbs.TBSFileViewActivity       TBS 文件预览封装组件 → 腾讯 X5/TBS
    ...contacts.ContactsActivity     屹通通讯录业务模块   → 屹通移动门户业务 Activity
    ...flutter.PortalFlutterActivity 屹通移动门户 Flutter 集成模块 → 屹通移动门户基础模块
    io.flutter.plugins.imagepicker
      .ImagePickerFileProvider       Flutter Image Picker 插件 → Flutter

前三条是「具体类名压过模块前缀」，可以接受；**第四条明显变粗**（`Flutter` 比
`Flutter Image Picker 插件` 更笼统）。没有一条事件失去归属（153/153 仍命中），
但第四条那种「精确登记指向更泛的组件」的取舍，需要业务上认账——若认为不可接受，
就得给 MANIFEST 类指纹加一条「不得覆盖更细粒度组件」的约束，而不是把 EXACT 关掉。

## 候选串从哪来

调用方负责给对候选。事件的 `caller`、`api`、组件名、权限名都直接传进来即可：
不同 `fingerprint_type` 的取值本就分属这些字段，按语义匹配由本模块负责。

## 未纳入的类型

`API_SIGNATURE`（959 条）的取值是**中文能力标签**（`sqlite/orm/键值存储/加密数据库`），
不是可匹配的签名，任何候选串都无从比起；`MAVEN_COORDINATE`（200 条）需要构建期依赖
坐标，当前管线不从 APK 提取。两者都不在 `MATCHABLE_TYPES` 里——它们是描述性数据，
不是匹配项，**不要把它们接进匹配器**。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.kb import KBComponent, KBComponentFingerprint, KBVendor

# 能参与匹配的指纹类型。加类型前先确认它的取值是「可比的字符串」，
# 而不是能力标签之类的描述性数据。
MATCHABLE_TYPES = (
    "PACKAGE_PREFIX", "CLASS",
    "MANIFEST_ACTIVITY", "MANIFEST_SERVICE",
    "MANIFEST_RECEIVER", "MANIFEST_PROVIDER",
    "PERMISSION",
)

# 按语义分派：EXACT 要相等、PREFIX 要比开头、SUFFIX 要比结尾。
MATCH_MODES = ("EXACT", "PREFIX", "SUFFIX")


class ComponentIndex:
    """指纹索引。三种 match_mode 各存一份，避免匹配时再去分派。"""

    __slots__ = ("_exact", "_prefix", "_suffix", "size")

    def __init__(self) -> None:
        self._exact: dict[str, dict] = {}
        self._prefix: list[tuple[str, dict]] = []
        self._suffix: list[tuple[str, dict]] = []
        self.size = 0

    def _add(self, value: str, mode: str, entry: dict) -> None:
        self.size += 1
        if mode == "EXACT":
            # 同一取值重复登记时保留先到的：库里 MANIFEST_ACTIVITY 有重复值
            # （同一 activity 登记了两次），保留哪条都一样，但要有确定行为。
            self._exact.setdefault(value, entry)
        elif mode == "PREFIX":
            self._prefix.append((value, entry))
        elif mode == "SUFFIX":
            self._suffix.append((value, entry))

    def _freeze(self) -> None:
        # 同级内部最长优先：`com.foo.bar` 要压过 `com.foo`
        self._prefix.sort(key=lambda x: len(x[0]), reverse=True)
        self._suffix.sort(key=lambda x: len(x[0]), reverse=True)

    def match(self, *candidates: str | None) -> dict | None:
        """按调用方给的候选串顺序（调用方优先）返回首个命中。

        **同一候选串内取「匹配到的最长值」**，长度相同时才按 EXACT > PREFIX > SUFFIX
        定夺。这一条是实测倒逼出来的：曾按「EXACT 一律优先于 PREFIX」实现，在真实
        样本上比对发现会**丢掉 4 个原本归属正确的组件**——某个精确登记的短值会压过
        更长的前缀登记，把归属改判到另一个组件上。归属错误的代价在「谁在采集」这条
        主线上比漏报更高，所以沿用原来的「最长优先」，只在长度相同时用语义分胜负。

        返回值是 entry 的副本外加 `matched_value` 与 `match_mode`，
        调用方不必回头去查命中的是哪条指纹。
        """
        for cand in candidates:
            if not cand:
                continue
            c = cand.strip().lower()
            if not c:
                continue
            best: tuple[int, int, dict] | None = None   # (值长度, 语义优先级, entry)
            exact = self._exact.get(c)
            if exact:
                best = (len(c), 0, {**exact, "matched_value": c, "match_mode": "EXACT"})
            for value, entry in self._prefix:
                if len(value) <= (best[0] if best else 0):
                    break       # 已按长度降序，再短的不可能更优
                if c.startswith(value):
                    best = (len(value), 1, {**entry, "matched_value": value, "match_mode": "PREFIX"})
                    break
            for value, entry in self._suffix:
                if len(value) <= (best[0] if best else 0):
                    break
                if c.endswith(value):
                    best = (len(value), 2, {**entry, "matched_value": value, "match_mode": "SUFFIX"})
                    break
            if best:
                return best[2]
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
