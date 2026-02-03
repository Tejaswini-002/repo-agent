#!/usr/bin/env python3
"""PDF logger for PR event summaries"""
import os
from datetime import datetime
from pathlib import Path

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False


def generate_pdf_report(events: list, output_path: str = "pr_events_report.pdf"):
    """Generate a PDF report from PR events (requires reportlab)"""
    if not HAS_REPORTLAB:
        return False
    
    try:
        doc = SimpleDocTemplate(output_path, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#0366d6'),
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.HexColor('#24292e'),
            spaceAfter=6,
        )
        
        # Title
        elements.append(Paragraph("Repository Monitor — PR Event Summary", title_style))
        elements.append(Paragraph(f"Generated: {datetime.utcnow().isoformat()}Z", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Process events
        for i, ev in enumerate(events):
            if ev.get("event_name") == "pull_request" and ev.get("summary"):
                s = ev["summary"]
                ts = ev.get("timestamp", "N/A")
                
                # Event header
                elements.append(Paragraph(f"Event #{i+1}: PR #{s.get('pr_number')} — {s.get('action').upper()}", heading_style))
                
                # Details table
                data = [
                    ["Field", "Value"],
                    ["Timestamp", ts],
                    ["Repository", s.get("repo", "N/A")],
                    ["PR Number", str(s.get("pr_number", "N/A"))],
                    ["Title", s.get("title", "N/A")],
                    ["Author", s.get("user", "N/A")],
                    ["Changed Files", str(s.get("changed_files_count", 0))],
                    ["URL", s.get("url", "N/A")],
                ]
                
                table = Table(data, colWidths=[1.5*inch, 4*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f6f8fa')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e1e4e8')),
                ]))
                elements.append(table)
                
                # File changes
                if s.get("files"):
                    elements.append(Spacer(1, 8))
                    elements.append(Paragraph("Changed Files:", styles['Heading3']))
                    file_data = [["Status", "Filename"]]
                    for f in s["files"][:50]:  # limit to 50 for PDF brevity
                        file_data.append([f.get("status", "?"), f.get("filename", "N/A")])
                    
                    file_table = Table(file_data, colWidths=[0.8*inch, 4.7*inch])
                    file_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f6f8fa')),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.3, colors.HexColor('#e1e4e8')),
                        ('TOPPADDING', (0, 0), (-1, -1), 2),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                    ]))
                    elements.append(file_table)
                
                elements.append(Spacer(1, 12))
        
        if len(elements) > 3:  # only if there were events
            doc.build(elements)
            return True
    except Exception as e:
        print(f"Error generating PDF: {e}")
        return False
    
    return False
