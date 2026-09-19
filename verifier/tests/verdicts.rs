//! FR-M43-02 (N2 Workstream D task 14): the three independent verdicts —
//! `valid_signature`, `trusted_signer`, `evidence_coverage` — computed
//! against witness receipts, with rollback/truncation and
//! wholesale-replacement (fork) detection landing in the coverage verdict,
//! NEVER in the signature verdict. FR-M43-03: no receipts, no coverage
//! claim, and the limitation is stated in the returned detail.

use ed25519_dalek::{Signer, SigningKey};
use meridian_verify::{canonical, merkle, verify_bundle_verdicts, UNWITNESSED_LIMITATION};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

fn sha256(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(data);
    hasher.finalize().into()
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Standard base64 with padding, matching Python's b64encode.
fn b64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] =
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::new();
    for chunk in bytes.chunks(3) {
        let value: u32 =
            chunk.iter().fold(0u32, |acc, b| (acc << 8) | *b as u32) << (8 * (3 - chunk.len()));
        out.push(ALPHABET[(value >> 18) as usize & 63] as char);
        out.push(ALPHABET[(value >> 12) as usize & 63] as char);
        if chunk.len() > 1 {
            out.push(ALPHABET[(value >> 6) as usize & 63] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(ALPHABET[value as usize & 63] as char);
        } else {
            out.push('=');
        }
    }
    out
}

fn tree_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    merkle::tree_root(leaves)
}

fn audit_path(leaves: &[[u8; 32]], index: usize) -> Vec<[u8; 32]> {
    fn root_range(leaves: &[[u8; 32]], lo: usize, hi: usize) -> [u8; 32] {
        let n = hi - lo;
        if n == 1 {
            return merkle::leaf_hash(&leaves[lo]);
        }
        let k = 1usize << ((n - 1).ilog2());
        merkle::node_hash(
            &root_range(leaves, lo, lo + k),
            &root_range(leaves, lo + k, hi),
        )
    }
    let mut path = Vec::new();
    fn walk(leaves: &[[u8; 32]], lo: usize, hi: usize, idx: usize, path: &mut Vec<[u8; 32]>) {
        if hi - lo == 1 {
            return;
        }
        let k = 1usize << ((hi - lo - 1).ilog2());
        if idx < lo + k {
            walk(leaves, lo, lo + k, idx, path);
            path.push(root_range(leaves, lo + k, hi));
        } else {
            walk(leaves, lo + k, hi, idx, path);
            path.push(root_range(leaves, lo, lo + k));
        }
    }
    walk(leaves, 0, leaves.len(), index, &mut path);
    path
}

/// Build a conforming bundle of `count` entries signed with `signing`.
/// `story` differentiates forks that share a signer key.
fn make_bundle(count: usize, signing: &SigningKey, story: &str) -> Value {
    let verifying = signing.verifying_key();
    let mut entries = Vec::new();
    let mut leaves: Vec<[u8; 32]> = Vec::new();
    let mut previous = [0u8; 32];
    for seq in 1..=count {
        let payload = json!({
            "action_type": "diff",
            "actor_id": "agent-one",
            "actor_kind": "role",
            "actor_version": "1.0.0",
            "loop_id": "L2-task",
            "loop_iteration": 1,
            "phase": "build",
            "policy_version": "policy-v1",
            "seq": seq,
            "simulated": 0,
            "story_id": story,
            "ts_utc": format!("2026-09-01T00:00:{seq:06}Z"),
            "vendor": "claude-code",
        });
        let mut preimage = previous.to_vec();
        preimage.extend_from_slice(&canonical::canonical_json(&payload).unwrap());
        let entry_hash = sha256(&preimage);
        entries.push(json!({
            "sequence": seq,
            "timestamp": format!("2026-09-01T00:00:{seq:06}Z"),
            "storyId": story,
            "phase": "build",
            "loopId": "L2-task",
            "loopIteration": 1,
            "actorId": "agent-one",
            "actorVersion": "1.0.0",
            "actorKind": "role",
            "policyVersion": "policy-v1",
            "actionType": "diff",
            "vendor": "claude-code",
            "observationConfidence": "direct",
            "externalSessionId": null,
            "runId": null,
            "origin": null,
            "simulated": false,
            "entryHash": hex(&entry_hash),
            "previousHash": hex(&previous),
            "hasInputBlob": false,
            "hasOutputBlob": false,
            "hashPayload": payload,
        }));
        previous = entry_hash;
        leaves.push(entry_hash);
    }

    let root = tree_root(&leaves);
    let signed_at = "2026-09-02T00:00:00Z";
    let head_message = canonical::canonical_json(&json!({
        "root_hash": hex(&root),
        "seq": count,
        "signed_at": signed_at,
    }))
    .unwrap();
    let head_signature = signing.sign(&head_message);

    let inclusion: Value = (1..=count)
        .map(|seq| {
            json!({
                "sequence": seq,
                "leafIndex": seq - 1,
                "path": audit_path(&leaves, seq - 1).iter().map(|n| hex(n)).collect::<Vec<_>>(),
            })
        })
        .collect();

    let mut bundle = json!({
        "formatVersion": 1,
        "generatedAt": signed_at,
        "signer": {"algorithm": "Ed25519", "publicKey": b64(&verifying.to_bytes())},
        "treeHead": {
            "seq": count,
            "rootHash": hex(&root),
            "signedAt": signed_at,
            "signature": hex(&head_signature.to_bytes()),
        },
        "range": {"fromSequence": 1, "toSequence": count},
        "filter": {},
        "entries": entries,
        "proofs": {
            "treeSize": count,
            "rootHash": hex(&root),
            "inclusion": inclusion,
        },
        "compliance": {
            "standards": ["NIST SSDF (SP 800-218 v1.1)"],
            "mappings": [{
                "framework": "EU AI Act",
                "reference": "Article 12(1) (Record keeping)",
                "requirement": "automatic recording of events",
                "bundleFields": ["entries"],
            }],
        },
    });
    let digest = sha256(&canonical::canonical_json(&bundle).unwrap());
    bundle["signature"] = json!({
        "algorithm": "Ed25519",
        "signedAt": signed_at,
        "digest": hex(&digest),
        "signature": hex(&signing.sign(&digest).to_bytes()),
    });
    bundle
}

