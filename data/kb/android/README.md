# Android 权限官方描述

`permission_descriptions.json`：**常量名 → 官方英文描述**，抽自 Android 官方参考页
`https://developer.android.google.cn/reference/android/Manifest.permission`。

抓取注意：该 URL 会重定向，**必须跟随重定向**（`curl -L`）才能拿到真页面（约 2.8MB 的表格）；
不跟随只会拿到一个 "Redirecting..." 的空壳。页面是服务端渲染的静态表格，可直接正则抽取：

```
<a href="/reference/android/Manifest.permission#NAME">NAME</a></code> <p>描述</p>
```

**这是目前唯一能取到的权威权限描述来源。** 试过且不可用的：
- AOSP `core/res/AndroidManifest.xml`：1018 条里只有 17 条带 `android:description`，且能解出
- AOSP `core/res/res/values/strings.xml`：84 个 `permdesc_*`，但绝大多数是 Settings 的按钮文案
- AOSP 老分支（7.1/9/11/13）：对应路径下取不到 permdesc
- `developer.android.com`（主站）：被墙
- Android SDK 仓库（`repository2-3.xml`）：没有 docs 包，只有 `sources;android-XX`
- 本机 MobSF 容器：只有被扫 APK 的 smali，无权限说明库

官方文档覆盖 365 个权限常量（另有约 650 个是 `@hide`、文档未收录）。
