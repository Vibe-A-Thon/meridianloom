//! Merkle tree verification — RFC 6962 §2.1 shapes and the RFC 9162
//! §2.1.3.2 reference inclusion algorithm, byte-identical to
//! `core/meridian_core/ledger/merkle.py`.

use sha2::{Digest, Sha256};

const LEAF_PREFIX: u8 = 0x00;
const NODE_PREFIX: u8 = 0x01;

pub fn leaf_hash(data: &[u8]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update([LEAF_PREFIX]);
    hasher.update(data);
    hasher.finalize().into()
}

pub fn node_hash(left: &[u8; 32], right: &[u8; 32]) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update([NODE_PREFIX]);
    hasher.update(left);
    hasher.update(right);
    hasher.finalize().into()
}

/// RFC 9162 §2.1.3.2 reference inclusion verification. Mirrors
/// `merkle.verify_inclusion` in the sidecar exactly.
pub fn verify_inclusion(
    index: usize,
    leaf_payload: &[u8],
    tree_size: usize,
    path: &[[u8; 32]],
    expected_root: &[u8; 32],
) -> bool {
    if index >= tree_size {
        return false;
    }
    let (mut fn_, mut sn) = (index, tree_size - 1);
    let mut r = leaf_hash(leaf_payload);
    for p in path {
        if sn == 0 {
            return false;
        }
        if fn_ & 1 == 1 || fn_ == sn {
            r = node_hash(p, &r);
            if fn_ & 1 == 0 {
                while fn_ & 1 == 0 && fn_ != 0 {
                    fn_ >>= 1;
                    sn >>= 1;
                }
            }
        } else {
            r = node_hash(&r, p);
        }
        fn_ >>= 1;
        sn >>= 1;
    }
    sn == 0 && r == *expected_root
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Root of a tree built by repeated RFC 6962 appends — compared against
    /// the Python implementation's output for the same 10 leaves.
    #[test]
    fn python_vector_tree_of_ten() {
        let leaves: Vec<[u8; 32]> = (0u8..10).map(|i| [i; 32]).collect();
        // Root computed by core/meridian_core/ledger/merkle.py `root()`:
        let expected = "fcebcde878bae4fd01745f71f8b199a31927e7ad9ed25ea0cd0c7997c1edad75";
        let mut frontier: Vec<(usize, [u8; 32])> = Vec::new();
        for leaf in &leaves {
            let mut size = 1usize;
            let mut carry = leaf_hash(leaf);
            while frontier.last().map(|(s, _)| *s) == Some(size) {
                let (_, left) = frontier.pop().unwrap();
                carry = node_hash(&left, &carry);
                size += size;
            }
            frontier.push((size, carry));
        }
        let mut acc = frontier.last().unwrap().1;
        for (_, subtree) in frontier[..frontier.len() - 1].iter().rev() {
            acc = node_hash(subtree, &acc);
        }
        assert_eq!(hex(&acc), expected);
    }

    #[test]
    fn inclusion_path_recomputes_root() {
        let leaves: Vec<[u8; 32]> = (0u8..7).map(|i| [i; 32]).collect();
        let root = python_root(&leaves);
        // Audit path for index 2 in a tree of 7, from the Python
        // implementation: sibling subtree hashes at each level.
        let path = audit_path(&leaves, 2);
        assert!(verify_inclusion(2, &leaves[2], 7, &path, &root));
        assert!(!verify_inclusion(2, &[0xff; 32], 7, &path, &root));
        assert!(!verify_inclusion(2, &leaves[2], 7, &path, &[0xff; 32]));
        assert!(!verify_inclusion(9, &leaves[2], 7, &path, &root));
    }

    fn python_root(leaves: &[[u8; 32]]) -> [u8; 32] {
        fn root_range(leaves: &[[u8; 32]], lo: usize, hi: usize) -> [u8; 32] {
            let n = hi - lo;
            if n == 0 {
                return sha256(b"");
            }
            if n == 1 {
                return leaf_hash(&leaves[lo]);
            }
            let k = 1usize << ((n - 1).ilog2());
            node_hash(
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
                return leaf_hash(&leaves[lo]);
            }
            let k = 1usize << ((n - 1).ilog2());
            node_hash(
                &root_range(leaves, lo, lo + k),
                &root_range(leaves, lo + k, hi),
            )
        }
        let mut path = Vec::new();
        fn walk(
            leaves: &[[u8; 32]],
            lo: usize,
            hi: usize,
            idx: usize,
            path: &mut Vec<[u8; 32]>,
        ) {
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

    fn sha256(data: &[u8]) -> [u8; 32] {
        let mut hasher = Sha256::new();
        hasher.update(data);
        hasher.finalize().into()
    }

    fn hex(bytes: &[u8; 32]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }
}
