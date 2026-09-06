//! meridian-verify — the open reference verifier for Meridian audit bundles.
//!
//! FR-M36-06 / NFR-31 / SEC-29 (F0 Workstream E task 26): validates a bundle
//! produced by `ledger.exportBundle` with nothing but the bundle itself.
//! The check list is normative and identical to `verifier/verify.py`:
//!
//! 1. shape — the v1 schema fields decode (hex digests, base64 key);
//! 2. chain — every entry hash recomputes from its `hashPayload` under the
//!    canonical JSON rules, and entries link head-to-tail;
//! 3. inclusion — RFC 6962 §2.1.1 proofs anchor each entry into the Merkle
//!    tree the signed tree head commits to;
//! 4. tree head — the Ed25519 tree-head signature verifies against the
//!    public key bundled inside (no trust in Meridian's servers — SEC-29);
//! 5. signature — the bundle signature covers the canonical JSON of every
//!    other field, so any tampering anywhere is detected.

use std::collections::BTreeSet;

use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

pub mod canonical;
pub mod merkle;

/// Every problem found; an empty vector means the bundle verifies.
pub fn verify_bundle(bundle: &Value) -> Vec<String> {
    let mut problems: Vec<String> = Vec::new();

    if bundle.get("formatVersion") != Some(&json!(1)) {
        problems.push("formatVersion must be 1".into());
    }

    // -- shape: the bundled public key --------------------
    let mut public_key: Option<[u8; 32]> = None;
    let key_b64 = bundle.pointer("/signer/publicKey").and_then(Value::as_str);
    match key_b64 {
        None => problems.push("signer.publicKey is missing or not a string".into()),
        Some(text) => match base64_decode(text) {
            Err(_) => problems.push("signer.publicKey is not valid base64".into()),
            Ok(bytes) => {
                if bytes.len() != 32 {
                    problems.push("signer.publicKey must decode to 32 bytes".into());
                } else {
                    public_key = Some(bytes.try_into().unwrap());
                }
            }
        },
    }

    let entries = bundle
        .get("entries")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if bundle.get("entries").map(Value::is_array) != Some(true) {
        problems.push("entries must be an array".into());
    }

    // -- 2. chain continuity + per-entry hash recompute ----
    let mut previous_hash: Option<[u8; 32]> = None;
    for (position, entry) in entries.iter().enumerate() {
        let label = format!(
            "entry {}",
            entry.get("sequence").and_then(Value::as_i64).unwrap_or(position as i64)
        );
        let entry_hash = hex_bytes(entry.get("entryHash"), 32, &format!("{label}.entryHash"), &mut problems);
        let prev_hash = hex_bytes(
            entry.get("previousHash"),
            32,
            &format!("{label}.previousHash"),
            &mut problems,
        );
        let payload = entry.get("hashPayload");
        if payload.map(Value::is_object) != Some(true) {
            problems.push(format!("{label}: hashPayload must be an object"));
        }
        if let (Some(entry_hash), Some(prev_hash), Some(payload)) =
            (entry_hash, prev_hash, payload)
        {
            let mut preimage = prev_hash.to_vec();
            match canonical::canonical_json(payload) {
                Err(error) => problems.push(format!("{label}: {error}")),
                Ok(bytes) => {
                    preimage.extend_from_slice(&bytes);
                    if sha256(&preimage) != entry_hash {
                        problems.push(format!(
                            "{label}: entryHash does not match its content (hashPayload \
                             was tampered with, or the entry was altered)"
                        ));
                    }
                }
            }
        }
        if let (Some(prev_hash), Some(previous)) = (prev_hash, previous_hash) {
            if prev_hash != previous {
                problems.push(format!(
                    "{label}: chain link broken — previousHash does not match the \
                     preceding entry's entryHash"
                ));
            }
        }
        if let Some(entry_hash) = entry_hash {
            previous_hash = Some(entry_hash);
        }
    }

    // -- 3. inclusion proofs -------------------------------
    let tree_size = bundle.pointer("/proofs/treeSize").and_then(Value::as_u64);
    if tree_size.is_none() {
        problems.push("proofs.treeSize must be an integer".into());
    }
    let root_hex = bundle.pointer("/proofs/rootHash").and_then(Value::as_str);
    let root = hex_bytes(
        bundle.get("proofs").and_then(|p| p.get("rootHash")),
        32,
        "proofs.rootHash",
        &mut problems,
    );
    if root_hex.is_some() != root.is_some() && root_hex.is_none() {
        problems.push("proofs.rootHash is missing or not a string".into());
    }
    let inclusion = bundle
        .pointer("/proofs/inclusion")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    if bundle.pointer("/proofs/inclusion").map(Value::is_array) != Some(true) {
        problems.push("proofs.inclusion must be an array".into());
    }
    let by_sequence: std::collections::HashMap<i64, &Value> = entries
        .iter()
        .filter_map(|e| e.get("sequence").and_then(Value::as_i64).map(|s| (s, e)))
        .collect();
    let mut proven: BTreeSet<i64> = BTreeSet::new();
    for proof in &inclusion {
        let sequence = proof.get("sequence").and_then(Value::as_i64);
        let Some(sequence) = sequence else {
            problems.push("proofs.inclusion: item has no integer sequence".into());
            continue;
        };
        let Some(entry) = by_sequence.get(&sequence) else {
            problems.push(format!("proof for unknown sequence {sequence}"));
            continue;
        };
        proven.insert(sequence);
        let leaf_index = match proof.get("leafIndex").and_then(Value::as_u64) {
            Some(index) => index as usize,
            None => {
                problems.push(format!("proof {sequence}: leafIndex must be an integer"));
                usize::MAX
            }
        };
        let Some(path_hex) = proof.get("path").and_then(Value::as_array) else {
            problems.push(format!("proof {sequence}: path must be an array"));
            continue;
        };
        let mut path: Vec<[u8; 32]> = Vec::with_capacity(path_hex.len());
        let mut path_ok = true;
        for node in path_hex {
            match hex_bytes(Some(node), 32, &format!("proof {sequence}: path node"), &mut problems) {
                Some(bytes) => path.push(bytes),
                None => {
                    path_ok = false;
                    break;
                }
            }
        }
        if !path_ok {
            continue;
        }
        let Some(entry_hash) = entry
            .get("entryHash")
            .and_then(Value::as_str)
            .and_then(|s| hex_decode(s))
        else {
            continue;
        };
        let Some(root) = root else { continue };
        let Some(tree_size) = tree_size else { continue };
        if !merkle::verify_inclusion(
            leaf_index,
            &entry_hash,
            tree_size as usize,
            &path,
            &root,
        ) {
            problems.push(format!(
                "entry {sequence}: Merkle inclusion proof does not verify"
            ));
        }
    }
    for sequence in by_sequence.keys() {
        if !proven.contains(sequence) {
            problems.push(format!("entry {sequence}: no inclusion proof included"));
        }
    }

    // -- 4. the signed tree head ---------------------------
    let head = bundle.get("treeHead");
    if !entries.is_empty() && head.map(Value::is_object) != Some(true) {
        problems.push("treeHead is required when entries exist".into());
    }
    if let (Some(head), Some(public_key)) = (head, public_key) {
        if head.get("seq").and_then(Value::as_u64) != tree_size {
            problems.push("treeHead.seq does not match proofs.treeSize".into());
        }
        if head.get("rootHash").and_then(Value::as_str) != root_hex {
            problems.push("treeHead.rootHash does not match proofs.rootHash".into());
        }
        let head_sig = hex_bytes(
            head.get("signature"),
            64,
            "treeHead.signature",
            &mut problems,
        );
        let signed_at = head.get("signedAt").and_then(Value::as_str);
        if signed_at.is_none() {
            problems.push("treeHead.signedAt must be a string".into());
        }
        if let (Some(head_sig), Some(signed_at), Some(root)) = (head_sig, signed_at, root)
        {
            let message = canonical::canonical_json(&json!({
                "root_hash": hex_encode(&root),
                "seq": head.get("seq").and_then(Value::as_u64).unwrap_or(0),
                "signed_at": signed_at,
            }))
            .unwrap_or_default();
            if !ed25519_verify(public_key, head_sig, &message) {
                problems.push(
                    "treeHead signature does not verify with the bundled public key"
                        .into(),
                );
            }
        }
    }

    // -- 5. the bundle signature ---------------------------
    if let Some(public_key) = public_key {
        let mut core: Map<String, Value> = bundle
            .as_object()
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter(|(key, _)| key != "signature")
            .collect();
        let _ = &mut core;
        let digest = match canonical::canonical_json(&Value::Object(core)) {
            Err(error) => {
                problems.push(format!("bundle is not canonically serializable: {error}"));
                None
            }
            Ok(bytes) => Some(sha256(&bytes)),
        };
        let declared = hex_bytes(
            bundle.pointer("/signature/digest"),
            32,
            "signature.digest",
            &mut problems,
        );
        if let (Some(digest), Some(declared)) = (digest, declared) {
            if digest != declared {
                problems.push(
                    "signature.digest does not match the bundle content — a field \
                     was tampered with after signing"
                        .into(),
                );
            }
        }
        let sig = hex_bytes(
            bundle.pointer("/signature/signature"),
            64,
            "signature.signature",
            &mut problems,
        );
        if let (Some(sig), Some(digest)) = (sig, digest) {
            if !ed25519_verify(public_key, sig, &digest) {
                problems.push(
                    "bundle signature does not verify with the bundled public key"
                        .into(),
                );
            }
        }
    }

    // -- compliance section presence -----------------------
    match bundle.get("compliance") {
        None => problems.push("compliance section is missing".into()),
        Some(compliance) => {
            if compliance.get("standards").and_then(Value::as_array).map(Vec::is_empty)
                != Some(false)
            {
                problems.push("compliance.standards is empty".into());
            }
            if compliance.get("mappings").and_then(Value::as_array).map(Vec::is_empty)
                != Some(false)
            {
                problems.push("compliance.mappings is empty".into());
            }
        }
    }

    problems
}

