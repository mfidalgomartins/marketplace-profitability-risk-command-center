from pathlib import Path

import pandas as pd
import pytest
from src.validation import enforce_release_gate as gate_module
from src.validation.enforce_release_gate import enforce_release_gate

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILE = ROOT / "reports" / "validation_release_assessment.csv"


def test_gate_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        enforce_release_gate(tmp_path / "missing.csv", "decision-support only", False)


def test_gate_raises_for_empty_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    pd.DataFrame(columns=["release_state"]).to_csv(empty, index=False)
    with pytest.raises(RuntimeError):
        enforce_release_gate(empty, "decision-support only", False)


def test_gate_raises_for_unknown_state(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    pd.DataFrame([{"release_state": "imaginary", "publish_blocked": False}]).to_csv(bad, index=False)
    with pytest.raises(RuntimeError):
        enforce_release_gate(bad, "decision-support only", False)


def test_gate_cli_passes_on_current_release(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["enforce_release_gate.py", "--release-file", str(RELEASE_FILE), "--required-state", "decision-support only"],
    )
    gate_module.main()
    assert "PASSED" in capsys.readouterr().out


def test_gate_cli_exits_nonzero_when_committee_grade_required(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "enforce_release_gate.py",
            "--release-file",
            str(RELEASE_FILE),
            "--required-state",
            "decision-support only",
            "--require-committee-grade",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        gate_module.main()
    assert exc.value.code == 1
    assert "FAILED" in capsys.readouterr().out


def test_release_gate_passes_for_current_state() -> None:
    enforce_release_gate(
        release_file=ROOT / "reports" / "validation_release_assessment.csv",
        required_state="decision-support only",
        require_committee_grade=False,
    )


def test_release_gate_rejects_excessive_required_state() -> None:
    tmp = ROOT / "reports" / "_tmp_release_gate_test.csv"
    pd.DataFrame(
        [
            {
                "release_state": "screening-grade only",
                "publish_blocked": False,
                "committee_grade_ready": False,
            }
        ]
    ).to_csv(tmp, index=False)
    with pytest.raises(RuntimeError):
        enforce_release_gate(
            release_file=tmp,
            required_state="decision-support only",
            require_committee_grade=True,
        )
    tmp.unlink(missing_ok=True)


def test_current_release_is_not_committee_grade() -> None:
    with pytest.raises(RuntimeError):
        enforce_release_gate(
            release_file=ROOT / "reports" / "validation_release_assessment.csv",
            required_state="decision-support only",
            require_committee_grade=True,
        )
