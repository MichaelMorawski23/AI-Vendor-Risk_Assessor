"""Generates an Excel risk register from a completed VendorAssessment."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

from .models import VendorAssessment


def write_excel_report(assessment: VendorAssessment, out_path: str | Path) -> Path:
    out_path = Path(out_path)
    wb = Workbook()

    summary = wb.active
    summary.title = "Summary"
    summary.append(["Vendor", assessment.vendor_name])
    summary.append(["Business use case", assessment.business_use_case])
    summary.append(["Data accessed", assessment.data_accessed])
    summary.append(["Used by", assessment.used_by])
    summary.append(["Inherent risk", assessment.inherent_risk.value if assessment.inherent_risk else "Not scored"])
    summary.append(["Residual risk", assessment.residual_risk.value if assessment.residual_risk else "Not scored"])
    summary.append(["Recommendation", assessment.recommendation or "Pending human review"])
    for row in summary.iter_rows(min_row=1, max_row=7, min_col=1, max_col=1):
        row[0].font = Font(bold=True)

    evidence_sheet = wb.create_sheet("Evidence")
    evidence_sheet.append(["Question", "Answer", "Verified", "Source document", "Page"])
    for e in assessment.evidence:
        evidence_sheet.append(
            [
                e.question_text,
                e.answer if e.verified else "Not verified",
                "Yes" if e.verified else "No",
                e.citation.document if e.citation else "",
                e.citation.page if e.citation else "",
            ]
        )

    findings_sheet = wb.create_sheet("Findings")
    findings_sheet.append(["Summary", "Severity", "Recommended control"])
    for f in assessment.findings:
        findings_sheet.append([f.summary, f.severity.value, f.recommended_control or ""])

    rmf_sheet = wb.create_sheet("NIST AI RMF Mapping")
    rmf_sheet.append(["Function", "Category", "Note"])
    for m in assessment.rmf_mappings:
        rmf_sheet.append([m.function.value, m.category, m.note])

    if assessment.injection_flags:
        flags_sheet = wb.create_sheet("Screened Content")
        flags_sheet.append(["Document", "Page", "Reason", "Snippet"])
        for flag in assessment.injection_flags:
            flags_sheet.append([flag.document, flag.page, flag.reason, flag.snippet])

    wb.save(out_path)
    return out_path
