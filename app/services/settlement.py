"""Greedy settlement algorithm for GiftPool balances.

Members with negative balance (paid less than fair share) are debtors.
Members with positive balance (paid more than fair share) are creditors.
We match debtors to creditors until all balances are settled.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class Settlement:
    payer_name: str
    receiver_name: str
    amount: Decimal

    def display(self) -> str:
        return f"{self.payer_name} pays ₹{self.amount:.2f} to {self.receiver_name}."


def compute_fair_share(target_amount: Decimal, num_members: int) -> Decimal:
    """Equal contribution per member, rounded to 2 decimal places."""
    if num_members <= 0:
        return Decimal("0.00")
    return (target_amount / num_members).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def compute_balances(
    members: List[Dict[str, Any]],
    fair_share: Decimal,
) -> List[Dict[str, Any]]:
    """
    members: list of dicts with keys: id, name, total_paid (Decimal)
    Returns list with added keys: fair_share, balance, status
    balance = total_paid - fair_share
      > 0  => should receive money (creditor)
      < 0  => owes money (debtor)
      = 0  => settled
    """
    result = []
    for m in members:
        total_paid = Decimal(str(m["total_paid"])).quantize(Decimal("0.01"))
        balance = (total_paid - fair_share).quantize(Decimal("0.01"))
        if balance > 0:
            status = "Should receive"
        elif balance < 0:
            status = "Owes"
        else:
            status = "Settled"
        result.append(
            {
                **m,
                "fair_share": fair_share,
                "total_paid": total_paid,
                "balance": balance,
                "status": status,
            }
        )
    return result


def greedy_settlement(balances: List[Dict[str, Any]]) -> List[Settlement]:
    """
    Greedy algorithm:
    - Sort debtors (negative balance) by amount owed (most negative first)
    - Sort creditors (positive balance) by amount to receive (largest first)
    - Repeatedly match the largest debtor to the largest creditor
    - Round each transfer to 2 decimal places
    """
    debtors = [
        {"name": b["name"], "amount": abs(b["balance"])}
        for b in balances
        if b["balance"] < 0
    ]
    creditors = [
        {"name": b["name"], "amount": b["balance"]}
        for b in balances
        if b["balance"] > 0
    ]

    # Sort: largest obligation / receivable first
    debtors.sort(key=lambda x: x["amount"], reverse=True)
    creditors.sort(key=lambda x: x["amount"], reverse=True)

    settlements: List[Settlement] = []
    i, j = 0, 0

    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        transfer = min(debtor["amount"], creditor["amount"]).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if transfer > 0:
            settlements.append(
                Settlement(
                    payer_name=debtor["name"],
                    receiver_name=creditor["name"],
                    amount=transfer,
                )
            )
            debtor["amount"] -= transfer
            creditor["amount"] -= transfer

        if debtor["amount"] <= Decimal("0.00"):
            i += 1
        if creditor["amount"] <= Decimal("0.00"):
            j += 1

    return settlements
