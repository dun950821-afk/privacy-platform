import json
from pathlib import Path
import pytest

from app.services.rule_evaluator import evaluate_rule
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

FIXTURES = Path(__file__).parent / "fixtures" / "correlation"


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_positive_fixture_matches(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "positive.json").read_text())
    assert evaluate_rule(rule["content"], observations) is not None


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_negative_fixture_does_not_match(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "negative.json").read_text())
    assert evaluate_rule(rule["content"], observations) is None
