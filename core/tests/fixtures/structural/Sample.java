package com.example.payments;

public class PaymentController {
    private final Ledger ledger;

    public PaymentController(Ledger ledger) {
        this.ledger = ledger;
    }

    public Receipt submit(Order order) {
        validate(order);
        Receipt receipt = charge(order);
        return receipt;
    }

    static class Defaults {
        static Receipt emptyReceipt() {
            return Receipt.NONE;
        }
    }
}
