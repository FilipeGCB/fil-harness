from examples.bugfix_ready.run import main as bugfix_main
from examples.human_gate.run import main as human_main


def test_bugfix_example_reaches_ready(capsys):
    assert bugfix_main() == 0
    out = capsys.readouterr().out
    assert "READY" in out
    assert "Trusted" in out


def test_human_gate_example_stops_for_human(capsys):
    assert human_main() == 0
    out = capsys.readouterr().out
    assert "WAITING_HUMAN" in out
    assert "merge" in out.lower()
