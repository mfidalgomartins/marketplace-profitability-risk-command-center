"""Build the decision-support analytical report into outputs/reports/.

The report is written as continuous prose with charts embedded inline. All
figures are computed from the governed processed tables so the document can be
rebuilt end to end from data.
"""

from __future__ import annotations

import types
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
REPORTS = ROOT / "reports"
GRAPHS = ROOT / "outputs" / "graphs"
OUT = ROOT / "outputs" / "reports"

# Brand palette — kept identical to the executive dashboard's light-mode CSS
# tokens (src/dashboard/build_executive_dashboard.py) and the chart pack's
# palette (src/visualization/build_report_graphs.py) so the dashboard, chart
# pack, and PDF read as one cohesive product rather than three near-matches.
NAVY = colors.HexColor("#0A1628")
INK = colors.HexColor("#1D2B3E")
MUTE = colors.HexColor("#5C6B80")
FAINT = colors.HexColor("#8593A5")
ACCENT = colors.HexColor("#5B54E0")
ACCENT_SOFT = colors.HexColor("#EEEDFD")
RED = colors.HexColor("#C5453B")
RED_SOFT = colors.HexColor("#FBECEA")
AMBER = colors.HexColor("#B07407")
AMBER_SOFT = colors.HexColor("#FBF3E4")
GREEN = colors.HexColor("#1F8A55")
GREEN_SOFT = colors.HexColor("#ECF6F0")
LINE = colors.HexColor("#E6E9EF")
PANEL = colors.HexColor("#F3F5F8")
WHITE = colors.white
PAGE_W, PAGE_H = A4
MARGIN = 1.9 * cm
FW = PAGE_W - 2 * MARGIN


def money(v: float, decimals: int = 2) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v) / 1e6:,.{decimals}f}M"


def thousands(v: float) -> str:
    sign = "-" if v < 0 else ""
    return f"{sign}${abs(v) / 1e3:,.0f}k"


def pct(v: float, decimals: int = 1) -> str:
    return f"{v * 100:.{decimals}f}%"


