//! CLI for meridian-verify — identical behaviour to `verifier/verify.py`:
//! exit 0 and a one-line summary on stdout when the bundle verifies; exit 1
//! with one actionable `FAIL:` line per problem on stderr otherwise.
//!
//! FR-M43-02: with `--witness`/`--trusted-keys` the CLI reports the three
//! separate verdicts (valid_signature / trusted_signer / evidence_coverage)
//! and exits non-zero when any verdict that has an opinion fails.

use std::io::Read;
use std::process::ExitCode;

struct Options {
    path: Option<String>,
    witness: Vec<String>,
    trusted_keys: Option<String>,
    trusted_witness_keys: Option<String>,
    help: bool,
    usage_error: bool,
}

fn parse_args() -> Options {
    let mut options = Options {
        path: None,
        witness: Vec::new(),
        trusted_keys: None,
        trusted_witness_keys: None,
        help: false,
        usage_error: false,
    };
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--witness" => match args.next() {
                Some(path) => options.witness.push(path),
                None => options.usage_error = true,
            },
            "--trusted-keys" => options.trusted_keys = args.next(),
            "--trusted-witness-keys" => options.trusted_witness_keys = args.next(),
            "-h" | "--help" => options.help = true,
            _ if options.path.is_none() => options.path = Some(arg),
            _ => options.usage_error = true,
        }
    }
    options
}

const USAGE: &str = "usage: meridian-verify <bundle.json> | - [--witness receipt.json]...\n\
    \t[--trusted-keys keys.txt] [--trusted-witness-keys wkeys.txt]\n\
    Validates a Meridian audit bundle (FR-M36-06): chain, Merkle proofs,\n\
    signed tree head, bundle signature, compliance section. With --witness\n\
    and --trusted-keys, reports three separate verdicts (FR-M43-02):\n\
    valid_signature, trusted_signer, evidence_coverage. Exit 0 = verifies,\n\
    1 = problems on stderr / a verdict failed, 2 = usage/IO/JSON error.\n\
    Without --witness the coverage verdict fails with the stated FR-M43-03\n\
    limitation: no witness, no wholesale-replacement detection.";

fn load_trusted_keys(path: &str) -> Result<Vec<[u8; 32]>, String> {
    let raw =
        std::fs::read_to_string(path).map_err(|error| format!("cannot read {path}: {error}"))?;
    let mut keys = Vec::new();
    for line in raw.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        let decoded = meridian_verify::base64_decode_pub(line)
            .ok_or_else(|| format!("{path}: not a valid base64 Ed25519 public key"))?;
        keys.push(decoded);
    }
    Ok(keys)
}

fn main() -> ExitCode {
    let options = parse_args();
    if options.usage_error {
        eprintln!("{USAGE}");
        return ExitCode::from(2);
    }
    if options.help {
        println!("{USAGE}");
        return ExitCode::SUCCESS;
    }

    let raw = match options.path.as_deref() {
        None | Some("-") => {
            let mut buffer = Vec::new();
            if let Err(error) = std::io::stdin().read_to_end(&mut buffer) {
                eprintln!("cannot read bundle from stdin: {error}");
                return ExitCode::from(2);
            }
            buffer
        }
        Some(path) => match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) => {
                eprintln!("cannot read bundle: {error}");
                return ExitCode::from(2);
            }
        },
    };

    let bundle: serde_json::Value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("bundle is not valid JSON: {error}");
            return ExitCode::from(2);
        }
    };

    let verdict_mode = !options.witness.is_empty() || options.trusted_keys.is_some();
    if !verdict_mode {
        // FR-M43-03 / T15: the interface states the unwitnessed limitation.
        eprintln!("NOTE: {}", meridian_verify::UNWITNESSED_LIMITATION);
    }

    let mut receipts = Vec::new();
    for path in &options.witness {
        let raw = match std::fs::read(path) {
            Ok(bytes) => bytes,
            Err(error) => {
                eprintln!("cannot read witness receipt: {error}");
                return ExitCode::from(2);
            }
        };
        match serde_json::from_slice(&raw) {
            Ok(receipt) => receipts.push(receipt),
            Err(error) => {
                eprintln!("witness receipt is not valid JSON: {error}");
                return ExitCode::from(2);
            }
        }
    }
    let trusted_keys = match &options.trusted_keys {
        Some(path) => match load_trusted_keys(path) {
            Ok(keys) => Some(keys),
            Err(error) => {
                eprintln!("{error}");
                return ExitCode::from(2);
            }
        },
        None => None,
    };
    let trusted_witness_keys = match &options.trusted_witness_keys {
        Some(path) => match load_trusted_keys(path) {
            Ok(keys) => Some(keys),
            Err(error) => {
                eprintln!("{error}");
                return ExitCode::from(2);
            }
        },
        None => None,
    };

    if verdict_mode {
        let verdicts = meridian_verify::verify_bundle_verdicts(
            &bundle,
            &receipts,
            trusted_keys.as_deref(),
            trusted_witness_keys.as_deref(),
        );
        for line in verdicts.lines() {
            println!("{line}");
        }
        return if verdicts.ok() {
            ExitCode::SUCCESS
        } else {
            ExitCode::FAILURE
        };
    }

    let problems = meridian_verify::verify_bundle(&bundle);
    if !problems.is_empty() {
        for problem in problems {
            eprintln!("FAIL: {problem}");
        }
        return ExitCode::FAILURE;
    }
    let entries = bundle["entries"].as_array().map(Vec::len).unwrap_or(0);
    let tree_size = bundle["treeHead"]["seq"].as_u64().unwrap_or(0);
    println!(
        "OK: bundle verifies — {entries} entries, tree size {tree_size}, \
         chain, Merkle proofs, tree head and bundle signature all valid"
    );
    ExitCode::SUCCESS
}
