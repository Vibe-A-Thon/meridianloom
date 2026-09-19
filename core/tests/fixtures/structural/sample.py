class Ledger:
    def __init__(self, entries):
        self.entries = list(entries)

    def total(self):
        return sum(self.entries)


def main():
    ledger = Ledger([1, 2, 3])
    print(ledger.total())
