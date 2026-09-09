package com.acme.core;

import com.acme.core.Ledger;

public class PaymentService {
    private final Ledger ledger;

    public PaymentService(Ledger ledger) {
        this.ledger = ledger;
    }

    public void charge(int amount) {
        ledger.record(amount);
    }
}
