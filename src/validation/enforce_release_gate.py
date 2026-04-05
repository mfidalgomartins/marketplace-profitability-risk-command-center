from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


STATE_ORDER = {
    "publish-blocked": 0,
    "screening-grade only": 1,
    "decision-support only": 2,
    "analytically acceptable": 3,
    "technically valid": 4,
}


def _as_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def enforce_release_gate(
    release_file: Path,
    required_state: str,
    require_committee_grade: bool,
) -> None:
    if not release_file.exists():
        raise FileNotFoundError(f"Release assessment file not found: {release_file}")

    df = pd.read_csv(release_file)
    if df.empty:
        raise RuntimeError("Release assessment file is empty.")

    row = df.iloc[0]
    state = str(row["release_state"]).strip()
    if state not in STATE_ORDER:
        raise RuntimeError(f"Unknown release_state `{state}` in {release_file}.")
    if required_state not in STATE_ORDER:
        raise RuntimeError(f"Unknown required state `{required_state}`.")

    publish_blocked = _as_bool(row.get("publish_blocked", False))
    committee_grade_ready = _as_bool(row.get("committee_grade_ready", False))

    if publish_blocked:
        raise RuntimeError("Release is publish-blocked by validation issues.")

    if STATE_ORDER[state] < STATE_ORDER[required_state]:
        raise RuntimeError(
            f"Release state `{state}` does not meet required minimum `{required_state}`."
        )

    if require_committee_grade and not committee_grade_ready:
        raise RuntimeError("Release is not committee-grade ready.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail build when validation release state is below required governance gate.")
    parser.add_argument("--release-file", type=Path, default=Path("reports/validation_release_assessment.csv"))
    parser.add_argument(
        "--required-state",
        type=str,
        default="decision-support only",
        choices=list(STATE_ORDER.keys()),
    )
    parser.add_argument("--require-committee-grade", action="store_true")
    args = parser.parse_args()

    try:
        enforce_release_gate(
            release_file=args.release_file,
            required_state=args.required_state,
            require_committee_grade=args.require_committee_grade,
        )
    except Exception as exc:  # pragma: no cover - CLI handling
        print(f"Release gate: FAILED - {exc}")
        sys.exit(1)

    print(
        f"Release gate: PASSED (state >= `{args.required_state}`"
        + (", committee-grade required" if args.require_committee_grade else "")
        + ")."
    )


if __name__ == "__main__":
    main()
