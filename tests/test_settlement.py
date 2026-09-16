"""Unit tests for the greedy settlement algorithm."""
from decimal import Decimal
from app.services.settlement import (
    compute_fair_share,
    compute_balances,
    greedy_settlement,
    Settlement,
)


def test_fair_share():
    assert compute_fair_share(Decimal("1000"), 4) == Decimal("250.00")
    assert compute_fair_share(Decimal("100"), 3) == Decimal("33.33")
    assert compute_fair_share(Decimal("100"), 0) == Decimal("0.00")


def test_balances_zero():
    members = [
        {"id": 1, "name": "A", "total_paid": Decimal("250")},
        {"id": 2, "name": "B", "total_paid": Decimal("250")},
    ]
    fair = Decimal("250.00")
    balances = compute_balances(members, fair)
    assert all(b["balance"] == Decimal("0.00") for b in balances)
    assert greedy_settlement(balances) == []


def test_settlement_simple():
    """A paid 0, B paid 1000, fair share 500 each → A pays 500 to B."""
    members = [
        {"id": 1, "name": "Rahul", "total_paid": Decimal("0")},
        {"id": 2, "name": "Priya", "total_paid": Decimal("1000")},
    ]
    fair = Decimal("500.00")
    balances = compute_balances(members, fair)
    settlements = greedy_settlement(balances)
    assert len(settlements) == 1
    s = settlements[0]
    assert s.payer_name == "Rahul"
    assert s.receiver_name == "Priya"
    assert s.amount == Decimal("500.00")
    assert "Rahul pays ₹500.00 to Priya." in s.display()


def test_settlement_three_way():
    """
    Fair share 300.
    A paid 0 (owes 300), B paid 100 (owes 200), C paid 800 (receives 500).
    Expected: A pays 300 to C, B pays 200 to C.
    """
    members = [
        {"id": 1, "name": "A", "total_paid": Decimal("0")},
        {"id": 2, "name": "B", "total_paid": Decimal("100")},
        {"id": 3, "name": "C", "total_paid": Decimal("800")},
    ]
    fair = Decimal("300.00")
    balances = compute_balances(members, fair)
    settlements = greedy_settlement(balances)
    total_transferred = sum(s.amount for s in settlements)
    assert total_transferred == Decimal("500.00")
    # All debtors should be settled
    assert len(settlements) >= 1
    payers = {s.payer_name for s in settlements}
    assert "A" in payers
    assert "B" in payers
    receivers = {s.receiver_name for s in settlements}
    assert "C" in receivers


def test_overpayment_and_partial():
    members = [
        {"id": 1, "name": "X", "total_paid": Decimal("50")},   # owes 150
        {"id": 2, "name": "Y", "total_paid": Decimal("350")},  # receives 150
    ]
    fair = Decimal("200.00")
    balances = compute_balances(members, fair)
    assert balances[0]["balance"] == Decimal("-150.00")
    assert balances[1]["balance"] == Decimal("150.00")
    settlements = greedy_settlement(balances)
    assert len(settlements) == 1
    assert settlements[0].amount == Decimal("150.00")
