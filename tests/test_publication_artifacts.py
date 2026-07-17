from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def test_publication_artifacts_exist() -> None:
    graphs = sorted((ROOT / "outputs" / "graphs").glob("*.png"))
    report = ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf"

    assert len(graphs) == 20
    assert report.exists()
    assert report.stat().st_size > 100_000


def test_report_folder_contains_one_final_pdf() -> None:
    pdfs = sorted(path.name for path in (ROOT / "outputs" / "reports").glob("*.pdf"))

    assert pdfs == ["marketplace-command-center-report.pdf"]


def test_final_report_uses_letter_format() -> None:
    report = PdfReader(ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf")
    first_page = report.pages[0]

    assert float(first_page.mediabox.width) == 612.0
    assert float(first_page.mediabox.height) == 792.0


def test_cover_art_is_not_repeated_on_body_pages() -> None:
    report = PdfReader(ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf")
    second_page_commands = report.pages[1].get_contents().get_data()

    assert b"n 0 0 612 792 re f*" not in second_page_commands


def test_report_has_no_nearly_blank_body_pages() -> None:
    report = PdfReader(ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf")
    body_text_lengths = [len(" ".join((page.extract_text() or "").split())) for page in report.pages[1:]]

    assert min(body_text_lengths) > 400


def test_final_report_preserves_core_sections_and_figures() -> None:
    report = PdfReader(ROOT / "outputs" / "reports" / "marketplace-command-center-report.pdf")
    text = "\n".join(page.extract_text() or "" for page in report.pages)
    normalized_text = " ".join(text.split())

    required_sections = {
        "Executive summary",
        "Context and objectives",
        "Data and methodology",
        "Analytical framework",
        "Growth quality and the protection gap",
        "Unit economics and where the money goes",
        "Category exposure",
        "Seller governance and concentration",
        "Order and buyer risk",
        "Scenario and policy economics",
        "Risks, limitations and caveats",
        "Recommendations and action priorities",
        "Further questions and evidence gaps",
        "Appendix",
    }

    assert all(section in normalized_text for section in required_sections)
    assert normalized_text.count("Figure ") == 20


def test_chart_pack_uses_the_editorial_palette() -> None:
    graph_builder_source = (ROOT / "src" / "visualization" / "build_report_graphs.py").read_text(encoding="utf-8")

    assert 'ACCENT = "#F04423"' in graph_builder_source
    assert 'LOSS = "#8C302B"' in graph_builder_source
    assert 'GOLD = "#C99A2E"' in graph_builder_source
    assert 'PINK = "#B76A88"' in graph_builder_source
