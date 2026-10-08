"""Check tracked files without printing sensitive values. Uses only the standard library."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

RULES = {
    "private key": rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    "GitHub token": rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b",
    "cloud credential": rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|\bAIza[A-Za-z0-9_-]{30,}\b",
    "API credential": rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b",
    "personal home path": rb"(?:/" rb"Users/[^/\s<>\"`]+|[A-Za-z]:\\Users\\[^\\\s<>\"`]+)",
    "private network address": rb"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b",
    "device fingerprint": rb"SHA256:[A-Za-z0-9+/]{43}(?![A-Za-z0-9+/])",
}


def violations(path: str, data: bytes) -> list[str]:
    name = pathlib.PurePosixPath(path).name
    results = []
    if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        results.append("private environment file")
    if name.endswith((".local.yaml", ".local.yml", ".pem", ".key", ".wav", ".pcm", ".mp3", ".db", ".sqlite", ".sqlite3")):
        results.append("private configuration, recording or database")
    results.extend(label for label, pattern in RULES.items() if re.search(pattern, data))
    return results


def main() -> int:
    root = pathlib.Path(__file__).resolve().parents[1]
    files = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode("utf-8").split("\0")
    failures = []
    for name in filter(None, files):
        path = root / name
        if path.is_file():
            failures.extend(f"{name}: {label}" for label in violations(name, path.read_bytes()))
    if failures:
        print("Publication privacy check failed (values withheld):")
        print("\n".join(failures))
        return 1
    print(f"Publication privacy check passed for {len(files) - 1} tracked files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
