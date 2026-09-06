//! CLI for meridian-verify — identical behaviour to `verifier/verify.py`:
//! exit 0 and a one-line summary on stdout when the bundle verifies; exit 1
//! with one actionable `FAIL:` line per problem on stderr otherwise.

use std::io::Read;
use std::process::ExitCode;

fn main() -> ExitCode {
    let mut args = std::env::args().skip(1);
    let path = args.next();
    if args.next().is_some() || path.as_deref() == Some("--help") || path.as_deref() == Some("-h")
    {
        eprintln!(
            "usage: meridian-verify <bundle.json> | -\n\
             Validates a Meridian audit bundle (FR-M36-06): chain, Merkle \
             proofs, signed tree head, bundle signature, compliance section. \
             Exit 0 = verifies, 1 = problems on stderr, 2 = usage/IO/JSON error."
        );
        return if args.next().is_some() { ExitCode::from(2) } else { ExitCode::SUCCESS };
    }

    let raw = match path.as_deref() {
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
