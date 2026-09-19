//! End-to-end test: build a ledger-shaped bundle in this crate (signing
//! with a throwaway key, exactly as the sidecar does), then run the same
//! verification the CLI runs. Proves the verifier accepts what a conforming
//! producer emits and rejects every tamper class — with no Meridian code.

use ed25519_dalek::{Signer, SigningKey};
use meridian_verify::{canonical, merkle, verify_bundle};
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

/// The tree construction the bundle proofs rely on, RFC 6962 §2.1.
fn tree_root(leaves: &[[u8; 32]]) -> [u8; 32] {
    fn root_range(leaves: &[[u8; 32]], lo: usize, hi: usize) -> [u8; 32] {
        let n = hi - lo;
        if n == 0 {
            return sha256(b"");
        }
        if n == 1 {
            return merkle::leaf_hash(&leaves[lo]);
        }
        let k = 1usize << ((n - 1).ilog2());
        merkle::node_hash(
            &root_range(leaves, lo, lo + k),
            &root_range(leaves, lo + k, hi),
        )
    }
    root_range(leaves, 0, leaves.len())
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

fn make_bundle(count: usize) -> (Value, SigningKey) {
    let signing = SigningKey::from_bytes(&[7u8; 32]);
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
            "cost_usd": 0.01,
            "confidence": 0.5,
            "loop_id": "L2-task",
            "loop_iteration": 1,
            "phase": "build",
            "policy_version": "policy-v1",
            "seq": seq,
            "simulated": 0,
            "story_id": "S-1",
            "ts_utc": format!("2026-09-01T00:00:{seq:06}Z"),
            "vendor": "claude-code",
        });
        let mut preimage = previous.to_vec();
        preimage.extend_from_slice(&canonical::canonical_json(&payload).unwrap());
        let entry_hash = sha256(&preimage);
        entries.push(json!({
            "sequence": seq,
            "timestamp": format!("2026-09-01T00:00:{seq:06}Z"),
            "storyId": "S-1",
            "phase": "build",
            "loopId": "L2-task",
            "loopIteration": 1,
            "actorId": "agent-one",
            "actorVersion": "1.0.0",
            "actorKind": "role",
            "policyVersion": "policy-v1",
            "actionType": "diff",
            "confidence": 0.5,
            "costUsd": 0.01,
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

    let tree_size = count;
    let root = tree_root(&leaves);
    let signed_at = "2026-09-02T00:00:00Z";
    let head_message = canonical::canonical_json(&json!({
        "root_hash": hex(&root),
        "seq": tree_size,
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

    let base64_key = {
        // Standard base64 with padding, matching Python's b64encode.
        const ALPHABET: &[u8; 64] =
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let bytes = verifying.to_bytes();
        let mut out = String::new();
        for chunk in bytes.chunks(3) {
            let value: u32 = chunk.iter().fold(0u32, |acc, b| (acc << 8) | *b as u32)
                << (8 * (3 - chunk.len()));
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
    };

    let mut bundle = json!({
        "formatVersion": 1,
        "generatedAt": signed_at,
        "signer": {"algorithm": "Ed25519", "publicKey": base64_key},
        "treeHead": {
            "seq": tree_size,
            "rootHash": hex(&root),
            "signedAt": signed_at,
            "signature": hex(&head_signature.to_bytes()),
        },
        "range": {"fromSequence": 1, "toSequence": count},
        "filter": {},
        "entries": entries,
        "proofs": {
            "treeSize": tree_size,
            "rootHash": hex(&root),
            "inclusion": inclusion,
        },
        "compliance": {
            "standards": [
                "NIST SSDF (SP 800-218 v1.1)",
                "ISO/IEC 42001:2023",
                "EU AI Act (Regulation (EU) 2024/1689), Article 12",
            ],
            "mappings": [{
                "framework": "EU AI Act",
                "reference": "Article 12(1) (Record keeping)",
                "requirement": "automatic recording of events",
                "bundleFields": ["entries"],
            }],
        },
    });

    // The bundle signature covers every field except the signature block.
    let digest = sha256(&canonical::canonical_json(&bundle).unwrap());
    bundle["signature"] = json!({
        "algorithm": "Ed25519",
        "signedAt": signed_at,
        "digest": hex(&digest),
        "signature": hex(&signing.sign(&digest).to_bytes()),
    });
    (bundle, signing)
}

#[test]
fn constructed_bundle_verifies() {
    let (bundle, _) = make_bundle(8);
    let problems = verify_bundle(&bundle);
    assert_eq!(problems, Vec::<String>::new());
}

#[test]
fn every_tamper_class_is_rejected() {
    let (bundle, _) = make_bundle(6);

    let mut payload = bundle.clone();
    payload["entries"][2]["hashPayload"]["phase"] = json!("evil");
    assert!(verify_bundle(&payload)
        .iter()
        .any(|p| p.contains("entry 3: entryHash")));

    let mut friendly = bundle.clone();
    friendly["entries"][2]["phase"] = json!("evil");
    assert!(verify_bundle(&friendly).iter().any(|p| p.contains("digest")));

    let mut proof = bundle.clone();
    proof["proofs"]["inclusion"][0]["path"][0] = json!("00".repeat(32));
    assert!(verify_bundle(&proof)
        .iter()
        .any(|p| p.contains("inclusion proof")));

    let mut head = bundle.clone();
    head["treeHead"]["rootHash"] = json!("ab".repeat(32));
    assert!(verify_bundle(&head)
        .iter()
        .any(|p| p.contains("treeHead")));

    let mut sig = bundle.clone();
    sig["signature"]["signature"] = json!("ff".repeat(64));
    assert!(verify_bundle(&sig)
        .iter()
        .any(|p| p.contains("bundle signature")));

    let mut link = bundle.clone();
    link["entries"][3]["previousHash"] = json!("00".repeat(32));
    assert!(verify_bundle(&link)
        .iter()
        .any(|p| p.contains("chain link")));

    let mut missing_proof = bundle.clone();
    missing_proof["proofs"]["inclusion"] =
        json!(missing_proof["proofs"]["inclusion"].as_array().unwrap()[1..]);
    assert!(verify_bundle(&missing_proof)
        .iter()
        .any(|p| p.contains("no inclusion proof")));

    let mut key = bundle.clone();
    key["signer"]["publicKey"] = json!("AAAA");
    assert!(verify_bundle(&key).iter().any(|p| p.contains("publicKey")));

    let mut compliance = bundle.clone();
    compliance.as_object_mut().unwrap().remove("compliance");
    assert!(verify_bundle(&compliance)
        .iter()
        .any(|p| p.contains("compliance")));
}
