from pathlib import Path

import pandas as pd
import pytest

from src.validation.enforce_release_gate import enforce_release_gate


ROOT = Path(__file__).resolve().parents[1]


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
