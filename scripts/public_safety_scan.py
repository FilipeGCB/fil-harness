from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

# Private identifiers are represented only by one-way hashes so the public
# scanner can reject them without publishing the private denylist in cleartext.
BUILTIN_DENIED_HASHES: dict[str, str] = {
    "06bf32f0d6e78587de7955bb50f9479dfbd75cfb78515c8fb6a87b3e05c6f9ea": "private_identifier",
    "36251d45a76fd0ddd05efeb0b34e7bc07dfd1215343bcf6d0bb11d40c4a2e7cc": "private_identifier",
    "13f8b3da903b2697b9c205302e0b151fd09747e836365bd56f6fd4fa438e3e0a": "private_identifier",
    "968325387139d9bd3b7da28ecda119becc0b3afae6dc93f0aa83c2898123a74a": "private_identifier",
    "3630e7aad2729cde329411fd9fe67bc204c2cda3253bfd71b5243658bbefa1aa": "private_identifier",
    "b0acd315baf7ba3ece50b99043632f073e807734fcdbe3c1a4ee932cef5532dd": "private_identifier",
    "96e02da61fce5f1f0d734f5a62ff7654de88b8db592ffa1632740301e8b49c25": "private_identifier",
    "2fdf3d58c45655a01d416b6098678c122c882a2c5a8b0f1407e10087f22e5680": "private_identifier",
}

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_.~-]+(?:/[A-Za-z0-9_.~-]+)*")
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{8,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
)
TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".yml", ".yaml", ".json", ".txt",
    ".ini", ".cfg", ".sh", ".ps1",
}
SKIP_PARTS = {".git", ".venv", ".prep", "__pycache__", ".pytest_cache"}


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    label: str
    needle: str


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hashed_identifier_findings(text: str, relative: str) -> list[Finding]:
    findings: list[Finding] = []
    for token in TOKEN_PATTERN.findall(text):
        label = BUILTIN_DENIED_HASHES.get(_hash(token))
        if label is not None:
            findings.append(Finding(relative, label, "sha256:" + _hash(token)))
    return findings


def scan_tree(root: Path, extra_denied: tuple[str, ...] = ()) -> tuple[Finding, ...]:
    root = root.resolve()
    extra = tuple(item for item in extra_denied if item)
    findings: list[Finding] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"README", "LICENSE"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        relative = str(path.relative_to(root))
        findings.extend(_hashed_identifier_findings(text, relative))

        for needle in extra:
            if needle in text:
                findings.append(Finding(relative, "private_external_denylist", "external-denylist-match"))

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(relative, "secret_pattern", pattern.pattern))

    return tuple(findings)


def _load_denylist(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    return tuple(
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--denylist", type=Path)
    args = parser.parse_args(argv)
    findings = scan_tree(Path(args.root), _load_denylist(args.denylist))
    for finding in findings:
        print(f"{finding.path}: {finding.label}: {finding.needle!r}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
