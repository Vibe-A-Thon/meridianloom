//! Canonical JSON writer — byte-compatible with
//! `core/meridian_core/ledger/canonical.py` and `verifier/verify.py`.
//!
//! Rules (normative; docs/open-ledger-spec/ is the human-readable version):
//! UTF-8 JSON, object keys sorted lexicographically by Unicode code point,
//! no insignificant whitespace, `null`/`true`/`false` lowercase, integers as
//! decimal digits, and floats rendered with CPython's `repr` shortest-round-
//! trip algorithm — including its fixed-vs-scientific thresholds (scientific
//! when the decimal point position is <= -4 or > 16) and two-digit exponents.
//! Non-finite floats are an error (the ledger refuses NaN/Infinity outright).

use serde_json::Value;

#[derive(Debug)]
pub struct CanonicalError(pub String);

impl std::fmt::Display for CanonicalError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

/// Canonical JSON bytes for `value`.
pub fn canonical_json(value: &Value) -> Result<Vec<u8>, CanonicalError> {
    let mut out = Vec::new();
    write_value(&mut out, value)?;
    Ok(out)
}

fn write_value(out: &mut Vec<u8>, value: &Value) -> Result<(), CanonicalError> {
    match value {
        Value::Null => out.extend_from_slice(b"null"),
        Value::Bool(true) => out.extend_from_slice(b"true"),
        Value::Bool(false) => out.extend_from_slice(b"false"),
        Value::Number(number) => {
            if let Some(int) = number.as_i64() {
                out.extend_from_slice(int.to_string().as_bytes());
            } else if let Some(uint) = number.as_u64() {
                out.extend_from_slice(uint.to_string().as_bytes());
            } else if let Some(float) = number.as_f64() {
                write_float(out, float)?;
            } else {
                return Err(CanonicalError("number is not representable".into()));
            }
        }
        Value::String(text) => write_string(out, text),
        Value::Array(items) => {
            out.push(b'[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_value(out, item)?;
            }
            out.push(b']');
        }
        Value::Object(map) => {
            // Byte order on UTF-8 equals Unicode code-point order, which is
            // exactly how Python sorts str keys.
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push(b'{');
            for (index, key) in keys.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_string(out, key);
                out.push(b':');
                write_value(out, &map[*key])?;
            }
            out.push(b'}');
        }
    }
    Ok(())
}

/// JSON string escaping per Python `json.dumps` with `ensure_ascii=False`:
/// control characters use the short escapes or `\u00xx` (lowercase hex);
/// everything else — including non-ASCII — is raw UTF-8.
fn write_string(out: &mut Vec<u8>, text: &str) {
    out.push(b'"');
    for character in text.chars() {
        match character {
            '"' => out.extend_from_slice(b"\\\""),
            '\\' => out.extend_from_slice(b"\\\\"),
            '\n' => out.extend_from_slice(b"\\n"),
            '\r' => out.extend_from_slice(b"\\r"),
            '\t' => out.extend_from_slice(b"\\t"),
            '\u{0008}' => out.extend_from_slice(b"\\b"),
            '\u{000C}' => out.extend_from_slice(b"\\f"),
            c if (c as u32) < 0x20 => {
                out.extend_from_slice(format!("\\u{:04x}", c as u32).as_bytes());
            }
            c => {
                let mut buffer = [0u8; 4];
                out.extend_from_slice(c.encode_utf8(&mut buffer).as_bytes());
            }
        }
    }
    out.push(b'"');
}

