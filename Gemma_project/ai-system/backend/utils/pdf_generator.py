"""
Professional PDF generator for Riphah admission applications.
Uses reportlab to produce a styled, branded PDF.
"""

import os
import uuid
from datetime import datetime


_TEAL = (15 / 255, 118 / 255, 110 / 255)   # #0f766e
_TEAL_LIGHT = (240 / 255, 253 / 255, 250 / 255)  # ~teal-50
_SLATE = (30 / 255, 41 / 255, 59 / 255)     # ~slate-800
_GRAY = (100 / 255, 116 / 255, 139 / 255)   # ~slate-500


def generate_admission_pdf(data: dict, output_dir: str | None = None) -> str:
    """
    Generate a professional admission application PDF.

    Args:
        data: dict with keys from ADMISSION_FIELDS
        output_dir: directory to write PDF; defaults to system temp

    Returns:
        Absolute path to the generated PDF file.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    if output_dir is None:
        import tempfile
        output_dir = tempfile.gettempdir()

    app_id = data.get("application_id", f"RIU-{uuid.uuid4().hex[:8].upper()}")
    filename = f"admission_application_{app_id}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    teal_color = colors.Color(*_TEAL)
    teal_light = colors.Color(*_TEAL_LIGHT)
    slate_color = colors.Color(*_SLATE)
    gray_color = colors.Color(*_GRAY)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "Title",
        parent=styles["Normal"],
        fontSize=20,
        fontName="Helvetica-Bold",
        textColor=colors.white,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=colors.Color(0.8, 0.95, 0.93),
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Normal"],
        fontSize=11,
        fontName="Helvetica-Bold",
        textColor=teal_color,
        spaceBefore=10,
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        fontName="Helvetica-Bold",
        textColor=gray_color,
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        fontName="Helvetica",
        textColor=slate_color,
    )
    footer_style = ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        fontName="Helvetica",
        textColor=gray_color,
        alignment=TA_CENTER,
    )

    story = []

    # Header banner (teal background via table)
    header_data = [
        [Paragraph("Riphah International University", title_style)],
        [Paragraph("Undergraduate / Postgraduate Admission Application", subtitle_style)],
        [Paragraph(f"Application ID: {app_id}", subtitle_style)],
    ]
    header_table = Table(header_data, colWidths=[17 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), teal_color),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 12),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [teal_color]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.4 * cm))

    def field_row(label: str, value: str):
        return [
            Paragraph(label, label_style),
            Paragraph(str(value) if value else "—", value_style),
        ]

    def section(title: str, rows: list):
        story.append(Paragraph(title, section_style))
        story.append(HRFlowable(width="100%", thickness=1, color=teal_color, spaceAfter=6))
        t = Table(rows, colWidths=[5 * cm, 12 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), teal_light),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, teal_light]),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.9, 0.95, 0.95)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3 * cm))

    # 1. Personal Information
    section("1. Personal Information", [
        field_row("Full Name",   data.get("full_name", "")),
        field_row("Father Name", data.get("father_name", "")),
        field_row("CNIC / B-Form", data.get("cnic", "")),
        field_row("Date of Birth",  data.get("dob", "")),
        field_row("Gender",         data.get("gender", "")),
    ])

    # 2. Contact Information
    section("2. Contact Information", [
        field_row("Email Address", data.get("email", "")),
        field_row("Phone Number",  data.get("phone", "")),
        field_row("Address",       data.get("address", "")),
    ])

    # 3. Programme & Campus
    section("3. Programme & Campus", [
        field_row("Programme Applied",  data.get("program", "")),
        field_row("Preferred Campus",   data.get("campus", "")),
    ])

    # 4. Academic Background
    section("4. Academic Background", [
        field_row("Matric / O-Level Marks",   data.get("matric_marks", "")),
        field_row("Intermediate / A-Level Marks", data.get("inter_marks", "")),
        field_row("Entry Test Score / Result",    data.get("entry_test", "")),
    ])

    # Declaration
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=gray_color))
    story.append(Spacer(1, 0.3 * cm))
    decl = (
        "I hereby declare that all information provided in this application is true and correct to the best "
        "of my knowledge. I understand that any false or misleading information may result in disqualification "
        "of my application or cancellation of admission."
    )
    story.append(Paragraph(decl, ParagraphStyle(
        "Decl", parent=styles["Normal"], fontSize=9, textColor=gray_color, leading=14
    )))
    story.append(Spacer(1, 1 * cm))

    sig_data = [
        [Paragraph("_________________________", value_style),
         Paragraph("_________________________", value_style)],
        [Paragraph("Applicant Signature", label_style),
         Paragraph("Date", label_style)],
    ]
    sig_table = Table(sig_data, colWidths=[8.5 * cm, 8.5 * cm])
    sig_table.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sig_table)

    # Footer
    story.append(Spacer(1, 0.6 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=gray_color))
    story.append(Spacer(1, 0.2 * cm))
    generated_at = datetime.now().strftime("%d %B %Y, %I:%M %p")
    story.append(Paragraph(
        f"Generated by AskRiphah AI Platform  •  {generated_at}  •  Application ID: {app_id}",
        footer_style,
    ))

    doc.build(story)
    return filepath
