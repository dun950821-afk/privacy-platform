# scripts/fetch_permission_sources.py
"""把三个平台的权限来源抓到 data/kb/。

联网只发生在这里。导入脚本读本地文件，所以数据能从零重建、且复现不依赖网络。

注意：raw.githubusercontent.com 上 openharmony/docs 实测拉不动（60s 超时），
走 GitHub API 的 Accept: application/vnd.github.raw 头可以。AOSP 的走 raw 没问题。
"""
import hashlib
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"
GH_API_RAW = {"Accept": "application/vnd.github.raw"}

SOURCES = [
    ("android", "AndroidManifest.xml",
     "https://raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/master/core/res/AndroidManifest.xml", {}),
    ("harmonyos", "permissions-for-all.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-all.md", GH_API_RAW),
    ("harmonyos", "permissions-for-all-user.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-all-user.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps-no-acl.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps-no-acl.md", GH_API_RAW),
    ("harmonyos", "permissions-for-system-apps-user.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-system-apps-user.md", GH_API_RAW),
    ("harmonyos", "permissions-for-enterprise-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-enterprise-apps.md", GH_API_RAW),
    ("harmonyos", "permissions-for-mdm-apps.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/permissions-for-mdm-apps.md", GH_API_RAW),
    ("harmonyos", "restricted-permissions.md",
     "https://api.github.com/repos/openharmony/docs/contents/zh-cn/application-dev/security/AccessToken/restricted-permissions.md", GH_API_RAW),
    ("ios", "protected-resources.json",
     "https://developer.apple.com/tutorials/data/documentation/bundleresources/protected-resources.json", {}),
]


def main():
    manifest = []
    for platform, filename, url, headers in SOURCES:
        target = ROOT / platform / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
        except Exception as exc:                      # 抓不到就记下来，不静默跳过
            print(f"  FAILED {platform}/{filename}: {exc}")
            manifest.append({"platform": platform, "file": filename, "url": url,
                             "fetched_at": None, "sha256": None, "error": str(exc)})
            continue
        target.write_bytes(body)
        manifest.append({"platform": platform, "file": filename, "url": url,
                         "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         "sha256": hashlib.sha256(body).hexdigest(),
                         "bytes": len(body)})
        print(f"  ok {platform}/{filename} {len(body)} bytes")

    (ROOT / "SOURCES.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [m for m in manifest if m.get("error")]
    print(f"\n抓取完成 {len(manifest) - len(failed)}/{len(manifest)}；失败 {len(failed)} 条")


if __name__ == "__main__":
    main()