/// A witness receipt for the bundle's tree head, countersigned by
/// `witness` (or unsigned when `witness` is None — the local reception
/// shape). Mirrors `ledger/receipts.py::make_receipt`.
fn make_receipt(bundle: &Value, witness: Option<&SigningKey>) -> Value {
    let head = &bundle["treeHead"];
    let mut receipt = json!({
        "formatVersion": 1,
        "kind": "meridian-tree-head-receipt",
        "witness": {
            "id": "test-witness",
            "publicKey": witness.map(|w| b64(&w.verifying_key().to_bytes())),
        },
        "ledgerPublicKey": bundle["signer"]["publicKey"],
        "treeHead": {
            "seq": head["seq"],
            "rootHash": head["rootHash"],
            "signedAt": head["signedAt"],
            "signature": head["signature"],
        },
        "receivedAt": "2026-09-02T01:00:00Z",
    });
    if let Some(witness) = witness {
        let mut body = receipt.as_object().unwrap().clone();
        body.remove("witnessSignature");
        let message = canonical::canonical_json(&Value::Object(body)).unwrap();
        receipt["witnessSignature"] = json!(hex(&witness.sign(&message).to_bytes()));
    }
    receipt
}

#[test]
fn all_three_verdicts_pass_with_witness_and_trusted_key() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let bundle = make_bundle(8, &signing, "S-1");
    let receipt = make_receipt(&bundle, Some(&witness));
    let trusted = [signing.verifying_key().to_bytes()];
    let pinned = [witness.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], Some(&trusted), Some(&pinned));
    assert_eq!(
        verdicts,
        meridian_verify::Verdicts {
            valid_signature: true,
            trusted_signer: Some(true),
            evidence_coverage: true,
            detail: verdicts.detail.clone(),
            problems: Vec::new(),
        }
    );
    assert!(verdicts.ok());
    assert!(verdicts.lines()[0].contains("valid_signature: pass"));
}

#[test]
fn changed_entry_fails_only_valid_signature() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let mut bundle = make_bundle(6, &signing, "S-1");
    let receipt = make_receipt(&bundle, Some(&witness));
    // Tamper with an entry's content but leave every signature in place.
    bundle["entries"][2]["hashPayload"]["phase"] = json!("evil");
    let trusted = [signing.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], Some(&trusted), None);
    assert!(!verdicts.valid_signature, "changed entry must fail valid_signature");
    assert_eq!(verdicts.trusted_signer, Some(true));
    assert!(
        verdicts
            .problems
            .iter()
            .any(|p| p.contains("entry 3: entryHash")),
        "an actionable changed-entry problem is reported: {:?}",
        verdicts.problems
    );
}

#[test]
fn untrusted_signer_fails_only_trusted_signer() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let other = SigningKey::from_bytes(&[11u8; 32]);
    let bundle = make_bundle(6, &signing, "S-1");
    let receipt = make_receipt(&bundle, Some(&witness));
    let wrong_trusted = [other.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], Some(&wrong_trusted), None);
    assert!(verdicts.valid_signature);
    assert_eq!(verdicts.trusted_signer, Some(false));
    assert!(verdicts.evidence_coverage);
    assert!(!verdicts.ok());
}

