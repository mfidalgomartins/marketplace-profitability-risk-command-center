from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_publication_artifacts_exist() -> None:
    graphs = sorted((ROOT / "outputs" / "graphs").glob("*.png"))
    report = ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf"

    assert len(graphs) == 20
    assert report.exists()
    assert report.stat().st_size > 100_000
