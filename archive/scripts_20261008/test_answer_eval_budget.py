"""평가 비용 보호가 호출 전에 멈추고 실패 예약을 보존하는지 확인한다."""
import json
from types import SimpleNamespace

import pytest

from scripts.answer_eval_budget import Budget, BudgetStop, config


def test_budget_refuses_request_before_spending(tmp_path):
    budget = Budget(0.01, tmp_path / "usage.json")
    with pytest.raises(BudgetStop):
        budget.reserve(config.ANSWER_MODEL, 1000)
    assert budget.spent == 0
    assert not budget.events


def test_success_releases_unused_reservation(tmp_path):
    budget = Budget(0.50, tmp_path / "usage.json")
    event = budget.reserve(config.ANSWER_MODEL, 1000)
    assert budget.spent > 0.06
    budget.settle(event, SimpleNamespace(prompt_tokens=100, completion_tokens=200))
    assert budget.spent == pytest.approx(0.00011)
    saved = json.loads(budget.log_path.read_text(encoding="utf-8"))
    assert saved["events"][0]["calculated_usd"] == pytest.approx(0.00011)


def test_failed_request_keeps_reservation_and_blocks_followup(tmp_path):
    budget = Budget(0.50, tmp_path / "usage.json")
    event = budget.reserve(config.ANSWER_MODEL, 1000)
    reserved = budget.spent
    budget.fail(event, RuntimeError("키가 포함됐을 수 있는 원문"))
    assert budget.spent == reserved
    with pytest.raises(BudgetStop):
        budget.reserve(config.JUDGE_MODEL, 100)
    assert "원문" not in budget.log_path.read_text(encoding="utf-8")


def test_missing_usage_keeps_reservation_and_stops(tmp_path):
    budget = Budget(0.50, tmp_path / "usage.json")
    event = budget.reserve(config.EMBED_MODEL, 1000)
    reserved = budget.spent
    with pytest.raises(BudgetStop):
        budget.settle(event, None)
    assert budget.spent == reserved
    assert budget.blocked