#[test]
fn no_trusted_key_set_means_no_trust_opinion() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let bundle = make_bundle(4, &signing, "S-1");
    let receipt = make_receipt(&bundle, None);
    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], None, None);
    assert_eq!(verdicts.trusted_signer, None);
    assert!(verdicts.ok(), "no opinion must not fail the run");
}

/// Re-sign a bundle after structural edits (models an administrator
/// holding the signing key re-signing a rolled-back ledger).
fn resign(bundle: &mut Value, signing: &SigningKey) {
    bundle.as_object_mut().unwrap().remove("signature");
    let digest = sha256(&canonical::canonical_json(&bundle).unwrap());
    bundle["signature"] = json!({
        "algorithm": "Ed25519",
        "signedAt": "2026-09-02T00:00:00Z",
        "digest": hex(&digest),
        "signature": hex(&signing.sign(&digest).to_bytes()),
    });
}

#[test]
fn truncation_against_witnessed_root_is_a_coverage_failure_not_a_signature_failure() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let bundle = make_bundle(8, &signing, "S-1");
    let receipt = make_receipt(&bundle, Some(&witness));
    // Roll the ledger back: drop the last four entries. The remaining
    // bundle is still internally consistent (inclusion proofs are for the
    // full tree of 8) and the administrator re-signs it — so signatures
    // pass, but the witness saw 8 entries.
    let mut truncated = bundle.clone();
    truncated["entries"] =
        json!(truncated["entries"].as_array().unwrap().iter().take(4).collect::<Vec<_>>());
    truncated["proofs"]["inclusion"] =
        json!(truncated["proofs"]["inclusion"].as_array().unwrap().iter().take(4).collect::<Vec<_>>());
    resign(&mut truncated, &signing);
    let trusted = [signing.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&truncated, &[receipt], Some(&trusted), None);
    assert!(
        verdicts.valid_signature,
        "rollback must NOT be reported as a signature failure: {:?}",
        verdicts.problems
    );
    assert!(!verdicts.evidence_coverage);
    assert!(verdicts.detail.contains("rollback/truncation"), "{}", verdicts.detail);
}

#[test]
fn wholesale_replacement_is_valid_signature_true_coverage_false() {
    // The FR-M43-02 headline case: an administrator (or attacker holding
    // the signing key) builds a FORK from the same enrolled key. Every
    // signature on the fork verifies; only the witness catches it.
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let original = make_bundle(8, &signing, "S-1");
    let receipt = make_receipt(&original, Some(&witness));
    let fork = make_bundle(8, &signing, "S-FORK");
    let trusted = [signing.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&fork, &[receipt], Some(&trusted), None);
    assert!(verdicts.valid_signature, "fork is honestly signed: {:?}", verdicts.problems);
    assert_eq!(verdicts.trusted_signer, Some(true));
    assert!(!verdicts.evidence_coverage);
    assert!(
        verdicts.detail.contains("wholesale replacement or fork"),
        "{}",
        verdicts.detail
    );
}

#[test]
fn no_receipts_stated_limitation() {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let bundle = make_bundle(4, &signing, "S-1");
    let verdicts = verify_bundle_verdicts(&bundle, &[], None, None);
    assert!(verdicts.valid_signature);
    assert!(!verdicts.evidence_coverage);
    assert_eq!(verdicts.detail, UNWITNESSED_LIMITATION);
    assert!(verdicts.detail.contains("wholesale ledger replacement"));
}

#[test]
fn unsigned_reception_receipt_counts_for_coverage() {
    // The default local file store records reception without a detachable
    // countersignature; it still anchors coverage (weaker, and the detail
    // says so).
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let bundle = make_bundle(5, &signing, "S-1");
    let receipt = make_receipt(&bundle, None);
    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], None, None);
    assert!(verdicts.valid_signature);
    assert!(verdicts.evidence_coverage);
    assert!(verdicts.detail.contains("reception receipt"), "{}", verdicts.detail);
}

#[test]
fn unpinned_witness_key_does_not_count_for_coverage() {
    // SEC-36 posture: the embedded witness key is self-asserted. With a
    // pinned set configured, a receipt from any other witness key is
    // ignored — coverage is undetermined, not silently passed.
    let signing = SigningKey::from_bytes(&[7u8; 32]);
    let witness = SigningKey::from_bytes(&[9u8; 32]);
    let pinned_witness = SigningKey::from_bytes(&[13u8; 32]);
    let bundle = make_bundle(5, &signing, "S-1");
    let receipt = make_receipt(&bundle, Some(&witness));
    let pinned = [pinned_witness.verifying_key().to_bytes()];

    let verdicts = verify_bundle_verdicts(&bundle, &[receipt], None, Some(&pinned));
    assert!(verdicts.valid_signature);
    assert!(!verdicts.evidence_coverage);
    assert!(
        verdicts.detail.contains("no usable witness receipts"),
        "{}",
        verdicts.detail
    );
}
