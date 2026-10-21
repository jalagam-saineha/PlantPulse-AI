"""
Professional PDF report generation for a single Leaf Analysis, using
ReportLab. Every figure in the report comes from the Analysis row (and,
when available, the plant's previous analysis for a historical
comparison) — nothing is fabricated.
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
)

from app.services.health_score import compute_health_score

FOREST = colors.HexColor("#1a3a26")
LEAF = colors.HexColor("#2f6d4f")
MUTED = colors.HexColor("#647065")
AMBER = colors.HexColor("#c8842a")
RUST = colors.HexColor("#a54a3f")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("PPTitle", parent=styles["Title"], textColor=FOREST, fontSize=22, spaceAfter=2))
    styles.add(ParagraphStyle("PPSubtitle", parent=styles["Normal"], textColor=MUTED, fontSize=10, spaceAfter=14))
    styles.add(ParagraphStyle("PPHeading", parent=styles["Heading2"], textColor=FOREST, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("PPBody", parent=styles["Normal"], fontSize=10, leading=14))
    styles.add(ParagraphStyle("PPMuted", parent=styles["Normal"], fontSize=8.5, textColor=MUTED, leading=12))
    return styles


def _observations(analysis) -> list:
    obs = []
    if analysis.leaf_coverage is not None:
        if analysis.leaf_coverage >= 85:
            obs.append("Leaf coverage is high, indicating healthy, intact foliage.")
        elif analysis.leaf_coverage >= 60:
            obs.append("Leaf coverage is moderate; some non-green regions were detected.")
        else:
            obs.append("Leaf coverage is low relative to the detected foliage area.")
    if analysis.yellowing is not None and analysis.yellowing >= 8:
        obs.append(f"Yellow-region presence is notable ({analysis.yellowing}% of foliage).")
    if analysis.damage is not None and analysis.damage >= 5:
        obs.append(f"Visible damage was detected across {analysis.damage}% of the measured foliage.")
    if analysis.dark_spots is not None and analysis.dark_spots >= 2:
        obs.append(f"Dark spot regions cover {analysis.dark_spots}% of the foliage.")
    if not obs:
        obs.append("No significant visual stress signals were detected in this image.")
    return obs


def generate_report_pdf(analysis, plant, output_path: Path, media_paths: dict, previous_analysis=None) -> None:
    """
    media_paths: dict with absolute filesystem paths for 'original',
    'processed', 'overlay' (any may be missing/None if the file can't be found).
    """
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )
    story = []

    story.append(Paragraph("PlantPulse AI", styles["PPTitle"]))
    story.append(Paragraph("Visual Plant Health &amp; Growth Intelligence Report", styles["PPSubtitle"]))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e3ddcd"), thickness=1))
    story.append(Spacer(1, 10))

    # --- Plant profile ---
    story.append(Paragraph("Plant Profile", styles["PPHeading"]))
    profile_rows = [
        ["Plant name", plant.name],
        ["Species", plant.species or "—"],
        ["Variety", plant.variety or "—"],
        ["Location", plant.location or "—"],
        ["Analysis date", analysis.created_at.strftime("%B %d, %Y at %H:%M")],
        ["Report generated", _now_str()],
    ]
    t = Table(profile_rows, colWidths=[4 * cm, 11 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(t)

    # --- Leaf-based visual score ---
    story.append(Paragraph("Leaf-Based Visual Score", styles["PPHeading"]))
    score = compute_health_score({
        "leaf_coverage": analysis.leaf_coverage, "yellowing": analysis.yellowing,
        "damage": analysis.damage, "dark_spots": analysis.dark_spots,
    })
    score_text = f'<font size="28" color="#1a3a26"><b>{analysis.health_score}</b></font>' \
                 f'<font size="11" color="#647065">/100 — {score["label"]}</font>'
    story.append(Paragraph(score_text, styles["PPBody"]))
    story.append(Spacer(1, 6))
    comp_rows = [["Component", "Value"]] + [
        [k.replace("_", " ").title(), f'{v}%'] for k, v in score["components"].items()
    ]
    ct = Table(comp_rows, colWidths=[7 * cm, 4 * cm])
    ct.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3f3e9")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e3ddcd")),
    ]))
    story.append(ct)
    story.append(Paragraph(
        "This score describes measured leaf appearance only. It does not assess stems, roots, pests, or "
        "the complete plant, and it is not a scientifically validated agricultural diagnostic.",
        styles["PPMuted"],
    ))

    # --- Visual metrics ---
    story.append(Paragraph("Leaf Analysis — Visual Metrics", styles["PPHeading"]))
    metric_rows = [
        ["Leaf Coverage", "Yellowing", "Visible Damage", "Dark Spots", "Affected Area"],
        [f"{analysis.leaf_coverage}%", f"{analysis.yellowing}%", f"{analysis.damage}%",
         f"{analysis.dark_spots}%", f"{analysis.affected_area}%"],
    ]
    mt = Table(metric_rows, colWidths=[3 * cm] * 5)
    mt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f6f3ea")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e3ddcd")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(mt)

    # --- Images ---
    img_flowables = []
    for label, key in [("Original", "original"), ("Processed", "processed"), ("Health Map", "overlay")]:
        path = media_paths.get(key)
        if path and Path(path).exists():
            img_flowables.append((label, path))
    if img_flowables:
        story.append(Paragraph("Original vs Processed vs Health Map", styles["PPHeading"]))
        row_imgs, row_labels = [], []
        for label, path in img_flowables:
            row_imgs.append(Image(str(path), width=4.6 * cm, height=4.6 * cm))
            row_labels.append(Paragraph(label, styles["PPMuted"]))
        img_table = Table([row_imgs, row_labels], colWidths=[4.8 * cm] * len(row_imgs))
        img_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        story.append(img_table)

    # --- Historical comparison (only if a prior analysis exists) ---
    if previous_analysis is not None:
        story.append(Paragraph("Historical Comparison", styles["PPHeading"]))
        delta_health = None
        if analysis.health_score is not None and previous_analysis.health_score is not None:
            delta_health = round(analysis.health_score - previous_analysis.health_score, 1)
        comp_text = (
            f"Compared to the previous analysis on {previous_analysis.created_at.strftime('%B %d, %Y')}: "
            f"health score {previous_analysis.health_score} → {analysis.health_score}"
            + (f" ({'+' if delta_health >= 0 else ''}{delta_health})" if delta_health is not None else "")
            + "."
        )
        story.append(Paragraph(comp_text, styles["PPBody"]))

    # --- Observations ---
    story.append(Paragraph("Key Observations", styles["PPHeading"]))
    for obs in _observations(analysis):
        story.append(Paragraph(f"• {obs}", styles["PPBody"]))

    # --- Disclaimer ---
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#e3ddcd"), thickness=1))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Disclaimer: PlantPulse AI provides visual screening based on computer-vision measurements and, "
        "where available, Gemini image assessment. It is not a certified agricultural or scientific diagnostic "
        "tool. For confirmed disease identification or treatment decisions, consult a qualified agricultural "
        "professional.",
        styles["PPMuted"],
    ))

    doc.build(story)


def _now_str() -> str:
    from app.models.user import utcnow
    return utcnow().strftime("%B %d, %Y at %H:%M UTC")