fn ed25519_verify(public_key: [u8; 32], signature: [u8; 64], message: &[u8]) -> bool {
    let Ok(key) = VerifyingKey::from_bytes(&public_key) else {
        return false;
    };
    key.verify(message, &Signature::from_bytes(&signature)).is_ok()
}

fn sha256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finalize().into()
}

fn hex_decode(text: &str) -> Option<[u8; 32]> {
    if text.len() != 64 || !text.bytes().all(|b| b.is_ascii_hexdigit()) {
        return None;
    }
    let mut out = [0u8; 32];
    for (index, chunk) in text.as_bytes().chunks(2).enumerate() {
        let byte = u8::from_str_radix(std::str::from_utf8(chunk).ok()?, 16).ok()?;
        out[index] = byte;
    }
    Some(out)
}

fn hex_bytes<const N: usize>(
    value: Option<&Value>,
    _byte_length: usize,
    what: &str,
    problems: &mut Vec<String>,
) -> Option<[u8; N]> {
    let byte_length = N;
    let mut invalid = || {
        problems.push(format!(
            "{what} must be a {}-character hex string ({} bytes)",
            byte_length * 2,
            byte_length
        ))
    };
    let Some(text) = value.and_then(Value::as_str) else {
        invalid();
        return None;
    };
    if text.len() != byte_length * 2 {
        invalid();
        return None;
    }
    if !text.bytes().all(|b| b.is_ascii_hexdigit()) || text.len() != N * 2 {
        problems.push(format!("{what} is not valid hex"));
        return None;
    }
    let mut out = [0u8; N];
    for (index, chunk) in text.as_bytes().chunks(2).enumerate() {
        let byte = u8::from_str_radix(std::str::from_utf8(chunk).ok()?, 16).ok()?;
        out[index] = byte;
    }
    Some(out)
}

