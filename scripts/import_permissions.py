# scripts/import_permissions.py
"""读 data/kb/ 的原始文件，解析后导入知识库。不联网。"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import SessionLocal                     # noqa: E402
from app.services.permission_import import import_platform      # noqa: E402
from app.services.permission_sources import (                   # noqa: E402
    parse_android_manifest, parse_harmonyos_doc, parse_ios_protected_resources,
)

KB = pathlib.Path(__file__).resolve().parent.parent / "data" / "kb"


def _load(platform):
    if platform == "ANDROID":
        return parse_android_manifest((KB / "android" / "AndroidManifest.xml").read_text(encoding="utf-8"))
    if platform == "HARMONYOS":
        rows, seen = [], set()
        for f in sorted((KB / "harmonyos").glob("permissions-for-*.md")) + \
                 sorted((KB / "harmonyos").glob("restricted-permissions.md")):
            file_rows = parse_harmonyos_doc(f.read_text(encoding="utf-8"))
            if not file_rows:
                # 单文件 0 条不会拖垮「每平台 > 0」的总断言（其余 7 个文件照样有几百条），
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


def main():
    db = SessionLocal()
    try:
        for platform in ("ANDROID", "HARMONYOS", "IOS"):
            rows = _load(platform)
            # **解析条数非零是硬断言。** 三个解析器都完全依赖文档的标题形态（鸿蒙那边是
            # `## ohos.permission.X`）；真实文档若换了层级，解析器会**静默返回空列表而不报错**，
            # 空的导入结果与「文档干净」在日志里长得一模一样。宁可在这里炸掉。
            if not rows:
                raise SystemExit(f"{platform} 解析出 0 条——文档形态可能变了，先查解析器再导入，别让空结果落库")
            result = import_platform(db, platform, rows)
            print(f"{platform:10s} 解析 {len(rows):5d} 条  ->  {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
