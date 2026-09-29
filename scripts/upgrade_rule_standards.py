# scripts/upgrade_rule_standards.py
"""把规则库的 `standards` 块同步到种子里的值。默认干跑，`--apply` 才写库。

## 为什么需要这个脚本

`backend/app/seed.py` 与 `services/rule_seed.py` 都是**只在 rule_key 不存在时插入**
（`if not existing:` / `if ... .first(): continue`）。也就是说，改种子代码只对新装生效，
已有的开发库里那 12 行**一个字节都不会动**。种子改了而库没改，是「代码里已经修好、
界面上还是错的」这类最难发现的不一致——所以升级得有一条明确的路径，不能靠重跑种子。

## 只动 standards，不动别的

规则内容会逐字进 `platform_findings`，改 `match`/`produce` 等于改结论语义。本次要修的是
**标准编号挂错**（`MASWE-0001` 讲的是落盘加密，不是通讯录外传；`MASTG-TEST-PRIVACY-1`
在 MASTG 里根本不存在）。所以这里只写 `standards` 这一个键，其余键原样带过去。

## 不覆写历史版本

规则内容是版本化资产，历史 Finding 的 `rule_version_id` 指着旧版本——旧版本必须留着，
否则「这条结论当时是按什么规则判的」就查不出来了。所以改法是**新开一个版本**并把
`current_version_id` 指过去，不是改旧行。

用 `--apply` 跑第二遍不会重复升版本：比的是「当前版本的 standards 与种子是否一致」，
一致就跳过。
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import text                                  # noqa: E402

from app.core.database import SessionLocal                   # noqa: E402
from app.models import Rule, RuleVersion                     # noqa: E402
from app.seed import SEED_RULES                              # noqa: E402
from app.services.rule_evaluator import validate_rule_content  # noqa: E402
from app.services.rule_seed import BUILTIN_CORRELATION_RULES   # noqa: E402

CHANGELOG = (
    "修正 standards 标准编号：原引用 MASWE-0001（实为 MASVS-STORAGE 的"
    "「敏感数据未加密落盘」，与本规则无关）与 MASTG-TEST-PRIVACY-1（MASTG 中不存在，"
    "稳定版无隐私测试、beta 版编号形如 MASTG-TEST-0206）。编号已对 OWASP/maswe 与 "
    "OWASP/owasp-mastg 仓库原文逐条核实。"
)


def _desired_standards() -> dict[str, dict]:
    """rule_key -> 种子里的 standards。两个种子文件是唯一事实源，这里不另抄一份。"""
    desired = {}
    for item in SEED_RULES:
        standards = (item["rule_content"] or {}).get("standards")
        if standards is not None:
            desired[item["rule_key"]] = standards
    for item in BUILTIN_CORRELATION_RULES:
        standards = (item["content"] or {}).get("standards")
        if standards is not None:
            desired[item["rule_key"]] = standards
    return desired


def _next_version(existing: list[str]) -> str:
    """按 `主.次` 递增次位。版本号不是语义化版本，取的是「当前最大次位 +1」。"""
    majors, minors = [], []
    for v in existing:
        head, _, tail = str(v).partition(".")
        try:
            majors.append(int(head))
            minors.append(int(tail or 0))
        except ValueError:
            # 版本号里混进非数字（如 `1.0-rc`）时不去猜：报错让人来处理，
            # 静默生成一个可能重号的版本会让下面那次 UNIQUE(rule_id, version) 报错。
            raise SystemExit(f"版本号无法解析为 主.次 形式: {v!r}")
    if not majors:
        return "1.0"
    top = max(majors)
    return f"{top}.{max(m for m, j in zip(minors, majors) if j == top) + 1}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="真正写库。不给这个开关时只报告将要做的改动")
    args = parser.parse_args()

    desired = _desired_standards()
    db = SessionLocal()
    try:
        changed = skipped = missing = 0
        for rule_key, want in sorted(desired.items()):
            rule = db.query(Rule).filter(Rule.rule_key == rule_key).first()
            if not rule:
                # 种子里有、库里没有：那是 seed 的活（新装/新增规则），不是本脚本的。
                print(f"  跳过 {rule_key}：库里没有这条规则，交给 seed 创建")
                missing += 1
                continue

            versions = (db.query(RuleVersion)
                        .filter(RuleVersion.rule_id == rule.id)
                        .order_by(RuleVersion.created_at).all())
            current = next((v for v in versions if v.id == rule.current_version_id), None)
            if current is None:
                raise SystemExit(f"{rule_key} 的 current_version_id 指向不存在的版本，先修数据")

            have = (current.rule_content or {}).get("standards")
            if have == want:
                print(f"  已一致 {rule_key}（当前 v{current.version}）")
                skipped += 1
                continue

            new_version = _next_version([v.version for v in versions])
            # 只换 standards 一个键。深拷贝一层就够：standards 是本脚本自己造的新对象，
            # 其余键都是只读带过去，不会被后续改动牵连。
            content = dict(current.rule_content or {})
            content["standards"] = want

            # 关联规则走各自的校验（schema 1.0/2.0 都认）；那 10 条判定规则用的是
            # `when` DSL，不在校验器支持范围内，跳过——它们本来也不参与求值，
            # 不校验不会让任何东西从「能跑」变成「跑不了」。
            if rule.category == "correlation":
                validate_rule_content(content)

            print(f"  {'[写]' if args.apply else '[干跑]'} {rule_key}："
                  f"v{current.version} -> v{new_version}")
            print(f"        旧 {have}")
            print(f"        新 {want}")
            if not args.apply:
                changed += 1
                continue

            stamp = db.execute(text("select now()")).scalar()
            rv = RuleVersion(rule_id=rule.id, version=new_version, rule_content=content,
                             changelog=CHANGELOG, status="published", published_at=stamp)
            db.add(rv)
            db.flush()
            rule.current_version_id = rv.id
            changed += 1

        if args.apply:
            db.commit()
        print(f"\n{'已升级' if args.apply else '待升级'} {changed} 条，"
              f"已一致 {skipped} 条，库中缺失 {missing} 条")
        if not args.apply and changed:
            print("这是干跑，未写库。确认无误后加 --apply 重跑。")
    finally:
        db.close()


if __name__ == "__main__":
    main()
