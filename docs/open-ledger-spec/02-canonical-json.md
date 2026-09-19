# 2. Canonical JSON — the byte rules every hash relies on

Every hash in this specification (§3 entry hashes, §5 tree-head messages, §7
bundle digest) is taken over **canonical JSON bytes**. Two implementations
that both apply these rules to the same data MUST produce byte-identical
output; one byte of difference invalidates the hash.

## 2.1 Rules

A canonical encoder MUST emit, for a JSON value:

- **Objects**: keys sorted lexicographically by Unicode code point
  (UTF-8 byte order is equivalent and MAY be used), no whitespace around the
  colon, entries joined by `,` without spaces, wrapped in `{}`.
- **Arrays**: items joined by `,` without spaces, wrapped in `[]`.
- **Strings**: UTF-8, no ASCII escaping of non-ASCII characters
  (`ensure_ascii=False` semantics). Only `"` → `\"`, `\` → `\\`, the short
  escapes `\n` `\r` `\t` `\b` `\f`, and `\u00xx` (lowercase hex) for other
  control characters below U+0020, are escaped.
- **Integers**: decimal digits, no leading zeros, leading `-` for negatives.
  (JSON-native integers; arbitrary magnitude.)
- **Booleans and null**: `true`, `false`, `null`.
- **No insignificant whitespace anywhere.** NaN and ±Infinity MUST be
  refused outright (they have no canonical spelling).

Python reference (exactly what the ledger runs):

```python
json.dumps(value, sort_keys=True, separators=(",", ":"),
           ensure_ascii=False, allow_nan=False).encode("utf-8")
```

## 2.2 The float caveat (normative)

Floats are rendered with **CPython's `repr` shortest-round-trip rule**: the
shortest decimal string that round-trips to the same IEEE-754 double, then
formatted with these thresholds — let `digits` be the shortest significant
digits and `decpt` the decimal-point position (value = `0.digits × 10^decpt`):

- **Scientific notation when `decpt <= -4` or `decpt > 16`**, spelled
  `d[.ddd]e±XX` with a sign and **at least two exponent digits**
  (`1e+16`, `1.5e-07`, `5e-324`).
- **Fixed notation otherwise**, with a trailing `.0` when integral
  (`0.01`, `100.0`, `1234567890123456.0`, `-0.0`, `0.0001`).
- Negative zero is `-0.0`.

This is *not* what most JSON encoders emit (`serde_json`, Go, JS differ in
exponent formatting and thresholds), and it is the single most likely cause
of an independent verifier disagreeing with the ledger. A non-Python
verifier MUST reimplement this rendering, not call its language's default
float formatter. Worked vectors (CPython 3.11, normative):

| Value | Canonical spelling |
|---|---|
| `0.01` | `0.01` |
| `0.5` | `0.5` |
| `2.5` | `2.5` |
| `42.0` | `42.0` |
| `100.0` | `100.0` |
| `1e15` | `1000000000000000.0` |
| `1e16` | `1e+16` |
| `1e-4` | `0.0001` |
| `1e-5` | `1e-05` |
| `1.5e-7` | `1.5e-07` |
| `5e-324` | `5e-324` |
| `0.30000000000000004` | `0.30000000000000004` |
| `-1234.5678` | `-1234.5678` |
| `-0.0` | `-0.0` |
| `1234567890123456.0` | `1234567890123456.0` |

> **Producer guidance.** Because float spelling is the fragile point,
> entries SHOULD keep `confidence` and `cost_usd` to short decimal values,
> and verifiers MUST treat a float that their shortest-round-trip
> implementation renders differently as an encoding error, not as tampering
> evidence. The reference verifiers' unit tests pin the table above.

## 2.3 Hash payloads and byte columns

The hashed payload of an entry is the **full column set minus `prev_hash`
and `entry_hash`** (§3). Columns stored as bytes (digests, the optional
`signature`) are hex-projected to lowercase hex *strings* before
canonicalization. Everything else passes through as its JSON-native value.

## 2.4 `tool_calls`

`tool_calls` is stored as the serialized JSON-array **text** produced by the
producer (`json.dumps(value, ensure_ascii=False)` with default separators —
note the spaces: `", "` between items and `": "` after keys). The hash
covers that exact stored string; a verifier never needs to re-parse or
re-serialize it, because bundles carry the entry's hash payload verbatim
(§7).
