package com.acme.core;

import java.util.ArrayList;
import java.util.List;

public class Ledger {
    private final List<Integer> entries = new ArrayList<>();

    public void record(int amount) {
        entries.add(amount);
    }

    public int total() {
        return entries.stream().mapToInt(Integer::intValue).sum();
    }
}
