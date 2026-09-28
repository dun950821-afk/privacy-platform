# scripts/import_permissions.py
"""读 data/kb/ 的原始文件，解析后导入知识库。不联网。"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                     # noqa: E402
from app.services.permission_import import import_platform      # noqa: E402
from app.services.permission_sources import (                   # noqa: E402
    parse_android_manifest, parse_harmonyos_doc, parse_ios_protected_resources,
)

KB = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"
PLATFORMS = ("ANDROID", "HARMONYOS", "IOS")


def _harmony_files():
    """鸿蒙源文件清单**从 SOURCES.json 派生**，导入侧不另维护一份。

    抓取脚本里已经有一份 `SOURCES`。导入侧若再写一套 glob 模式，新增一个名字对不上的
    鸿蒙源文件就会被**静默漏读**——而平台级「> 0」断言看不见（其余文件仍产数百条），
    正是 Ruling L 那类「少收」。清单以入仓的 SOURCES.json 为准，抓什么就导什么。
    """
    manifest = json.loads((KB / "SOURCES.json").read_text(encoding="utf-8"))
    files = [KB / m["platform"] / m["file"]
             for m in manifest if m.get("platform") == "harmonyos"]
    if not files:
        raise SystemExit("SOURCES.json 里没有任何 harmonyos 源文件——清单坏了，先查抓取脚本")
    return sorted(files)


def _load(platform):
    if platform == "ANDROID":
        return parse_android_manifest((KB / "android" / "AndroidManifest.xml").read_text(encoding="utf-8"))
    if platform == "HARMONYOS":
        rows, seen = [], set()
        for f in _harmony_files():
            if not f.exists():
                raise SystemExit(f"SOURCES.json 列了 {f.name}，但磁盘上没有——先跑抓取脚本")
            file_rows = parse_harmonyos_doc(f.read_text(encoding="utf-8"))
            if not file_rows:
                # 单文件 0 条不会拖垮「每平台 > 0」的总断言（其余文件照样有几百条），
                # 所以它必须自己出声，否则一份文档改版会被整批的平均数掩盖。
                print(f"  警告 {f.name} 解析出 0 条")
            for r in file_rows:
                if r["permission_name"] not in seen:        # 跨文件去重（同一权限可能出现在多个文件）
                    seen.add(r["permission_name"])
                    rows.append(r)
        return rows
    if platform == "IOS":
        return parse_ios_protected_resources((KB / "ios" / "protected-resources.json").read_text(encoding="utf-8"))
    raise ValueError(platform)


def _load_all():
    """三个平台全部解析完并断言非零，**在任何写库之前**。

    **解析条数非零是硬断言。** 三个解析器都完全依赖文档的标题形态（鸿蒙那边是
    `## ohos.permission.X`）；真实文档若换了层级，解析器会**静默返回空列表而不报错**，
    空的导入结果与「文档干净」在日志里长得一模一样。宁可在这里炸掉。

    与导入**分两趟**：交错着做的话，IOS 解析出 0 条时 ANDROID 与 HARMONYOS 已经写进库了。
    没有数据损坏（按平台各自事务、幂等），但守卫的自述目的是「坏解析不许进库」，
    那就该在任何写入之前中止。
    """
    loaded = []
    for platform in PLATFORMS:
        rows = _load(platform)
        if not rows:
            raise SystemExit(f"{platform} 解析出 0 条——文档形态可能变了，先查解析器再导入，别让空结果落库")
        print(f"{platform:10s} 解析 {len(rows):5d} 条")
        loaded.append((platform, rows))
    return loaded


def main():
    loaded = _load_all()
    db = SessionLocal()
    try:
        for platform, rows in loaded:
            result = import_platform(db, platform, rows)
            print(f"{platform:10s} ->  {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
