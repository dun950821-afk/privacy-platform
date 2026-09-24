"""Finding baseline 状态判定。"""


def baseline_state(previous: dict | None, current: dict) -> str:
    if not previous:
        return "new"
    if previous.get("dedup_key") == current.get("dedup_key"):
        return "unchanged"
    return "changed"
