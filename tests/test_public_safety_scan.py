from pathlib import Path

from scripts.public_safety_scan import scan_tree


def test_scan_rejects_external_private_denylist_marker(tmp_path: Path):
    marker = "synthetic-private-marker"
    (tmp_path / "bad.py").write_text(f"value = {marker!r}\n", encoding="utf-8")
    labels = {finding.label for finding in scan_tree(tmp_path, (marker,))}
    assert "private_external_denylist" in labels


def test_scan_accepts_public_identifiers(tmp_path: Path):
    (tmp_path / "good.py").write_text(
        "HumanDecision\n~/.fil-harness/\nagent_harness",
        encoding="utf-8",
    )
    assert scan_tree(tmp_path) == ()


def test_scan_rejects_secret_shaped_values(tmp_path: Path):
    (tmp_path / "secret.txt").write_text(
        "Authorization: " + "Bearer " + "abcdefghijklmnop",
        encoding="utf-8",
    )
    labels = {finding.label for finding in scan_tree(tmp_path)}
    assert "secret_pattern" in labels



def test_public_scanner_stores_builtin_private_markers_only_as_hashes():
    from scripts.public_safety_scan import BUILTIN_DENIED_HASHES

    assert BUILTIN_DENIED_HASHES
    assert all(len(value) == 64 for value in BUILTIN_DENIED_HASHES)
    assert all(set(value) <= set("0123456789abcdef") for value in BUILTIN_DENIED_HASHES)
