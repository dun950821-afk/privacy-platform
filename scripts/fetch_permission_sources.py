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

# 仓库内的人工整理文件：一样是「重建输入」，必须登记进清单，否则只跑这个脚本 +
# `import_permissions.py` 复现不出活库（人工判定的字段会整批丢失）。
# 它们没有可抓的 URL，所以**不放进 SOURCES**——抓取循环碰不到；由 _repo_entries()
# 按磁盘内容算 sha256 后追加。注意本脚本是**整份重写** SOURCES.json 的：
# 这条登记必须在这里显式重建，手动往 JSON 里加一条会在下次抓取时被无声抹掉。
REPO_SOURCES = [
    {"platform": "android",
     "file": "curated_permission_snapshot.tsv",
     "path": "data/kb/curated_permission_snapshot.tsv",
     "url": "repo://data/kb/curated_permission_snapshot.tsv",
     "source_kind": "repo"},
]


def _repo_entries() -> list[dict]:
    """仓库内文件的清单条目。`sha256`/`bytes` 由磁盘内容算，和抓来的条目一样可校验。

    `path` 是相对仓库根的路径——快照不在 `data/kb/<platform>/` 下，不能按抓取条目的
    `platform/file` 拼路径去猜。
    """
    entries = []
    for item in REPO_SOURCES:
        path = ROOT.parent.parent / item["path"]
        if not path.exists():
            raise SystemExit(f"清单里的仓库内文件 {item['path']} 不存在——先把它加回仓库")
        body = path.read_bytes()
        entries.append({**item, "sha256": hashlib.sha256(body).hexdigest(),
                        "bytes": len(body)})
    return entries


def _load_previous(manifest_path: pathlib.Path) -> dict[tuple[str, str], dict]:
    """上一轮清单，按 (platform, file) 索引。

    失败时要把上一次的 sha256/bytes/fetched_at **沿用**下来：抓不到不等于磁盘上那份
    变坏了——脚本从不删旧文件，失败条目若写 `sha256: null`，清单就会声称「源文件不可验证」，
    而磁盘上那份其实好端端在。这样清单和仓库里的实际内容会脱节，下载类失败还特别常见
    （实测 AOSP 清单就偶发读超时）。
    """
    if not manifest_path.exists():
        return {}
    try:
        return {(m["platform"], m["file"]): m for m in json.loads(
            manifest_path.read_text(encoding="utf-8"))}
    except (ValueError, KeyError, TypeError):
        return {}


def main():
    manifest_path = ROOT / "SOURCES.json"
    previous = _load_previous(manifest_path)
    manifest = []
    for platform, filename, url, headers in SOURCES:
        target = ROOT / platform / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        prev = previous.get((platform, filename)) or {}
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", **headers})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
        except Exception as exc:                      # 抓不到就记下来，不静默跳过
            print(f"  FAILED {platform}/{filename}: {exc}")
            manifest.append({"platform": platform, "file": filename, "url": url,
                             # 沿用上一轮的三项：文件没被删，它还是好的
                             "fetched_at": prev.get("fetched_at"),
                             "sha256": prev.get("sha256"),
                             "bytes": prev.get("bytes"),
                             "error": str(exc)})
            continue
        digest = hashlib.sha256(body).hexdigest()
        # 字节没变就沿用上一轮的 fetched_at：`fetched_at` 记的是**内容何时到手**，
        # 不是「脚本何时跑过」。否则每次重抓都会让清单产生一堆无意义的 diff。
        unchanged = prev.get("sha256") == digest
        target.write_bytes(body)
        manifest.append({"platform": platform, "file": filename, "url": url,
                         "fetched_at": prev.get("fetched_at") if unchanged
                         else time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                         "sha256": digest,
                         "bytes": len(body)})
        print(f"  ok {platform}/{filename} {len(body)} bytes"
              + ("（内容未变）" if unchanged else ""))

    for item in _repo_entries():
        manifest.append(item)
        print(f"  repo {item['path']} {item['bytes']} bytes（仓库内文件，不抓取）")

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [m for m in manifest if m.get("error")]
    print(f"\n抓取完成 {len(manifest) - len(failed)}/{len(manifest)}；失败 {len(failed)} 条")


if __name__ == "__main__":
    main()
