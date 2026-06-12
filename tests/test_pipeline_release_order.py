from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pipeline_builds_dashboard_after_current_validation_outputs() -> None:
    source = (ROOT / "src" / "pipeline" / "run_full_pipeline.py").read_text(encoding="utf-8")

    validation_pos = source.index('"run formal validation"')
    dashboard_pos = source.index('"build executive dashboard"')
    gate_pos = source.index('"enforce release gate"')
    graphs_pos = source.index('"build publication chart pack"')
    report_pos = source.index('"build publication PDF report"')
    pages_pos = source.index('"publish GitHub Pages dashboard entrypoint"')

    assert validation_pos < dashboard_pos < gate_pos < graphs_pos < report_pos < pages_pos
