# AppShark 规则能力边界（实测）

样本：营口银行 v4.5.1（`app_version_id=12`），未加固，DEX 引用了 `ContactsContract`。
每次实验均为真实任务，结果取自 `engine_observations`。

## 能力矩阵

| # | 能力 | 状态 | 依据 |
|---|---|---|---|
| 1 | API Fact：识别 `ContentResolver.query()` 调用 | **VERIFIED** | `APIMode: true` + 方法签名作 sink → 命中 76 次 |
| 2 | URI Fact：识别 Contacts URI 常量 | **FAILED** | `Field` source 用 `Contacts.CONTENT_URI` → 未命中 |
| 3 | URI → query：证明该 URI 是 query 的参数 | **NOT_VERIFIED** | 依赖 #2，未单独验证 |
| 4 | query → Cursor：保持返回对象语义 | **NOT_VERIFIED** | 未验证 |
| 5 | Contacts Data → Sink | **NOT_EXPRESSIBLE** | 见「关键失败」 |
| 6 | 跨类目隔离 | **NOT_VERIFIED** | 未验证；#1 的类目无关性使该风险具体存在 |

## 关键失败

### 失败 1：URI 常量不能作为 APIMode 的 sink

```text
错误写法  "APIMode": true, sink: {"<ContactsContract$Contacts: * CONTENT_URI>": {}}
结果      零命中
原因      APIMode 的 sink 列表只匹配方法签名，不识别静态字段常量
对照      DeviceId_APICall（方法签名作 sink）同次运行命中 18 次
```

### 失败 2：URI 常量作为 Field source 无法传播到 sink

```text
写法      source.Field = [Contacts.CONTENT_URI...]，sink = Log.d/i/e
结果      零命中
```

### 失败 3：`ContentResolver.query` 作 Return source 无法传播到网络

```text
写法      source.Return = [<ContentResolver: * query(*)>]，sink = 网络栈
结果      零命中
原因      污点在 LibraryOnly + InstantDefault 模型下不传播到 sink
```

## 由实验 A 得出的关键推论

实验 A 命中的是 `ContentResolver.query` —— 这是**所有内容提供者共用的唯一调用点**：

```text
76 次命中
  ├── 其中可能包含通讯录查询
  ├── 也可能包含日历、媒体、通话记录、设置等一切查询
  └── 该观测无法区分是哪一个
```

因此：

```text
正确命名  fact.content_resolver_query        ✓ 只声明「调用了查询 API」
错误命名  fact.contacts_read / contacts_data_read  ✗ 语义扩大
```

同时说明：**不给 #6 跨类目隔离做验证，就无法把 `ContentResolver.query` 用于任何类目专属结论。**

## 结论

contacts / sms / calllog 的「读取 → 外传」在当前 AppShark 规则语言与引擎配置下 **不可静态表达**。

- 检测「调用了查询 API」：可以（类目无关）
- 检测「查询目标是通讯录」：**不能**（URI 常量既不能作 sink，也不能作可传播的 source）
- 因此无法形成「通讯录数据 → 网络」的 source→sink 规则

这不是规则库缺口，是能力边界。不得通过扩大 Source 范围（例如用 `ContentResolver.query` 冒充通讯录来源）来制造覆盖假象。

## 未完成

- #6 跨类目隔离未验证。若要使用 `ContentResolver.query` 观测，**必须先完成此验证**：至少覆盖 Contacts / Calendar / CallLog / Media，确认不会互相误判。
