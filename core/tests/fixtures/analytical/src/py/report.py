"""Report: depends on payments (fixture)."""

from payments import PaymentProcessor


def build_report(processor: PaymentProcessor) -> str:
    return f"entries: {len(processor.book.entries)}"