def styles():
    s = getSampleStyleSheet()
    s.add(
        ParagraphStyle(
            "CoverEyebrow", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT, leading=11, tracking=1.6
        )
    )
    s.add(
        ParagraphStyle("CoverTitle", fontName="Helvetica-Bold", fontSize=30, textColor=NAVY, leading=34, spaceAfter=12)
    )
    s.add(ParagraphStyle("CoverSub", fontName="Helvetica", fontSize=13.5, textColor=MUTE, leading=19))
    s.add(
        ParagraphStyle("MetaLabel", fontName="Helvetica-Bold", fontSize=7.3, textColor=FAINT, leading=9, tracking=0.7)
    )
    s.add(ParagraphStyle("MetaValue", fontName="Helvetica", fontSize=9.3, textColor=INK, leading=12.5))
    s.add(
        ParagraphStyle(
            "Kicker", fontName="Helvetica-Bold", fontSize=8, textColor=ACCENT, leading=10, tracking=1.2, spaceAfter=3
        )
    )
    # Section heading: tagged for the table of contents (level 0)
    s.add(
        ParagraphStyle(
            "SectionH1", fontName="Helvetica-Bold", fontSize=17, textColor=NAVY, leading=20, spaceBefore=0, spaceAfter=2
        )
    )
    # Same look as SectionH1 but not tagged for the table of contents
    s.add(
        ParagraphStyle(
            "PlainH1", fontName="Helvetica-Bold", fontSize=17, textColor=NAVY, leading=20, spaceBefore=0, spaceAfter=2
        )
    )
    s.add(ParagraphStyle("Deck", fontName="Helvetica", fontSize=10.5, textColor=MUTE, leading=15, spaceAfter=11))
    # Sub heading: tagged for the table of contents (level 1)
    s.add(
        ParagraphStyle(
            "SubH", fontName="Helvetica-Bold", fontSize=11.5, textColor=NAVY, leading=14, spaceBefore=9, spaceAfter=4
        )
    )
    s.add(
        ParagraphStyle(
            "Body", fontName="Helvetica", fontSize=9.7, textColor=INK, leading=14.4, spaceAfter=8, alignment=TA_JUSTIFY
        )
    )
    s.add(ParagraphStyle("BodyTight", parent=s["Body"], spaceAfter=5))
    s.add(
        ParagraphStyle(
            "Pull",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            leading=15.5,
            spaceBefore=2,
            spaceAfter=8,
            leftIndent=10,
            alignment=TA_LEFT,
        )
    )
    s.add(
        ParagraphStyle(
            "Caption",
            fontName="Helvetica-Oblique",
            fontSize=7.6,
            textColor=FAINT,
            leading=10,
            spaceBefore=3,
            alignment=TA_CENTER,
        )
    )
    s.add(
        ParagraphStyle(
            "FigNo",
            fontName="Helvetica-Bold",
            fontSize=7.6,
            textColor=ACCENT,
            leading=10,
            spaceBefore=3,
            alignment=TA_CENTER,
        )
    )
    s.add(ParagraphStyle("Metric", fontName="Helvetica-Bold", fontSize=18, textColor=NAVY, leading=20))
    s.add(ParagraphStyle("MetricRed", parent=s["Metric"], textColor=RED))
    s.add(ParagraphStyle("MetricLabel", fontName="Helvetica", fontSize=7.2, textColor=MUTE, leading=9))
    s.add(ParagraphStyle("TblH", fontName="Helvetica-Bold", fontSize=7.8, textColor=WHITE, leading=9.5))
    s.add(ParagraphStyle("TblHR", parent=s["TblH"], alignment=TA_RIGHT))
    s.add(ParagraphStyle("Tbl", fontName="Helvetica", fontSize=7.9, textColor=INK, leading=10.2))
    s.add(ParagraphStyle("TblR", parent=s["Tbl"], alignment=TA_RIGHT))
    s.add(
        ParagraphStyle(
            "BadgeHigh",
            fontName="Helvetica-Bold",
            fontSize=7.2,
            textColor=RED,
            backColor=RED_SOFT,
            borderPadding=(3, 5, 3, 5),
            alignment=TA_CENTER,
        )
    )
    s.add(
        ParagraphStyle(
            "BadgeMed",
            fontName="Helvetica-Bold",
            fontSize=7.2,
            textColor=AMBER,
            backColor=AMBER_SOFT,
            borderPadding=(3, 5, 3, 5),
            alignment=TA_CENTER,
        )
    )
    s.add(
        ParagraphStyle(
            "BadgeLow",
            fontName="Helvetica-Bold",
            fontSize=7.2,
            textColor=GREEN,
            backColor=GREEN_SOFT,
            borderPadding=(3, 5, 3, 5),
            alignment=TA_CENTER,
        )
    )
    s.add(ParagraphStyle("TOC0", fontName="Helvetica-Bold", fontSize=9.6, textColor=NAVY, leading=18, spaceBefore=5))
    s.add(ParagraphStyle("TOC1", fontName="Helvetica", fontSize=9.2, textColor=MUTE, leading=15, leftIndent=14))
    return s


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(MARGIN, 1.25 * cm, PAGE_W - MARGIN, 1.25 * cm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(FAINT)
    canvas.drawString(MARGIN, 0.9 * cm, "Marketplace Profitability, Fraud & Seller Quality")
    canvas.drawCentredString(PAGE_W / 2, 0.9 * cm, "Marketplace Intelligence and Analytics")
    canvas.drawRightString(PAGE_W - MARGIN, 0.9 * cm, str(doc.page))
    canvas.restoreState()


def cover_canvas(canvas, _doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, 0.55 * cm, PAGE_H, fill=1, stroke=0)
    canvas.setFillColor(ACCENT)
    canvas.rect(0.55 * cm, PAGE_H - 0.32 * cm, PAGE_W - 0.55 * cm, 0.32 * cm, fill=1, stroke=0)
    canvas.restoreState()


# ----------------------------------------------------------------------------
# Flowable helpers
# ----------------------------------------------------------------------------
ST = None
FIG = {"n": 0}


def h1(text):
    return Paragraph(text, ST["SectionH1"])


def deck(text):
    return Paragraph(text, ST["Deck"])


def h2(text):
    return Paragraph(text, ST["SubH"])


def p(text):
    return Paragraph(text, ST["Body"])


def pull(text):
    bar = Table([[Paragraph(text, ST["Pull"])]], colWidths=[FW])
    bar.setStyle(
        TableStyle(
            [
                ("LINEBEFORE", (0, 0), (0, 0), 2.5, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    # Table flowables carry no spacing of their own (unlike Paragraph styles),
    # so without this the callout sits flush against the body text before and
    # after it. Match Body's own spaceAfter (8) on both sides so the pull
    # quote reads as a distinct, breathing callout rather than run-in text.
    bar.spaceBefore = 8
    bar.spaceAfter = 10
    return bar


def fig(name, caption, width=14.4 * cm):
    from PIL import Image as PILImage

    FIG["n"] += 1
    path = GRAPHS / name
    iw, ih = PILImage.open(path).size
    img = Image(str(path), width=width, height=width * ih / iw)
    cap = Paragraph(f"Figure {FIG['n']}.&nbsp;&nbsp;{caption}", ST["Caption"])
    block = Table([[img], [cap]], colWidths=[width])
    block.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 1),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    outer = Table([[block]], colWidths=[FW])
    outer.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return KeepTogether([outer])


def metric_card(value, label, negative=False):
    t = Table(
        [
            [Paragraph(value, ST["MetricRed" if negative else "Metric"])],
            [Paragraph(label, ST["MetricLabel"])],
        ],
        colWidths=[(FW - 18) / 4],
    )
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("LINEABOVE", (0, 0), (-1, 0), 2, RED if negative else ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )
    return t


def metric_strip(cards):
    t = Table([cards], colWidths=[FW / 4] * 4)
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (1, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def table(rows, widths, numeric_cols=(), header=True, small=False):
    body = ST["Tbl"]
    cooked = []
    for r_idx, row in enumerate(rows):
        cooked_row = []
        for c_idx, value in enumerate(row):
            if header and r_idx == 0:
                # A numeric column's header must share its data's right edge —
                # left-aligning the label over right-aligned figures below it
                # reads as misaligned columns, not just a styling nicety.
                style = ST["TblHR"] if c_idx in numeric_cols else ST["TblH"]
            elif c_idx in numeric_cols:
                style = ST["TblR"]
            else:
                style = body
            cooked_row.append(Paragraph(str(value), style))
        cooked.append(cooked_row)
    t = Table(cooked, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [
        ("ROWBACKGROUNDS", (0, 1 if header else 0), (-1, -1), [WHITE, PANEL]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        cmds.insert(0, ("BACKGROUND", (0, 0), (-1, 0), NAVY))
    t.setStyle(TableStyle(cmds))
    return t


def priority_table(rows):
    cooked = [[Paragraph(v, ST["TblH"]) for v in rows[0]]]
    for row in rows[1:]:
        badge = {"Immediate": "BadgeHigh", "Near term": "BadgeMed", "Structural": "BadgeLow"}[row[0]]
        cooked.append(
            [
                Paragraph(row[0], ST[badge]),
                Paragraph(row[1], ST["Tbl"]),
                Paragraph(row[2], ST["Tbl"]),
                Paragraph(row[3], ST["Tbl"]),
                Paragraph(row[4], ST["TblR"]),
            ]
        )
    t = Table(cooked, colWidths=[2.2 * cm, 4.4 * cm, 3.3 * cm, 4.4 * cm, 2.9 * cm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, PANEL]),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------
def build():
    global ST
    OUT.mkdir(parents=True, exist_ok=True)
    ST = styles()

    # ---- Load governed data ------------------------------------------------
    kpi = pd.read_csv(REPORTS / "executive_kpi_snapshot.csv").set_index("metric")
    kv, kd = kpi["value"].to_dict(), kpi["display"].to_dict()
    opf = pd.read_csv(PROC / "order_profitability_features.csv", parse_dates=["order_date"])
    score = pd.read_csv(PROC / "seller_scorecard.csv")
    buyer = pd.read_csv(PROC / "buyer_behavior_risk.csv")
    ors = pd.read_csv(PROC / "order_risk_scores.csv")
    rec = pd.read_csv(PROC / "backtesting_recommended_policy.csv").iloc[0]
    threshold_curve = pd.read_csv(PROC / "backtesting_threshold_curve.csv").set_index("threshold")
    scen = pd.read_csv(PROC / "scenario_results_summary.csv").set_index("scenario")
    mc = pd.read_csv(PROC / "scenario_monte_carlo_summary.csv").set_index("scenario")
    scen_exposure = pd.read_csv(PROC / "scenario_top_risk_exposure.csv").iloc[0]
    release = pd.read_csv(REPORTS / "validation_release_assessment.csv").iloc[0]
    buyers_raw = pd.read_csv(RAW / "buyers.csv")[["buyer_id", "region"]]

    # ---- Derived figures ---------------------------------------------------
    n_orders, n_sellers, n_buyers = len(opf), len(score), len(buyer)
    commission = opf.commission_fee.sum()
    subsidy = opf.subsidy_amount.sum()
    refunds = opf.refund_amount.sum()
    disputes = opf.dispute_amount.sum()
    chargebacks = opf.chargeback_loss_proxy.sum()
    leakage = refunds + disputes + chargebacks
    margin = opf.realized_contribution_margin_proxy.sum()
    gmv = opf.gross_value.sum()
    margin_rate = margin / gmv
    pool = leakage + subsidy
    break_even_gap = abs(margin)
    take_rate_lift_needed = break_even_gap / gmv
    leakage_reduction_needed = break_even_gap / leakage

    monthly = (
        opf.assign(m=opf.order_date.dt.to_period("M"))
        .groupby("m")
        .agg(
            gmv=("gross_value", "sum"),
            rav=("risk_adjusted_order_value", "sum"),
            margin=("realized_contribution_margin_proxy", "sum"),
        )
    )
    n_months = len(monthly)
    first_loss, last_loss = monthly.margin.iloc[0], monthly.margin.iloc[-1]
    gap_first = 1 - monthly.rav.iloc[0] / monthly.gmv.iloc[0]
    gap_last = 1 - monthly.rav.iloc[-1] / monthly.gmv.iloc[-1]
    gap_avg = 1 - monthly.rav.sum() / monthly.gmv.sum()

    cat = (
        opf.groupby("category")
        .agg(
            orders=("order_id", "count"),
            gmv=("gross_value", "sum"),
            refunds=("refund_amount", "sum"),
            disputes=("dispute_amount", "sum"),
            margin=("realized_contribution_margin_proxy", "sum"),
        )
        .sort_values("gmv", ascending=False)
    )
    cat["refund_rate"] = cat.refunds / cat.gmv
    cat["margin_rate"] = cat.margin / cat.gmv
    elec, fash = cat.loc["Electronics"], cat.loc["Fashion"]
    home = cat.loc["Home"]

    geo = (
        opf.merge(buyers_raw, on="buyer_id")
        .groupby("region")
        .agg(gmv=("gross_value", "sum"), margin=("realized_contribution_margin_proxy", "sum"))
    )
    geo["margin_rate"] = geo.margin / geo.gmv
    geo = geo.sort_values("gmv", ascending=False)

    tiers = score.governance_priority_tier.value_counts()
    high_n = int(tiers.get("High", 0))
    high_gmv_share = score[score.governance_priority_tier == "High"].gmv.sum() / score.gmv.sum()
    g = score.sort_values("gmv", ascending=False)
    top10 = g.head(10).gmv.sum() / g.gmv.sum()
    top25 = g.head(25).gmv.sum() / g.gmv.sum()
    top100 = g.head(100).gmv.sum() / g.gmv.sum()
    high_quality_n = int(
        score[(score.governance_priority_tier == "High") & (score.main_risk_driver == "seller_quality")].shape[0]
    )
    seller_loss = opf.groupby("seller_id").realized_contribution_margin_proxy.sum().sort_values()
    worst20_share = seller_loss.head(20).sum() / seller_loss.sum()

    rtier = ors.order_risk_tier.value_counts()
    opf["adverse"] = ((opf.refund_amount > 0) | (opf.dispute_amount > 0) | (opf.chargeback_loss_proxy > 0)).astype(int)
    inc = (
        ors[["order_id", "order_risk_tier"]]
        .merge(opf[["order_id", "adverse"]], on="order_id")
        .groupby("order_risk_tier")
        .adverse.mean()
    )

    bmean = buyer.order_risk_proxy.mean()
    bp95 = buyer.order_risk_proxy.quantile(0.95)
    bp99 = buyer.order_risk_proxy.quantile(0.99)
    t55 = threshold_curve.loc[55]
    t65 = threshold_curve.loc[65]

    fraud = scen.loc["fraud_control_improvement"]
    quality = scen.loc["seller_quality_improvement"]
    subs = scen.loc["subsidy_tightening"]
    down = scen.loc["downside_high_risk_deterioration"]
    mc_fraud = mc.loc["fraud_control_improvement"]
    # Since probabilities are non-negative, the maximum across scenarios is 0
    # if and only if every scenario's modeled probability of a positive
    # contribution margin is 0 — so this single derived value backs both the
    # "zero in any scenario" and "zero in every scenario" claims below.
    mc_prob_positive_max = float(mc["prob_cm_positive"].max())
    # The scenario baseline is a trailing run-rate window, not the cumulative
    # 24-month figures used elsewhere in this report. Read the window length
    # from the pipeline's own recorded output (scenario_top_risk_exposure.csv)
    # rather than hardcoding it, so the disclosure can never silently drift
    # out of sync with whatever window actually produced the loaded data.
    scenario_baseline_months = int(scen_exposure["baseline_months_used"])
    scenario_horizon_months = int(scen_exposure["horizon_months"])

    # ---- Document skeleton -------------------------------------------------
    doc = BaseDocTemplate(
        str(OUT / "marketplace-command-center-report.pdf"),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=1.55 * cm,
        bottomMargin=1.65 * cm,
        title="Marketplace Profitability, Fraud & Seller Quality",
        author="Marketplace Intelligence and Analytics",
        subject="Marketplace analytical report",
    )
    body = Frame(MARGIN, 1.5 * cm, FW, PAGE_H - 3.05 * cm, id="body")
    cover_frame = Frame(2.35 * cm, 2.0 * cm, PAGE_W - 4.1 * cm, PAGE_H - 4 * cm, id="cover")
    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], onPage=cover_canvas),
            PageTemplate(id="body", frames=[body], onPage=footer),
        ]
    )

    def after_flowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        name = flowable.style.name
        if name == "SectionH1":
            self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))
        elif name == "SubH":
            self.notify("TOCEntry", (1, flowable.getPlainText(), self.page))

    doc.afterFlowable = types.MethodType(after_flowable, doc)

    toc = TableOfContents()
    toc.levelStyles = [ST["TOC0"], ST["TOC1"]]

    story = []

    # ===================================================================
    # COVER
    # ===================================================================
    story += [
        Spacer(1, 3.6 * cm),
        Paragraph("MARKETPLACE PERFORMANCE REVIEW", ST["CoverEyebrow"]),
        Spacer(1, 9),
        Paragraph("Marketplace Profitability, Fraud &amp; Seller Quality", ST["CoverTitle"]),
        Paragraph(
            "A decision report on growth quality, value leakage and the controls "
            "that recover the most contribution margin",
            ST["CoverSub"],
        ),
        Spacer(1, 1.15 * cm),
    ]
    meta = [
        [Paragraph("ANALYSIS PERIOD", ST["MetaLabel"]), Paragraph("SCOPE", ST["MetaLabel"])],
        [
            Paragraph("March 2024 to February 2026 (24 months)", ST["MetaValue"]),
            Paragraph(f"{n_orders:,} orders  |  {n_sellers:,} sellers  |  {n_buyers:,} buyers", ST["MetaValue"]),
        ],
        [Paragraph("PREPARED FOR", ST["MetaLabel"]), Paragraph("PREPARED BY", ST["MetaLabel"])],
        [
            Paragraph("CFO and Marketplace Executive Committee", ST["MetaValue"]),
            Paragraph("Marketplace Intelligence and Analytics", ST["MetaValue"]),
        ],
    ]
    mt = Table(meta, colWidths=[8.0 * cm, 7.0 * cm])
    mt.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, 0), 1.5, ACCENT),
                ("LINEABOVE", (0, 2), (-1, 2), 0.6, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story += [mt, Spacer(1, 6.2 * cm), PageBreak()]

    # ===================================================================
    # TABLE OF CONTENTS
    # ===================================================================
    story += [
        Paragraph("CONTENTS", ST["Kicker"]),
        Paragraph("Table of contents", ST["PlainH1"]),
        Spacer(1, 10),
        toc,
        PageBreak(),
    ]

    # ===================================================================
    # 1. EXECUTIVE SUMMARY
    # ===================================================================
    story += [
        Paragraph("SECTION 1", ST["Kicker"]),
        h1("Executive summary"),
        deck(
            "The marketplace is scaling into a contribution loss. Growth is real, but it "
            "is not converting into protected economics, and the controls that exist today "
            "mitigate the loss rather than close it."
        ),
    ]
    story += [
        metric_strip(
            [
                metric_card(money(gmv, 1), "GMV, 24-month period"),
                metric_card(money(margin), "Realized contribution margin", True),
                metric_card(money(leakage), "Refund, dispute and chargeback leakage", True),
                metric_card(f"{high_n}", "High-priority sellers"),
            ]
        ),
        Spacer(1, 10),
    ]
    story += [
        p(
            f"Across the 24 months from March 2024 to February 2026 the platform processed "
            f"{n_orders:,} orders worth {money(gmv)} in gross merchandise value. That volume "
            f"earned {money(commission)} of commission at an effective take rate of "
            f"{pct(kv['take_rate'])}. It also generated {money(refunds)} of refunds, "
            f"{money(disputes)} of disputed value and {money(chargebacks)} of chargeback loss, "
            f"alongside {money(subsidy)} of promotional subsidy. After those costs the realized "
            f"contribution margin is {money(margin)}, a margin rate of {pct(margin_rate)} on GMV. "
            f"The marketplace loses money on its merchandise economics, and it has done so in every "
            f"one of the {n_months} months in scope."
        ),
        p(
            f"The central problem is not weak revenue. It is that post-order leakage is larger than "
            f"the revenue pool it sits against. Refunds alone ({money(refunds)}) very nearly equal "
            f"total commission ({money(commission)}). Add disputes and chargebacks and the combined "
            f"leakage of {money(leakage)} is more than double commission before a single dollar of "
            f"subsidy or operating cost is counted. No realistic increase in take rate closes a gap "
            f"of that shape. The economics have to be repaired on the cost side, and most of that "
            f"cost is the value returned, disputed and charged back after the sale."
        ),
        p(
            f"The materiality test is severe. To reach break-even on this 24-month period without "
            f"changing volume, the marketplace would need {money(break_even_gap)} of contribution "
            f"improvement. That is equivalent to an additional {pct(take_rate_lift_needed)} of GMV "
            f"in take-rate yield or a {pct(leakage_reduction_needed, 0)} reduction in the current "
            f"refund, dispute and chargeback pool. Those are not tuning adjustments; they are "
            f"program-level economics. Leadership should therefore treat the report as a recovery "
            f"case, not as a KPI refresh."
        ),
        pull(
            "Refunds alone nearly equal all commission earned. Combined leakage is more than "
            "double the revenue pool. Growth cannot out-run a gap of that shape."
        ),
        p(
            f"The loss is concentrated, which is the most useful fact in this report. Electronics "
            f"alone accounts for {money(elec.gmv)} of GMV ({pct(elec.gmv / gmv, 0)} of the platform) "
            f"and {money(elec.margin)} of contribution loss ({pct(elec.margin / margin, 0)} of the "
            f"total). Fashion carries the highest value-based refund rate at {pct(fash.refund_rate)}. "
            f"On the seller side, {high_n} of {n_sellers:,} sellers are flagged High priority for "
            f"governance and they control {pct(high_gmv_share, 0)} of GMV, while the twenty worst "
            f"sellers by contribution account for {pct(worst20_share, 0)} of the total loss. The "
            f"exposure is large but it is addressable through a finite set of named queues rather "
            f"than a platform-wide rebuild."
        ),
        p(
            f"The controls modeled in this analysis help, but none of them reach break-even on their "
            f"own. The strongest single intervention, tighter fraud and review controls, improves "
            f"modeled contribution margin by {money(fraud.contribution_margin_change_vs_baseline)} "
            f"against the run-rate baseline and avoids "
            f"{money(fraud.leakage_avoided_vs_baseline)} of leakage. A retrospective review policy "
            f"that inspects {pct(rec.review_rate)} of orders at risk score {rec.recommended_threshold:.0f} "
            f"produces {money(rec.net_benefit)} of in-sample net benefit. Across every scenario, "
            f"including the most favorable, the modeled probability of a positive contribution margin "
            f"is zero. These are mitigations. They buy time and reduce the bleed. They do not, by "
            f"themselves, make the marketplace profitable."
        ),
        KeepTogether(
            [
                h2("What leadership should decide"),
                p(
                    "Four decisions follow directly from the evidence. They are sequenced so that the "
                    "cheapest and most reversible control comes first and the structural change comes "
                    "last, after the diagnostics that justify it are in place."
                ),
            ]
        ),
    ]
    decisions = [
        (
            "1",
            "Make contribution margin the growth gate.",
            f"Commission of {money(commission)} is outweighed by {money(pool)} of subsidy and "
            f"post-order leakage, and every month is contribution-negative. No growth initiative "
            f"should be approved without a demonstrated, non-dilutive effect on contribution margin.",
            "CFO and Commercial, approve within 30 days",
        ),
        (
            "2",
            "Run a category-specific recovery program led by Electronics and Fashion.",
            f"Electronics drives {pct(elec.margin / margin, 0)} of the loss and needs absolute value "
            f"recovery; Fashion carries the highest refund rate at {pct(fash.refund_rate)} and needs "
            f"rate reduction. The two require different interventions and different targets.",
            "Marketplace GM and Category, mobilize within 30 days",
        ),
        (
            "3",
            "Operate finite seller and order intervention queues.",
            f"{high_n} sellers require high-priority governance and the order risk score at threshold "
            f"{rec.recommended_threshold:.0f} reviews {pct(rec.review_rate)} of orders for "
            f"{money(rec.net_benefit)} of in-sample net benefit. Both queues are small enough to own.",
            "Risk Operations and Seller Management, validate and launch within 60 days",
        ),
        (
            "4",
            "Treat fraud control as mitigation, not as the profitability solution.",
            f"Fraud control is the strongest modeled lever at "
            f"{money(fraud.contribution_margin_change_vs_baseline)} of margin improvement, but no "
            f"scenario reaches break-even. Structural commercial repair must run in parallel.",
            "CFO, Risk and Strategy, fold into the 90-day plan",
        ),
    ]
    rows = [["", "Decision", "Evidence and owner"]]
    for num, dtxt, ev, owner in decisions:
        rows.append(
            [
                f"<b>{num}</b>",
                f"<b>{dtxt}</b>",
                # Inline <font> tags need a literal hex string (reportlab markup
                # can't reference the ACCENT Color object) — keep in sync with ACCENT above.
                f"{ev}<br/><font color='#5B54E0'><b>{owner}</b></font>",
            ]
        )
    story += [KeepTogether(table(rows, [0.8 * cm, 5.2 * cm, FW - 6.0 * cm], header=True)), Spacer(1, 8)]
    story += [
        p(
            f"The economic boundary is explicit. The best modeled contribution-margin "
            f"improvement is {money(fraud.contribution_margin_change_vs_baseline)} and the "
            f"probability of a positive margin in any scenario is {pct(mc_prob_positive_max)}. The board should "
            f"approve a recovery program and a controlled policy validation. It should not read "
            f"the synthetic values as a budget, a forecast or a profitability claim. The evidence "
            f"that would change the conclusion is specific: governed real economics, holdout score "
            f"performance, calibrated intervention costs and post-pilot proof that avoided leakage "
            f"survives customer-friction and supply-retention effects."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 2. CONTEXT AND OBJECTIVES
    # ===================================================================
    story += [
        Paragraph("SECTION 2", ST["Kicker"]),
        h1("Context and objectives"),
        deck("Why this review exists, who it is for, and the decision it is built to support."),
        p(
            "Marketplaces are graded on gross merchandise value because GMV is visible, easy to "
            "compare and easy to grow. It is also a poor proxy for whether the business is healthy. "
            "A marketplace can grow GMV quickly while losing money on every incremental order if "
            "refunds, disputes, chargebacks and promotional subsidy rise in step with volume. The "
            "purpose of this review is to look past the topline and ask a narrower question: when "
            "the platform sells one more dollar of merchandise, does it keep any of it?"
        ),
        p(
            f"The answer, on this data, is no. The platform retains {money(margin_rate * 1e6, 2)} of "
            f"contribution for every dollar of GMV, which is to say it loses "
            f"{pct(abs(margin_rate))} of GMV after subsidy and post-order leakage. The review traces "
            f"that result to its sources, separates the part that is structural from the part that is "
            f"operational, and identifies where intervention recovers the most value per unit of "
            f"effort."
        ),
        h2("Primary reader and decision"),
        p(
            "The report is written for the CFO and the Marketplace Executive Committee, with Risk, "
            "Category, Seller Operations and Customer Experience as the action owners. The decision "
            "it supports is whether to approve a sequenced recovery program, and how to prioritize "
            "the controls inside it, before committing further capital to volume growth. Every "
            "finding is therefore tied to an owner and a timeframe rather than left as an "
            "observation."
        ),
        h2("Scope and boundaries"),
        p(
            f"The analysis covers {n_orders:,} orders, {n_sellers:,} sellers and {n_buyers:,} buyers "
            f"across eight merchandise categories and five buyer regions, over the 24 months ending "
            f"February 2026. It covers the economics of those orders, the risk concentrated in them, "
            f"the sellers who generate them and the scenarios that change them. It does not cover "
            f"logistics network design, marketing channel attribution or pricing elasticity, each of "
            f"which would require data and methods outside this workflow."
        ),
        pull(
            "The data is synthetic. The report demonstrates decision architecture and governance "
            "discipline. It does not establish real-world causality."
        ),
        p(
            "One boundary deserves emphasis at the start rather than buried in an appendix. The "
            "underlying data is synthetic, generated to exercise the workflow end to end. The "
            "scores are interpretable prioritization indices, not calibrated probabilities. The "
            "scenarios are assumption-driven stress tests, not forecasts. The review policy is "
            "retrospective and in-sample. What the report demonstrates is a governed analytical "
            "process and the quality of the decisions it can support. It does not, and is not "
            "intended to, describe a real marketplace or stand in for a management profit and loss "
            "statement."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 3. DATA AND METHODOLOGY
    # ===================================================================
    story += [
        Paragraph("SECTION 3", ST["Kicker"]),
        h1("Data and methodology"),
        deck(
            "A governed workflow connects realized economics, pre-outcome risk and "
            "operational prioritization, with a release gate controlling what may be claimed."
        ),
        p(
            "The workflow is built in five layers, each answering a different question and feeding a "
            "different decision. The separation matters because the layers measure different things "
            "and must not be reconciled to each other casually. Realized economics describe what "
            "actually happened to margin. Risk scores describe what might happen before the outcome "
            "is known. Seller governance translates both into who to act on. Scenarios test what "
            "changes the result. Validation controls what the organization is allowed to say about "
            "any of it."
        ),
        table(
            [
                ["Layer", "Primary question", "Core outputs", "Decision use"],
                [
                    "Economics",
                    "Does growth survive leakage?",
                    "GMV, protected value, realized contribution margin",
                    "Growth gate and category targets",
                ],
                [
                    "Risk",
                    "Where are adverse outcomes concentrated?",
                    "Order risk, buyer risk, fraud exposure",
                    "Review and preventive controls",
                ],
                [
                    "Seller governance",
                    "Which sellers require intervention?",
                    "Quality, fragility and governance priority",
                    "Coaching, audit, reserves, payouts",
                ],
                [
                    "Scenarios",
                    "Which actions improve economics?",
                    "Deterministic and Monte Carlo stress tests",
                    "Sequence mitigation, quantify trade-offs",
                ],
                [
                    "Validation",
                    "Can the output be published responsibly?",
                    "Metric contracts, schema checks, release gate",
                    "Control the claims and release state",
                ],
            ],
            [2.5 * cm, 3.7 * cm, 4.7 * cm, 4.6 * cm],
        ),
        Spacer(1, 9),
        h2("How to read the core metrics"),
        p(
            "<b>Realized contribution margin</b> is commission less subsidy, refunds, disputes and "
            "a chargeback-loss proxy. It is a deliberately conservative gross-leakage view of unit "
            "economics, not accounting profit, and it excludes fulfillment, platform and overhead "
            "costs that a full profit and loss statement would carry. Because it omits those costs, "
            "it understates the true loss rather than overstating it."
        ),
        p(
            "<b>Risk-adjusted value</b> and <b>expected margin after risk</b> are pre-outcome "
            "underwriting measures. They discount value by modeled expected loss before any real "
            "refund or dispute occurs, and they should not be reconciled directly to realized "
            "contribution margin. The gap between GMV and risk-adjusted value is a measure of "
            "modeled exposure, not of money already lost."
        ),
        p(
            "<b>Scores</b> are interpretable indices on a 0 to 100 scale, each carrying a main risk "
            "driver and a recommended action. They rank and route; they are not calibrated event "
            "probabilities and must be validated before any automated decision relies on them. "
            "<b>Scenarios</b> compare assumption-driven interventions against a modeled run-rate "
            "baseline, and the Monte Carlo ranges reflect uncertainty in those assumptions rather "
            "than forecast confidence."
        ),
        h2("Pipeline integrity and release position"),
        p(
            f"Every chart, table and figure in this report is generated by Python from the processed "
            f"data tables, and the document can be rebuilt end to end. Before publication the output "
            f"passes a release gate that checks metric governance, schema contracts and analytical "
            f"consistency. The current release state is <b>{release['release_state']}</b> with "
            f"{int(release['blocker_count'])} blockers and {int(release['limitation_count'])} "
            f"recorded limitations. That state permits use as a public decision-support "
            f"demonstration and explicitly withholds committee-grade and production status."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 4. ANALYTICAL FRAMEWORK
    # ===================================================================
    story += [
        Paragraph("SECTION 4", ST["Kicker"]),
        h1("Analytical framework"),
        deck(
            "The diagnosis follows the money: from the topline gap, through the leakage "
            "bridge, into the categories, sellers, orders and buyers that produce it, and "
            "out to the scenarios that could change it."
        ),
        p(
            "The findings that follow are ordered to build an argument rather than to list metrics. "
            "They begin with the gap between reported growth and protected value, because that gap is "
            "the reason the review exists. They move to the unit-economics bridge that shows where "
            "the revenue pool is consumed. They then localize the loss in the dimensions a manager "
            "can actually act on: category, seller, order and buyer. They close with geography and "
            "correlation, which rule out easy explanations, and with the scenario and policy "
            "economics that test what intervention is worth."
        ),
        p(
            "Each section pairs the evidence with a named owner and a timeframe. The intent is that a "
            "reader can move from a chart to a decision without an intermediate translation step. "
            "Where a finding limits what can be claimed, that limit is stated next to the finding "
            "rather than deferred, so the argument never runs ahead of the evidence."
        ),
        table(
            [
                ["Diagnostic question", "Section", "Primary evidence"],
                [
                    "Is growth converting into protected value?",
                    "5  Growth quality",
                    "GMV vs risk-adjusted value; monthly margin",
                ],
                ["Where is the revenue pool consumed?", "6  Unit economics", "Leakage bridge; leakage composition"],
                [
                    "Which categories drive the loss?",
                    "7  Category exposure",
                    "Refund rate, economics matrix, risk heatmap",
                ],
                [
                    "Which sellers require intervention?",
                    "8  Seller governance",
                    "Governance tiers, portfolio matrix, concentration",
                ],
                [
                    "Where is order and buyer risk?",
                    "9  Order and buyer risk",
                    "Score distribution, tier separation, funnel",
                ],
                ["Do geography or correlation explain it?", "10  Structure", "Regional economics; correlation matrix"],
                ["Are newer sellers safer?", "11  Cohorts", "Governance priority by onboarding quarter"],
                [
                    "What intervention is worth funding?",
                    "12  Scenario and policy",
                    "Monte Carlo ranges, scenario bridge, threshold curve",
                ],
            ],
            [6.0 * cm, 4.0 * cm, FW - 10.0 * cm],
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 5. GROWTH QUALITY
    # ===================================================================
    story += [
        Paragraph("SECTION 5  |  FINDINGS", ST["Kicker"]),
        h1("Growth quality and the protection gap"),
        deck("Topline expansion is real and steady. It is not converting into value the platform gets to keep."),
        p(
            f"Monthly GMV rose from roughly {money(monthly.gmv.iloc[0], 1)} at the start of the "
            f"period to about {money(monthly.gmv.iloc[-1], 1)} by February 2026, a clean upward "
            f"trend with the expected seasonal movement. Risk-adjusted value, which discounts each "
            f"order by its modeled expected loss, tracks the same path but sits persistently below "
            f"it. The space between the two lines is the protection gap, and it does not close as the "
            f"business scales."
        ),
        fig(
            "01_growth_quality_gap.png",
            "Monthly GMV and risk-adjusted value, March 2024 to February 2026. The shaded band is the protection gap.",
        ),
        p(
            f"The gap is stable in percentage terms and growing in dollars. It removed "
            f"{pct(gap_first)} of GMV in the first month and {pct(gap_last)} in the last, averaging "
            f"{pct(gap_avg)} across the period. Because the percentage holds while volume rises, the "
            f"absolute exposure climbs with every increment of growth. This is the first reason GMV "
            f"is a misleading scorecard here: each new dollar of merchandise arrives with the same "
            f"proportional risk attached, so faster growth means a larger control problem rather than "
            f"a smaller one."
        ),
        p(
            f"Realized margin tells the harder version of the same story. Every one of the {n_months} "
            f"months in scope is contribution-negative. The monthly loss widened from "
            f"{thousands(first_loss)} early in the period to {thousands(last_loss)} at the end, "
            f"moving broadly in line with volume rather than improving with scale."
        ),
        fig(
            "02_monthly_margin_variance.png",
            "Monthly realized contribution margin. The series is negative in all 24 months and "
            "deepens as volume grows.",
        ),
        p(
            "If there were genuine operating leverage, the margin line would flatten or turn up as "
            "fixed costs spread across more orders. It does not. A stable take rate against unchanged "
            "leakage intensity reproduces the same negative unit economics at larger scale. The "
            "implication for the growth function is direct: until the protection gap and the monthly "
            "loss respond to a control, additional volume compounds the problem."
        ),
        pull(
            "The protection gap holds near 10.5% of GMV while volume rises. Stable percentage, "
            "growing dollars. Growth is scaling the loss, not diluting it."
        ),
        p(
            "<b>Owner and action.</b> CFO and Commercial, within 30 days. Add protected value and the "
            "monthly protection gap to the growth approval scorecard, and require every growth "
            "proposal to show a stable or improving contribution margin after risk and leakage before "
            "it is funded."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 6. UNIT ECONOMICS
    # ===================================================================
    story += [
        Paragraph("SECTION 6  |  FINDINGS", ST["Kicker"]),
        h1("Unit economics and where the money goes"),
        deck(
            "The revenue pool is consumed before structural costs are even considered. "
            "Refunds are the single largest controllable loss."
        ),
        p(
            f"The bridge from commission to contribution margin makes the shape of the problem "
            f"unavoidable. Commission revenue of {money(commission)} is the only inflow. Against it "
            f"sit {money(subsidy)} of promotional subsidy, {money(refunds)} of refunds, "
            f"{money(disputes)} of disputed value and {money(chargebacks)} of chargeback loss. The "
            f"result is a {money(margin)} contribution loss."
        ),
        fig(
            "03_leakage_waterfall.png",
            "Bridge from commission revenue to realized contribution margin. Each red bar is a "
            "deduction; the final bar is the net loss.",
        ),
        p(
            f"The decisive comparison is refunds against commission. Refunds of {money(refunds)} "
            f"alone are {pct(refunds / commission, 0)} of all commission earned. Before subsidy and "
            f"chargebacks are added, refunds and disputes together already exceed the entire revenue "
            f"pool. This is why a revenue-side fix cannot work in isolation. To close the gap on "
            f"commission alone, the platform would need to roughly triple its take rate, which no "
            f"competitive marketplace can do without losing the supply and demand that generate the "
            f"volume in the first place. The repair has to happen on the leakage side."
        ),
        p(
            "Splitting the subsidy and post-order leakage pool into its components shows where the "
            "controllable money sits. Refunds are the largest slice, followed by disputes, then "
            "chargebacks, with subsidy the smallest of the four."
        ),
        fig("04_leakage_composition.png", "Composition of the combined subsidy and post-order leakage pool."),
        p(
            f"Refunds represent {pct(refunds / pool, 0)} of the combined pool and disputes a further "
            f"{pct(disputes / pool, 0)}. The practical consequence is that the largest recoverable "
            f"loss is a returns problem, not a fraud problem. Returns are driven by product quality, "
            f"listing accuracy, fulfillment reliability and refund policy, and they respond to "
            f"controls that sit with Category and Customer Experience rather than with the fraud "
            f"team. A program that funds only fraud controls would leave the single biggest loss "
            f"pool untouched."
        ),
        pull(
            "Refunds are the largest single loss and they are a returns problem, not a fraud "
            "problem. Fraud controls alone leave the biggest pool untreated."
        ),
        p(
            "<b>Owner and action.</b> Two workstreams under one CFO-owned economic bridge. Customer "
            "Experience and Category own refund-value reduction targets by category and by top-loss "
            "seller within 60 days. Finance and the Marketplace GM own a structural margin review of "
            "fees, take rate, category mix and policy cost within 45 days. Running them separately "
            "but reporting them on one bridge keeps the accountability clear without letting either "
            "claim credit for the other's effect."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 7. CATEGORY EXPOSURE
    # ===================================================================
    story += [
        Paragraph("SECTION 7  |  FINDINGS", ST["Kicker"]),
        h1("Category exposure"),
        deck("The loss is concentrated by category, and the categories that matter most need opposite interventions."),
        p(
            f"Refund pressure is not uniform. Measured as refund value over category GMV, Fashion "
            f"carries the highest rate at {pct(fash.refund_rate)}, with Electronics close behind at "
            f"{pct(elec.refund_rate)}. The lowest rate sits in Grocery. The ranking matters because "
            f"it tells two different categories to do two different things."
        ),
        fig("05_refund_rate_by_category.png", "Refund value as a share of category GMV, by merchandise category."),
        p(
            f"Fashion has a rate problem. Its refund rate is the highest on the platform but it sits "
            f"on a smaller base of {money(fash.gmv)} of GMV, so the right target there is reducing "
            f"the rate through sizing accuracy, fit information and returns policy. Electronics is the "
            f"opposite case. Its rate is high but its scale is enormous, and that scale is what makes "
            f"it the dominant driver of the absolute loss."
        ),
        fig(
            "06_category_economics_matrix.png",
            "Category GMV, contribution margin rate and order volume, on a single view.",
        ),
        p(
            f"Electronics contributes {money(elec.gmv)} of GMV, which is {pct(elec.gmv / gmv, 0)} of "
            f"the platform, and {money(elec.margin)} of contribution loss, which is "
            f"{pct(elec.margin / margin, 0)} of the total. A modest proportional improvement in "
            f"Electronics therefore recovers more dollars than a large improvement anywhere else. "
            f"Home is a distant second at {money(home.gmv)} of GMV, and the remaining categories are "
            f"smaller still. The math points to an executive-sponsored Electronics program with a "
            f"target denominated in avoided dollars, run alongside a Fashion program with a target "
            f"denominated in refund-rate reduction."
        ),
        p(
            "Category risk is also multi-dimensional, and a single blended score would hide the "
            "control that matters. Standardizing refund, dispute, subsidy and margin-fragility "
            "indicators by category produces materially different rankings depending on which "
            "indicator is in view."
        ),
        fig(
            "07_category_risk_heatmap.png",
            "Standardized category risk indicators. Darker cells are higher relative risk.",
        ),
        p(
            "Toys stands out on disputes, Grocery combines lower refunds with higher subsidy and "
            "fragility, and Electronics and Fashion lead on refund intensity. The operational "
            "reading is that each category needs its own control pack rather than a common playbook: "
            "a dispute-cluster investigation where disputes dominate, a subsidy-eligibility review "
            "where subsidy dominates, and a returns-root-cause sprint where refunds dominate."
        ),
        pull(
            "Electronics drives roughly half the loss on scale; Fashion leads on refund rate. "
            "Same symptom, opposite fix. One common target would misallocate the effort."
        ),
        p(
            "<b>Owner and action.</b> Category Directors, within 30 to 90 days. Launch separate "
            "Electronics and Fashion recovery sprints with value and rate targets respectively, and "
            "define category-specific control packs with explicit success measures for the remaining "
            "categories."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 8. SELLER GOVERNANCE
    # ===================================================================
    story += [
        Paragraph("SECTION 8  |  FINDINGS", ST["Kicker"]),
        h1("Seller governance and concentration"),
        deck(
            "The intervention queue is small enough to own by name, and the controls should "
            "scale with economic exposure rather than risk score alone."
        ),
        p(
            f"Of {n_sellers:,} sellers, {high_n} are classified High priority for governance, "
            f"{int(tiers.get('Moderate', 0))} Moderate and {int(tiers.get('Low', 0))} Low. No seller "
            f"reaches the Critical tier. The governance priority index combines quality, fraud, "
            f"margin fragility and concentration signals, and for the High tier the dominant driver "
            f"is seller quality rather than fraud."
        ),
        fig("08_seller_governance_distribution.png", "Seller count by governance priority tier."),
        p(
            f"A queue of {high_n} sellers is operationally finite. It can be assigned, owned and "
            f"reviewed on a weekly cadence, with each seller carrying a named owner, a recommended "
            f"action, a due date and an outcome measure. The absence of any Critical seller is "
            f"reassuring at the portfolio level but it does not remove severe order-level risk, which "
            f"concentrates differently and is handled through the review queue rather than seller "
            f"governance. The two queues are complementary and should not be merged."
        ),
        p(
            "Risk and economic scale do not coincide cleanly, which is the reason a single threshold "
            "misroutes effort. Plotting each seller's GMV against its quality-risk score shows "
            "several high-risk sellers carrying meaningful volume, while the single largest seller by "
            "GMV sits only at Moderate risk."
        ),
        fig(
            "09_seller_portfolio_matrix.png",
            "Seller GMV against quality-risk score. Bubble position separates economic scale from risk severity.",
        ),
        p(
            f"A risk-only rule would chase small sellers with high scores and ignore large sellers "
            f"with moderate scores and large dollar exposure. A volume-only rule would do the "
            f"reverse. The portfolio is concentrated enough to justify exposure-based controls: the "
            f"ten largest sellers hold {pct(top10)} of GMV, the top 25 hold {pct(top25)}, and half "
            f"of all GMV sits with the top 100 sellers ({pct(top100)})."
        ),
        fig("10_seller_concentration_curve.png", "Cumulative share of GMV by seller, largest first."),
        KeepTogether(
            p(
                f"That curve is concentrated but not fragile. No handful of sellers can sink the "
                f"platform on its own, yet enough value sits in the top decile to make graduated, "
                f"exposure-weighted controls worthwhile. The twenty worst sellers by contribution "
                f"already account for {pct(worst20_share)} of the total loss, and {high_quality_n} of "
                f"the {high_n} High-priority sellers are driven primarily by seller-quality signals. "
                f"That combination matters: the queue is not mostly a fraud blacklist, and the right "
                f"response is a seller-performance operating model with reserves, audits and payout "
                f"controls reserved for accounts where quality issues create material dollar exposure."
            )
        ),
        pull(
            f"{high_n} High-priority sellers, no Critical sellers, and the worst 20 sellers carry "
            f"{pct(worst20_share, 0)} of the loss. The queue is finite and the controls can be "
            f"exposure-weighted."
        ),
        p(
            "<b>Owner and action.</b> Seller Management and Seller Risk. Assign every High-priority "
            "seller an owner, action, due date and outcome measure immediately, and within 60 days "
            "scale reserves, audit frequency and payout controls with each seller's gross value "
            "exposure rather than with risk score alone."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 9. ORDER AND BUYER RISK
    # ===================================================================
    story += [
        Paragraph("SECTION 9  |  FINDINGS", ST["Kicker"]),
        h1("Order and buyer risk"),
        deck(
            "The order risk score separates outcomes directionally and supports a bounded "
            "review queue, but manual review is a capacity decision rather than a complete "
            "prevention strategy."
        ),
        p(
            f"Order risk scores cluster in the middle of the range, with {int(rtier.get('High', 0)):,} "
            f"orders in the High tier and {int(rtier.get('Moderate', 0)):,} in Moderate. The "
            f"recommended review threshold of score {rec.recommended_threshold:.0f} selects "
            f"{pct(rec.review_rate)} of orders, and because the score density is highest near that "
            f"threshold, small threshold changes move review demand sharply."
        ),
        fig(
            "11_order_risk_distribution.png",
            "Distribution of order risk scores, with the recommended review threshold marked.",
        ),
        p(
            "The score earns its place by separating outcomes monotonically. Observed adverse-event "
            "incidence, defined as any refund, dispute or chargeback on the order, rises cleanly with "
            "the tier."
        ),
        fig("12_risk_tier_separation.png", "Share of orders with an adverse outcome, by order risk tier."),
        p(
            f"Adverse incidence climbs from {pct(inc.get('Low', 0))} in the Low tier to "
            f"{pct(inc.get('Moderate', 0))} in Moderate, {pct(inc.get('High', 0))} in High and "
            f"{pct(inc.get('Critical', 0))} in the small Critical tier. The separation is real and "
            f"useful for prioritization. It is also not clean enough for automatic rejection: the "
            f"overlap between Moderate and High means a meaningful share of adverse outcomes sits in "
            f"the tier most orders fall into, so a blanket reject rule would either miss too much or "
            f"block too much legitimate volume. The score routes attention; it does not replace "
            f"judgment."
        ),
        p(
            f"The funnel makes the capacity trade-off explicit. Reviewing the {pct(rec.review_rate)} "
            f"of orders above the threshold captures {pct(rec.recall)} of observed adverse outcomes "
            f"at a precision of {pct(rec.precision)}."
        ),
        fig("13_review_funnel.png", "Operational review funnel at the recommended score threshold."),
        p(
            f"Most adverse outcomes therefore remain outside manual review. That is not a failure of "
            f"the score; it is a property of any capacity-limited manual process. The conclusion is "
            f"that manual review should be reserved for the highest-value cases and paired with "
            f"automated, upstream controls in payments, category policy and seller management that "
            f"cover the broader order base. The recommended policy generates {money(rec.net_benefit)} "
            f"of in-sample net benefit, but it is retrospective, and it must be validated on a "
            f"later-period holdout before any capacity is committed to it."
        ),
        p(
            f"Threshold sensitivity is large enough to require an operating decision, not just a model "
            f"decision. Moving the threshold down to 55 would review {pct(t55.review_rate)} of orders "
            f"and capture {pct(t55.recall)} of adverse outcomes, but it more than doubles review "
            f"demand versus the recommended threshold. Moving it up to 65 would review only "
            f"{pct(t65.review_rate)} of orders, but recall falls to {pct(t65.recall)}. The right "
            f"threshold therefore depends on staffing capacity, review unit cost, customer friction "
            f"and the financial value of each avoided event. The analytics can rank the trade-off; "
            f"leadership must set the operating constraint."
        ),
        p(
            f"Buyer risk supports a narrower, targeted control. The buyer behavior risk distribution "
            f"has a defined upper tail rather than a uniformly elevated population: the mean sits "
            f"around {bmean:.0f}, the 95th percentile near {bp95:.0f} and the 99th near {bp99:.0f}."
        ),
        fig("14_buyer_risk_distribution.png", "Distribution of buyer behavior risk across the buyer base."),
        p(
            "A distribution with a thin tail argues for step-up verification on a small, high-risk "
            "group rather than broad friction applied to the whole customer base. Broad restrictions "
            "would tax the large majority of low-risk buyers to reach the few who matter, and the "
            "shape of this distribution does not justify that cost."
        ),
        pull(
            "Reviewing a quarter of orders captures roughly a third of adverse outcomes. Manual "
            "review is a high-value scalpel, not full coverage. Prevention has to run upstream too."
        ),
        p(
            "<b>Owner and action.</b> Risk Operations, Payments and Fraud Product, 30 to 90 days. "
            "Set a daily review-capacity ceiling, validate thresholds 55, 60 and 65 on holdout data "
            "before deployment, pair manual review with upstream automated rules, and pilot step-up "
            "verification for the upper buyer-risk tail with explicit customer-friction monitoring."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 10. STRUCTURE: GEOGRAPHY AND CORRELATION
    # ===================================================================
    story += [
        Paragraph("SECTION 10  |  FINDINGS", ST["Kicker"]),
        h1("Structure: geography and correlation"),
        deck(
            "Geography does not explain the loss, and the correlation structure confirms "
            "that loss events, not revenue mix, drive margin."
        ),
        p(
            f"It would be convenient if the loss concentrated in one region that could be fixed or "
            f"exited. It does not. The South is the largest region at {money(geo.gmv.iloc[0])} of "
            f"GMV and the smallest, Central, at {money(geo.gmv.iloc[-1])}, but every region carries a "
            f"negative contribution margin rate, ranging only from {pct(geo.margin_rate.max())} to "
            f"{pct(geo.margin_rate.min())}."
        ),
        fig(
            "15_geography_value_and_margin.png", "Regional GMV bars and contribution margin rate line, by buyer region."
        ),
        p(
            "The narrow spread is the point. Because every region loses money at a similar rate, the "
            "loss is structural to the platform rather than localized to a market. Regional analysis "
            "is still useful as a diagnostic cut within category and seller actions, but it cannot "
            "substitute for the platform-wide recovery program. There is no region to exit that would "
            "fix the economics."
        ),
        p(
            "The correlation structure points the diagnosis at the right variables. Realized "
            "contribution margin is most strongly and negatively related to refund value, then "
            "dispute value, then chargeback loss, with gross value and commission showing weaker "
            "relationships."
        ),
        fig("16_correlation_matrix.png", "Order-level correlations among economic and risk measures."),
        p(
            "This confirms with the full order base what the leakage bridge showed in aggregate: "
            "margin is destroyed by loss events, not by the level of revenue or subsidy on an order. "
            "It also clarifies the measurement discipline for the recovery program. Operational "
            "indicators such as risk scores and activity counts should be used to route "
            "investigation, but the outcome the program is held to should be avoided loss value and "
            "realized contribution margin, because those are the quantities the correlation "
            "structure ties directly to the result."
        ),
        pull(
            "Every region loses money at a similar rate. The loss is structural, not regional. "
            "There is no market to exit that fixes the economics."
        ),
        p(
            "<b>Owner and action.</b> Regional Operations and Finance Analytics, within 30 to 60 "
            "days. Use region as a diagnostic cut rather than a primary lever, and anchor every "
            "intervention scorecard to avoided refund, dispute and chargeback value and to realized "
            "contribution margin."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 11. COHORTS
    # ===================================================================
    story += [
        Paragraph("SECTION 11  |  FINDINGS", ST["Kicker"]),
        h1("Seller onboarding cohorts"),
        deck(
            "Recent onboarding cohorts do not show a clean quality improvement, so "
            "onboarding changes cannot yet be credited with fixing seller quality."
        ),
        p(
            "If onboarding standards had tightened effectively, newer seller cohorts would show lower "
            "median governance priority than older ones. They do not. Median governance priority "
            "fluctuates across recent onboarding quarters without a stable downward trend, moving "
            "within a narrow band rather than improving cohort over cohort."
        ),
        fig("17_seller_onboarding_cohort.png", "Median seller governance priority score by onboarding quarter."),
        p(
            "The reading is deliberately cautious. The absence of a clean trend does not prove "
            "onboarding changes have failed, because cohort medians are affected by category mix, "
            "seller type and early-volume effects that are not controlled here. What it does mean is "
            "that the organization cannot yet claim a quality improvement from onboarding on this "
            "evidence. A controlled cohort study that measures first-six-month seller quality while "
            "holding category and seller type constant is required before onboarding is credited as "
            "a lever in the recovery plan."
        ),
        pull(
            "Newer cohorts are not visibly safer. Onboarding cannot be credited as a fix until a "
            "controlled cohort study shows it."
        ),
        p(
            "<b>Owner and action.</b> Seller Onboarding and Analytics, within 90 days. Measure "
            "first-six-month seller quality by cohort, controlling for category and seller type, "
            "before attributing any quality gain to onboarding changes."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 12. SCENARIO AND POLICY ECONOMICS
    # ===================================================================
    story += [
        Paragraph("SECTION 12  |  FINDINGS", ST["Kicker"]),
        h1("Scenario and policy economics"),
        deck(
            "The scenarios rank the available mitigations clearly. None of them reaches "
            "break-even, and the policy that supports them still needs holdout evidence."
        ),
        p(
            f"Four interventions are modeled against a run-rate baseline built from the trailing "
            f"{scenario_baseline_months} months and scaled to a {scenario_horizon_months}-month "
            f"forward horizon. That baseline is a smaller, forward-looking window, not the "
            f"cumulative 24-month totals used earlier in this report, so the dollar figures below "
            f"should not be compared directly to the executive summary's full-period numbers; read "
            f"them as relative rankings of the mitigations against each other. The four "
            f"interventions are tighter fraud and review controls, seller quality improvement, "
            f"subsidy tightening, and an adverse downside in which risky cohorts expand faster. "
            f"Fraud control is the strongest lever, improving contribution margin by "
            f"{money(fraud.contribution_margin_change_vs_baseline)} and avoiding "
            f"{money(fraud.leakage_avoided_vs_baseline)} of leakage for a modest "
            f"{abs(fraud.gmv_change_vs_baseline_pct):.1f}% reduction in GMV. Seller quality "
            f"improvement adds {money(quality.contribution_margin_change_vs_baseline)} and subsidy "
            f"tightening {money(subs.contribution_margin_change_vs_baseline)}, the latter at a larger "
            f"{abs(subs.gmv_change_vs_baseline_pct):.1f}% GMV cost."
        ),
        fig(
            "19_scenario_before_after.png",
            "Deterministic contribution margin by scenario, against the run-rate baseline.",
        ),
        p(
            f"The downside scenario is the warning. If high-risk cohorts grow faster, contribution "
            f"margin deteriorates by {money(abs(down.contribution_margin_change_vs_baseline))} even "
            f"as GMV rises {down.gmv_change_vs_baseline_pct:.1f}%. That asymmetry, where unmanaged "
            f"growth can erase the entire benefit of the best mitigation, is the quantitative case "
            f"for risk-adjusted growth limits. Growth and risk cannot be governed on separate "
            f"scorecards when the downside of getting risk wrong is larger than the upside of the "
            f"best available control."
        ),
        p(
            "The Monte Carlo distribution removes any temptation to over-read a single point estimate. "
            "Simulating the scenarios across their assumption ranges produces contribution-margin "
            "bands rather than fixed numbers."
        ),
        fig(
            "18_scenario_margin_ranges.png",
            "Monte Carlo contribution-margin ranges by scenario, from repeated simulation.",
        ),
        p(
            f"Even the most favorable scenario keeps a negative margin across the entire simulated "
            f"range. Fraud control improves on the baseline in essentially every draw, with a median "
            f"contribution margin around {money(mc_fraud['contribution_margin_proxy_p50'])} and a "
            f"95th-percentile outcome near {money(mc_fraud['contribution_margin_proxy_p95'])}, still "
            f"a loss. The modeled probability of a positive contribution margin is "
            f"{pct(mc_prob_positive_max)} in every scenario. The conclusion is not that the "
            f"mitigations are worthless; it is that they are "
            f"too small relative to a structural loss of this size. Scenario ranking guides the "
            f"sequence of mitigation funding. It does not support any claim of profitability."
        ),
        p(
            f"The review policy sits inside the same caution. The threshold curve shows simulated net "
            f"benefit rising and then flattening as the review rate increases, with the recommended "
            f"threshold of {rec.recommended_threshold:.0f} producing {money(rec.net_benefit)} of "
            f"in-sample net benefit after review cost and conversion friction."
        ),
        fig(
            "20_threshold_tradeoff.png",
            "Review coverage against simulated net benefit, with the recommended operating point.",
        ),
        p(
            "The optimum is set by marginal benefit against capacity and customer friction, not by "
            "maximum theoretical coverage. Because the estimate is retrospective and in-sample, the "
            "responsible path is a measured holdout experiment that selects the operating threshold "
            "on later-period data before any review capacity is committed."
        ),
        pull(
            "Fraud control is the best lever and still leaves a loss. Every scenario has zero "
            "modeled probability of positive margin. Mitigation buys time; it does not buy "
            "profitability."
        ),
        p(
            "<b>Owner and action.</b> CFO, Chief Risk Officer and Strategy, next planning cycle. "
            "Fund fraud control first and establish risk-adjusted growth limits, release review "
            "capacity only through a holdout experiment, and keep a separate structural economics "
            "program running in parallel with the mitigation scenarios."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 13. RISKS AND LIMITATIONS
    # ===================================================================
    story += [
        Paragraph("SECTION 13", ST["Kicker"]),
        h1("Risks, limitations and caveats"),
        deck(
            "The largest risk in this report is confusing disciplined analytics with "
            "real-world proof. Each limitation below has a required guardrail."
        ),
        p(
            "Every number in this report should be read against the boundary set in the methodology. "
            "The analysis is internally consistent and reproducible, and it is honest about what it "
            "cannot support. The table below records the five limitations that govern how the output "
            "may be used, each paired with the control that contains it."
        ),
        table(
            [
                ["Limitation", "Why it matters", "Required guardrail", "Owner"],
                [
                    "Synthetic data",
                    "Findings do not describe a real marketplace",
                    "Rebuild on governed real data before any business use",
                    "Data and Finance",
                ],
                [
                    "Proxy economics",
                    "Margin excludes fulfillment and overhead cost pools",
                    "Reconcile to the management P&amp;L before target setting",
                    "Finance",
                ],
                [
                    "Heuristic scores",
                    "Indices are not calibrated event probabilities",
                    "Validate calibration, fairness and drift before automation",
                    "Model Risk",
                ],
                [
                    "In-sample policy",
                    "Review economics may not generalize forward",
                    "Use a later-period holdout and a controlled pilot",
                    "Risk Operations",
                ],
                [
                    "Assumption-driven scenarios",
                    "Ranges are not forecasts or causal estimates",
                    "Approve assumptions and track realized impact",
                    "Strategy and Finance",
                ],
            ],
            [3.1 * cm, 4.3 * cm, 5.4 * cm, FW - 12.8 * cm],
        ),
        Spacer(1, 10),
        h2("Release position"),
        p(
            f"The formal release state is <b>{release['release_state']}</b>. The configured technical "
            f"and analytical checks pass, with {int(release['blocker_count'])} blockers recorded. "
            f"That state supports external publication as an analytical reference. Committee-grade and "
            f"production readiness are explicitly withheld, and the synthetic values must not be used "
            f"as a budget, forecast or operating commitment."
        ),
        h2("How the board should interpret this"),
        p(
            "The board can use this report to assess the quality of the decision architecture, the "
            "clarity of the economic trade-offs and the credibility of the proposed governance model. "
            "Those are the genuine deliverables. The specific dollar figures are illustrative of the "
            "method, not of a real position, and the recovery program is the right shape for a "
            "marketplace with these symptoms even though the magnitudes would change on real data."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 14. RECOMMENDATIONS
    # ===================================================================
    story += [
        Paragraph("SECTION 14", ST["Kicker"]),
        h1("Recommendations and action priorities"),
        deck(
            "A 180-day program in three tiers. Immediate economic control, near-term "
            "execution, and structural margin repair, with a decision gate closing each phase."
        ),
        p(
            "The recommendations restate the findings as a sequenced program. The ordering is "
            "deliberate: the cheapest and most reversible controls come first, the structural "
            "commercial change comes last after the diagnostics that justify it are in hand, and each "
            "phase ends with an explicit gate decision rather than drifting into the next."
        ),
        priority_table(
            [
                ["Tier", "Decision", "Accountable owner", "Success measure", "Timing"],
                [
                    "Immediate",
                    "Make contribution margin the growth gate",
                    "CFO and Commercial",
                    "No approved growth plan dilutes contribution margin without explicit exception",
                    "0-30 days",
                ],
                [
                    "Immediate",
                    "Mobilize Electronics and Fashion recovery",
                    "Marketplace GM and Category",
                    "Refund value and contribution loss reduced against category baseline",
                    "0-30 days",
                ],
                [
                    "Near term",
                    "Operate seller and order queues",
                    "Risk Operations and Seller Management",
                    "Queue SLA, outcome capture and holdout policy evidence",
                    "30-60 days",
                ],
                [
                    "Near term",
                    "Deploy category-specific control packs",
                    "Category, CX and Payments",
                    "Avoided leakage value measured by control pack",
                    "30-90 days",
                ],
                [
                    "Structural",
                    "Repair commercial economics",
                    "CFO, Strategy and Marketplace GM",
                    "Credible path to break-even under governed assumptions",
                    "60-180 days",
                ],
            ]
        ),
        Spacer(1, 10),
        h2("Evidence gates"),
        p(
            "Each phase closes when its evidence gate is met, and the gate decision is binary: "
            "proceed, revise or stop. This keeps the program honest, because a phase cannot be "
            "declared successful on activity alone."
        ),
        table(
            [
                ["Phase", "Critical actions", "Evidence gate", "Gate decision"],
                [
                    "0-30 days",
                    "Install growth gate; mobilize Electronics and Fashion; assign High-priority sellers",
                    "Baseline margin, leakage value, owners and targets approved",
                    "Confirm scope and funding",
                ],
                [
                    "31-60 days",
                    "Validate score thresholds; launch seller queue; define category control packs",
                    "Holdout performance, queue SLA and pilot design approved",
                    "Authorize controlled pilots",
                ],
                [
                    "61-90 days",
                    "Run pilots; deploy fraud controls; implement targeted buyer and seller friction",
                    "Avoided loss, customer friction and operational cost measured",
                    "Scale, revise or stop each control",
                ],
                [
                    "91-180 days",
                    "Implement structural commercial changes; embed monthly scenario review",
                    "Break-even path supported by governed economics",
                    "Approve operating model and targets",
                ],
            ],
            [2.1 * cm, 5.0 * cm, 5.3 * cm, FW - 12.4 * cm],
        ),
        Spacer(1, 8),
        p(
            "<b>Cadence.</b> Weekly governance of the seller and order queues; monthly review of "
            "economics and scenarios; quarterly threshold validation and structural economics review. "
            "<b>Escalation.</b> Any initiative that widens the protection gap, or that relies on an "
            "unvalidated threshold, escalates to the CFO before it proceeds."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 15. FURTHER QUESTIONS
    # ===================================================================
    story += [
        Paragraph("SECTION 15", ST["Kicker"]),
        h1("Further questions and evidence gaps"),
        deck(
            "The current report is decision-ready for a synthetic command-center demonstration. "
            "These are the questions that must be answered before the same logic becomes an "
            "operating governance process."
        ),
        p(
            "A high-quality executive report should be explicit about what would change the decision. "
            "The evidence here is internally consistent, but the next level of rigor is not another "
            "chart; it is proof that the same relationships hold on governed real data and under "
            "live operating constraints. The open questions below define the upgrade path from "
            "diagnostic confidence to execution confidence."
        ),
        table(
            [
                ["Open question", "Why it matters", "Evidence needed", "Decision unlocked"],
                [
                    "What is the true contribution margin after full cost allocation?",
                    "The current proxy excludes fulfillment, support, platform and overhead cost pools",
                    "Reconciliation to management P&amp;L by category, seller tier and order cohort",
                    "Set break-even targets and capital allocation rules",
                ],
                [
                    "Do risk scores generalize out of sample?",
                    "The review policy is retrospective and can overstate deployable value",
                    "Later-period holdout by threshold, with precision, recall, avoided loss and friction",
                    "Authorize review capacity and threshold deployment",
                ],
                [
                    "Which refund drivers are operationally addressable?",
                    "Refunds are the largest loss pool, but root causes require different controls",
                    "Reason-code taxonomy, item defect signals, delivery performance and listing-quality audit",
                    "Fund category control packs with measurable value targets",
                ],
                [
                    "How much customer and seller friction is acceptable?",
                    "Fraud, payout and return controls can recover leakage while damaging growth or supply",
                    "Controlled pilots measuring conversion, repeat purchase, churn and seller retention",
                    "Scale, revise or stop each control",
                ],
                [
                    "Are high-priority sellers persistently bad or temporarily volatile?",
                    "Governance action should differ for chronic issues versus transient operational shocks",
                    "Rolling seller cohorts, remediation history and post-action recovery curves",
                    "Choose coaching, reserve, audit or offboarding by seller type",
                ],
                [
                    "Can intervention benefits be causally attributed?",
                    "Scenario gains are assumption-driven and should not be booked as realized savings",
                    "A/B tests, matched cohorts or stepped-wedge rollout with pre-registered success metrics",
                    "Recognize avoided leakage and update scenario assumptions",
                ],
            ],
            [4.1 * cm, 4.1 * cm, 5.0 * cm, FW - 13.2 * cm],
        ),
        Spacer(1, 10),
        h2("Minimum evidence standard for operating use"),
        p(
            "Before this framework is used for real seller enforcement, fraud intervention or capital "
            "allocation, the evidence standard should be: governed real tables; finance-approved "
            "margin definitions; out-of-sample score performance; documented intervention unit "
            "costs; customer and seller friction measurement; and a release gate that separates "
            "monitoring, pilot and production status. Without those controls, the framework should "
            "remain a decision-support prototype and publication artifact."
        ),
        pull(
            "The next question is not whether the synthetic report is internally coherent. It is "
            "whether the same economics, score separation and intervention returns survive real "
            "data, holdout validation and live operating friction."
        ),
        PageBreak(),
    ]

    # ===================================================================
    # 16. APPENDIX
    # ===================================================================
    story += [
        Paragraph("APPENDIX", ST["Kicker"]),
        h1("Appendix"),
        deck(
            "Supporting tables and definitions. The same governed metrics feed this report, "
            "the standalone dashboard and the validation gate."
        ),
        h2("A. Executive KPI snapshot"),
    ]
    interp = {
        "gmv": "Commercial scale before protection and leakage",
        "net_value": "Value after discounts and subsidy treatment",
        "risk_adjusted_value": "Net value after modeled expected risk loss",
        "take_rate": "Commission yield on GMV",
        "subsidy_share": "GMV funded by marketplace subsidy",
        "realized_contribution_margin_proxy": "Commission less modeled gross leakage",
        "expected_margin_after_risk": "Pre-outcome underwriting view",
        "refund_rate": "Share of orders refunded",
        "dispute_rate": "Share of orders disputed",
        "chargeback_rate": "Share of orders charged back",
        "top10_seller_gmv_share": "Current-period seller concentration",
    }
    # Metric keys carry acronyms (GMV) and embedded digits (top10) that
    # str.title() mangles into "Gmv" and "Top10 Seller Gmv Share" — a
    # display name is a deliberate editorial choice, not a mechanical
    # transform of the underlying column name.
    display_name = {
        "gmv": "GMV",
        "net_value": "Net Value",
        "risk_adjusted_value": "Risk-Adjusted Value",
        "take_rate": "Take Rate",
        "subsidy_share": "Subsidy Share",
        "realized_contribution_margin_proxy": "Realized Contribution Margin",
        "expected_margin_after_risk": "Expected Margin After Risk",
        "refund_rate": "Refund Rate",
        "dispute_rate": "Dispute Rate",
        "chargeback_rate": "Chargeback Rate",
        "top10_seller_gmv_share": "Top 10 Seller GMV Share",
    }
    kpi_rows = [["Metric", "Value", "Interpretation"]]
    for key, txt in interp.items():
        kpi_rows.append([display_name[key], kd[key], txt])
    story += [
        table(kpi_rows, [5.6 * cm, 3.2 * cm, FW - 8.8 * cm], numeric_cols=(1,)),
        Spacer(1, 12),
        h2("B. Category economics"),
    ]
    cat_rows = [["Category", "Orders", "GMV", "Refund rate", "Margin rate", "Contribution"]]
    for name, r in cat.iterrows():
        cat_rows.append(
            [name, f"{int(r.orders):,}", money(r.gmv), pct(r.refund_rate), pct(r.margin_rate), money(r.margin)]
        )
    story += [
        table(
            cat_rows, [3.0 * cm, 2.0 * cm, 2.6 * cm, 2.4 * cm, 2.4 * cm, FW - 12.4 * cm], numeric_cols=(1, 2, 3, 4, 5)
        ),
        Spacer(1, 12),
        h2("C. Scenario decision matrix"),
    ]
    nice = {
        "baseline": "Baseline",
        "fraud_control_improvement": "Fraud control improvement",
        "seller_quality_improvement": "Seller quality improvement",
        "subsidy_tightening": "Subsidy tightening",
        "downside_high_risk_deterioration": "Downside risk deterioration",
    }
    scen_rows = [["Scenario", "CM vs baseline", "Leakage avoided", "GMV change", "P(CM &gt; 0)"]]
    for key, label in nice.items():
        r = scen.loc[key]
        scen_rows.append(
            [
                label,
                money(r.contribution_margin_change_vs_baseline),
                money(r.leakage_avoided_vs_baseline),
                f"{r.gmv_change_vs_baseline_pct:+.1f}%",
                pct(mc.loc[key, "prob_cm_positive"]),
            ]
        )
    story += [
        table(scen_rows, [5.0 * cm, 3.1 * cm, 3.1 * cm, 2.7 * cm, FW - 13.9 * cm], numeric_cols=(1, 2, 3, 4)),
        Spacer(1, 12),
        h2("D. Definitions and analytical sources"),
        table(
            [
                ["Term", "Definition"],
                [
                    "Realized contribution margin",
                    "Commission less subsidy, refund, dispute and chargeback-loss proxy; not accounting profit.",
                ],
                ["Risk-adjusted value", "Net value less modeled expected risk loss; a pre-outcome measure."],
                ["Protection gap", "Share of GMV removed by risk adjustment before realized loss events."],
                ["Governance priority", "Seller index combining quality, fraud, fragility and concentration."],
                ["Threshold simulation", "Retrospective in-sample estimate of review economics; needs holdout."],
            ],
            [4.6 * cm, FW - 4.6 * cm],
        ),
        Spacer(1, 9),
        p(
            "<b>Primary analytical sources.</b> Order profitability features, order risk scores, "
            "seller scorecards, buyer behavior risk, category risk summaries, scenario results, "
            "Monte Carlo scenario summaries and backtesting policy outputs, all generated by the "
            "reproducible pipeline and validated through the release gate before publication."
        ),
    ]

    doc.multiBuild(story)
    print("wrote", OUT / "marketplace-command-center-report.pdf", "(", FIG["n"], "figures )")


if __name__ == "__main__":
    build()