/// CPython `repr(float)` shortest-round-trip rendering.
///
/// Rust's `{:e}` formatter already produces the shortest round-tripping
/// mantissa; we re-render it with Python's notation rules: `digits` and
/// `decpt` satisfy `value = 0.digits × 10^decpt`. Scientific notation is
/// used when `decpt <= -4` or `decpt > 16`, with a signed, at-least-two-digit
/// exponent; integral values in fixed notation carry a trailing `.0`.
fn write_float(out: &mut Vec<u8>, float: f64) -> Result<(), CanonicalError> {
    if !float.is_finite() {
        return Err(CanonicalError(
            "non-finite float is not canonically serializable".into(),
        ));
    }
    if float == 0.0 {
        out.extend_from_slice(if float.is_sign_negative() {
            b"-0.0"
        } else {
            b"0.0"
        });
        return Ok(());
    }
    let scientific = format!("{:e}", float); // e.g. "-1.2345e-7", "1e16"
    let (mantissa, exponent) = scientific
        .split_once('e')
        .ok_or_else(|| CanonicalError("unexpected float formatting".into()))?;
    let exponent: i32 = exponent
        .parse()
        .map_err(|_| CanonicalError("unexpected float exponent".into()))?;
    let negative = mantissa.starts_with('-');
    let digits: String = mantissa.chars().filter(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() {
        return Err(CanonicalError("unexpected float mantissa".into()));
    }
    let decpt = exponent + 1;
    if negative {
        out.push(b'-');
    }
    if decpt <= -4 || decpt > 16 {
        // Scientific: d[.ddd]e±XX
        out.push(digits.as_bytes()[0]);
        if digits.len() > 1 {
            out.push(b'.');
            out.extend_from_slice(&digits.as_bytes()[1..]);
        }
        let point = decpt - 1;
        if point < 0 {
            out.extend_from_slice(b"e-");
        } else {
            out.extend_from_slice(b"e+");
        }
        out.extend_from_slice(format!("{:02}", point.abs()).as_bytes());
    } else if decpt <= 0 {
        out.extend_from_slice(b"0.");
        for _ in 0..(-decpt) {
            out.push(b'0');
        }
        out.extend_from_slice(digits.as_bytes());
    } else if decpt as usize >= digits.len() {
        out.extend_from_slice(digits.as_bytes());
        for _ in 0..(decpt as usize - digits.len()) {
            out.push(b'0');
        }
        out.extend_from_slice(b".0");
    } else {
        out.extend_from_slice(&digits.as_bytes()[..decpt as usize]);
        out.push(b'.');
        out.extend_from_slice(&digits.as_bytes()[decpt as usize..]);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn canon(text: &str) -> String {
        let value: Value = serde_json::from_str(text).unwrap();
        String::from_utf8(canonical_json(&value).unwrap()).unwrap()
    }

    #[test]
    fn floats_match_python_repr() {
        // Vectors generated from CPython 3.11 json.dumps(..., sort_keys,
        // separators, ensure_ascii=False); see docs/open-ledger-spec/.
        let cases = [
            ("0.01", "0.01"),
            ("0.5", "0.5"),
            ("1e16", "1e+16"),
            ("1e-5", "1e-05"),
            ("0.0001", "0.0001"),
            ("0.30000000000000004", "0.30000000000000004"),
            ("-0.0", "-0.0"),
            ("1234567890123456.0", "1234567890123456.0"),
            ("5e-324", "5e-324"),
            ("1.5e-7", "1.5e-07"),
            ("2.5", "2.5"),
            ("100.0", "100.0"),
            ("1e15", "1000000000000000.0"),
            ("-1234.5678", "-1234.5678"),
            ("42.0", "42.0"),
            ("1.0", "1.0"),
            ("0.001", "0.001"),
        ];
        for (input, expected) in cases {
            assert_eq!(canon(input), expected, "float {input}");
        }
    }

    #[test]
    fn integers_stay_integers() {
        assert_eq!(canon("42"), "42");
        assert_eq!(canon("-7"), "-7");
        assert_eq!(canon("18446744073709551615"), "18446744073709551615");
    }

    #[test]
    fn objects_sort_keys_and_escape_strings() {
        // Python: json.dumps({"b":1,"a":"é\x01\"","A":None}, sort_keys=True,
        // separators=(",",":"), ensure_ascii=False)
        assert_eq!(
            canon("{\"b\": 1, \"a\": \"é\\u0001\\\"\", \"A\": null}"),
            "{\"A\":null,\"a\":\"é\\u0001\\\"\",\"b\":1}"
        );
    }

    #[test]
    fn nested_compact_no_whitespace() {
        assert_eq!(
            canon("{ \"x\" : [ 1, true, null, { \"y\": 2.5 } ] }"),
            "{\"x\":[1,true,null,{\"y\":2.5}]}"
        );
    }

    #[test]
    fn non_finite_floats_never_arrive_from_json() {
        // serde_json refuses out-of-range literals and maps explicit NaN
        // constructors to null, so the canonical writer's non-finite guard
        // is defence in depth for programmatically-built values only.
        assert!(serde_json::from_str::<Value>("1e999").is_err());
        assert_eq!(
            canonical_json(&serde_json::from_str::<Value>("null").unwrap()).unwrap(),
            b"null"
        );
        // serde_json::Value cannot even hold a non-finite float (From<f64>
        // maps it to null), so the writer's is_finite guard is unreachable
        // through parsed bundles — kept as defence in depth.
        assert_eq!(Value::from(f64::NAN), Value::Null);
    }
}
