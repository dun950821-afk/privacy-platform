"""MASVS/MASWE/MASTG 标准映射和 Finding baseline。"""

MAS_MAPPINGS = {
    "PRIVACY_CONTACTS_NETWORK": {
        "masvs": ["MASVS-PRIVACY-1"],
        "maswe": ["MASWE-0001"],
        "mastg": ["MASTG-TEST-PRIVACY-1"],
    },
}


def apply_mas_mapping(finding: dict) -> dict:
    mapping = MAS_MAPPINGS.get(finding.get("finding_code"), {})
    finding = dict(finding)
    finding["masvs_controls"] = mapping.get("masvs", [])
    finding["maswe_ids"] = mapping.get("maswe", [])
    finding["mastg_test_ids"] = mapping.get("mastg", [])
    finding["schema_version"] = "1.0"
    return finding


def baseline_state(previous: dict | None, current: dict) -> str:
    if not previous:
        return "new"
    if previous.get("dedup_key") == current.get("dedup_key"):
        return "unchanged"
    return "changed"
