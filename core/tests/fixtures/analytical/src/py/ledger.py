"""The ledger: core record keeping (fixture)."""


class Ledger:
    """Records entries; the root of the import graph fixture."""

    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []

    def record(self, name: str, amount: int) -> None:
        self.entries.append((name, amount))

    def total(self) -> int:
        return sum(amount for _, amount in self.entries)