fn base64_decode(text: &str) -> Result<Vec<u8>, ()> {
    // Standard alphabet with padding, strict like Python's
    // base64.b64decode(validate=True).
    const ALPHABET: &[u8; 64] =
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let bytes = text.as_bytes();
    if bytes.len() % 4 != 0 {
        return Err(());
    }
    let mut out = Vec::with_capacity(bytes.len() / 4 * 3);
    for chunk in bytes.chunks(4) {
        let pad = chunk.iter().rev().take_while(|b| **b == b'=').count();
        if pad > 2 || (pad > 0 && chunk[3 - pad + 1..].iter().any(|b| *b != b'=')) {
            return Err(());
        }
        let mut value: u32 = 0;
        for (index, &symbol) in chunk.iter().enumerate() {
            let digit = match symbol {
                b'=' => {
                    if index < 4 - pad {
                        return Err(());
                    }
                    0
                }
                _ => match ALPHABET.iter().position(|a| *a == symbol) {
                    Some(position) => position as u32,
                    None => return Err(()),
                },
            };
            value = (value << 6) | digit;
        }
        out.push((value >> 16) as u8);
        if pad < 2 {
            out.push((value >> 8) as u8);
        }
        if pad < 1 {
            out.push(value as u8);
        }
    }
    Ok(out)
}

fn hex_encode(bytes: &[u8; 32]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_strict_matches_python() {
        assert_eq!(base64_decode("dGVzdA==").unwrap(), b"test");
        assert_eq!(base64_decode("dGVzdA").unwrap_err(), ());
        assert_eq!(base64_decode("dGVzdA=!").unwrap_err(), ());
        assert_eq!(base64_decode("dGVzdA== ").unwrap_err(), ());
        // The bundled keys are 32 raw bytes: 44 base64 chars with one pad.
        assert_eq!(base64_decode("AAAAAAA=").unwrap(), vec![0u8; 5]);
    }
}
