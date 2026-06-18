"""A small loan-calculation module used as the Task 2 demo target.

Deliberately mixes documented and undocumented functions/methods so the
docstring-audit task has real work to do.
"""
from __future__ import annotations


def calculate_emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Returns the equated monthly instalment for a loan.

    Uses the standard amortising-loan formula. `annual_rate_pct` is the
    nominal annual interest rate as a percentage (e.g. 8.5, not 0.085).
    """
    if months <= 0:
        raise ValueError("months must be positive")
    monthly_rate = annual_rate_pct / 100 / 12
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def total_interest(principal: float, emi: float, months: int) -> float:
    """TODO: document this function."""
    return emi * months - principal


def amortisation_schedule(principal, annual_rate_pct, months):
    """TODO: document this function."""
    monthly_rate = annual_rate_pct / 100 / 12
    emi = calculate_emi(principal, annual_rate_pct, months)
    balance = principal
    rows = []
    for month in range(1, months + 1):
        interest = balance * monthly_rate
        principal_paid = emi - interest
        balance -= principal_paid
        rows.append((month, round(emi, 2), round(interest, 2), round(principal_paid, 2), round(max(balance, 0), 2)))
    return rows


class LoanSummary:
    """Holds the headline numbers for a single loan and formats them
    for display."""

    def __init__(self, principal: float, annual_rate_pct: float, months: int):
        """TODO: document this function."""
        self.principal = principal
        self.annual_rate_pct = annual_rate_pct
        self.months = months
        self.emi = calculate_emi(principal, annual_rate_pct, months)

    def summary_line(self) -> str:
        """Returns a single human-readable summary line."""
        return f"EMI for {self.principal:,.0f} @ {self.annual_rate_pct}% over {self.months}mo: {self.emi:,.2f}"

    def total_payable(self):
        """TODO: document this function."""
        return self.emi * self.months

    def total_interest(self):
        """TODO: document this function."""
        return total_interest(self.principal, self.emi, self.months)


if __name__ == "__main__":
    loan = LoanSummary(5_000_000, 8.5, 12)
    print(loan.summary_line())
