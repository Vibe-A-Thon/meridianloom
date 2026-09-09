"""Payments: depends on the ledger (fixture)."""

import ledger


class PaymentProcessor:
    """Wraps the ledger; imported by report."""

    def __init__(self, book: "ledger.Ledger") -> None:
        self.book = book

    def charge(self, name: str, amount: int) -> None:
        self.book.record(name, amount)
