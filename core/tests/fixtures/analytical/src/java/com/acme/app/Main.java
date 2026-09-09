package com.acme.app;

import com.acme.core.PaymentService;

public class Main {
    public static void main(String[] args) {
        PaymentService service = new PaymentService(null);
        service.charge(0);
    }
}
