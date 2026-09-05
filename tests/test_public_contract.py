from pathlib import Path
import importlib


def test_public_package_imports_under_neutral_name():
    module = importlib.import_module("agent_harness")
    assert module.__name__ == "agent_harness"


def test_private_transport_modules_are_absent():
    root = Path(__file__).resolve().parents[1] / "src" / "agent_harness"
    assert not (root / "github_supervision.py").exists()
    assert not (root / "supervision_watcher.py").exists()


def test_public_runtime_path_is_neutral():
    cli = (Path(__file__).resolve().parents[1] / "src" / "agent_harness" / "cli.py")
    assert ".fil-harness" in cli.read_text(encoding="utf-8")
    assert (".filipe" + "-harness") not in cli.read_text(encoding="utf-8")


def test_required_public_docs_and_single_ci_exist():
    root = Path(__file__).resolve().parents[1]
    for rel in ("README.md", "AGENTS.md", "SECURITY.md", "docs/architecture.md", "docs/trust-model.md", "docs/public-private-boundary.md"):
        assert (root / rel).is_file()
    workflows = list((root / ".github" / "workflows").glob("*.yml")) + list((root / ".github" / "workflows").glob("*.yaml"))
    assert [p.name for p in workflows] == ["ci.yml"]
    text = workflows[0].read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in text
    assert "python -m pytest -q" in text
    assert "python scripts/public_safety_scan.py ." in text


def test_public_branding_is_fil_harness():
    root = Path(__file__).resolve().parents[1]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    cli = (root / "src" / "agent_harness" / "cli.py").read_text(encoding="utf-8")
    assert 'name = "fil-harness"' in pyproject
    assert 'fil-harness = "agent_harness.cli:main"' in pyproject
    assert readme.startswith("# Fil-Harness\n")
    assert 'prog="fil-harness"' in cli
