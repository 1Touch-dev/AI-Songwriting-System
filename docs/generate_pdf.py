"""
Generate SonicFlow_Studio_Manual.pdf from the markdown source.
Uses fpdf2 (available in venv). Run from project root with venv active:
    python docs/generate_pdf.py
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos
import re
import os

MD_PATH  = os.path.join(os.path.dirname(__file__), "SonicFlow_Studio_Manual.md")
PDF_PATH = os.path.join(os.path.dirname(__file__), "SonicFlow_Studio_Manual.pdf")

# ── Colour palette ────────────────────────────────────────────────────────────
C_BG        = (14, 14, 14)
C_SURFACE   = (28, 28, 28)
C_CYAN      = (143, 245, 255)
C_LIME      = (195, 244, 0)
C_PURPLE    = (210, 119, 255)
C_WHITE     = (240, 240, 240)
C_MUTED     = (160, 160, 160)
C_RED       = (255, 71, 87)
C_BORDER    = (50, 50, 50)

MARGIN = 15
PAGE_W = 210

# Font paths — Arial Unicode covers all scripts inc. bullets, arrows, emoji fallbacks
FONT_REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD    = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
FONT_UNICODE = "/Library/Fonts/Arial Unicode.ttf"


class ManualPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(MARGIN, MARGIN, MARGIN)
        # Register Unicode-capable fonts
        self.add_font("Arial", style="",  fname=FONT_REGULAR)
        self.add_font("Arial", style="B", fname=FONT_BOLD)
        self.add_font("ArialUni", style="", fname=FONT_UNICODE)

    def header(self):
        # Dark header bar
        self.set_fill_color(*C_SURFACE)
        self.rect(0, 0, 210, 12, style="F")
        self.set_font("Arial", "B", 8)
        self.set_text_color(*C_CYAN)
        self.set_y(3.5)
        self.cell(0, 5, "SonicFlow Studio v3  |  Complete User Manual & Reference Guide",
                  align="C")
        self.set_y(13)

    def footer(self):
        self.set_y(-12)
        self.set_fill_color(*C_SURFACE)
        self.rect(0, self.get_y(), 210, 12, style="F")
        self.set_font("Arial", "", 7)
        self.set_text_color(*C_MUTED)
        self.cell(0, 5,
                  f"Page {self.page_no()}  |  AI Songwriting System V3  |  EC2 3.239.91.199",
                  align="C")

    def cover_page(self):
        self.add_page()
        # Full dark background
        self.set_fill_color(*C_BG)
        self.rect(0, 0, 210, 297, style="F")

        # Gradient accent bar
        self.set_fill_color(*C_CYAN)
        self.rect(0, 80, 8, 60, style="F")
        self.set_fill_color(*C_PURPLE)
        self.rect(0, 140, 8, 40, style="F")

        # Title
        self.set_xy(20, 90)
        self.set_font("Arial", "B", 32)
        self.set_text_color(*C_CYAN)
        self.cell(0, 12, "SonicFlow Studio", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_x(20)
        self.set_font("Arial", "B", 22)
        self.set_text_color(*C_WHITE)
        self.cell(0, 10, "Version 3  —  Complete User Manual", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_x(20)
        self.set_font("Arial", "", 12)
        self.set_text_color(*C_MUTED)
        self.cell(0, 8, "AI Songwriting  -  Voice Synthesis  -  Music Generation",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Divider
        self.set_y(160)
        self.set_draw_color(*C_BORDER)
        self.line(20, 160, 190, 160)

        # Info block
        info = [
            ("System",      "SonicFlow Studio v3"),
            ("Deployment",  "AWS EC2  -  3.239.91.199"),
            ("API Version", "3.0.0"),
            ("Branch",      "feature/final-production-hardening"),
            ("AI Engines",  "OpenAI GPT-4o  -  ElevenLabs  -  Suno AI v4"),
        ]
        self.set_y(170)
        for label, value in info:
            self.set_x(20)
            self.set_font("Arial", "B", 9)
            self.set_text_color(*C_CYAN)
            self.cell(45, 7, label + ":")
            self.set_font("Arial", "", 9)
            self.set_text_color(*C_WHITE)
            self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Bottom tagline
        self.set_y(255)
        self.set_x(20)
        self.set_font("Arial", "I", 9)
        self.set_text_color(*C_MUTED)
        self.multi_cell(170, 5,
            "From a creative idea to a fully produced song with vocals and music in one click.",
            align="L")


_EMOJI_MAP = {
    "🧠": "[AI]", "🎤": "[Vocal]", "🎵": "[Music]", "🔍": "[Analysis]",
    "📝": "[Lyrics]", "🌈": "[Variants]", "💡": "[Insights]", "📊": "[Stats]",
    "🗑": "[Del]", "✕": "x", "✓": "OK", "►": ">", "▼": "v",
    "\u2022": "-",  # bullet
    "\u2014": "--", # em dash
    "\u2013": "-",  # en dash
    "\u2019": "'",  # curly apostrophe
    "\u201c": '"',  "\u201d": '"',  # curly quotes
    "\u2192": "->", "\u25ba": ">",
}

def _strip_md(text: str) -> str:
    """Strip markdown formatting and replace non-Latin-1 chars for PDF."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`(.*?)`", r"\1", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text)
    for emoji, replacement in _EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    # Drop any remaining non-latin1 chars gracefully
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text.strip()


def build_pdf():
    pdf = ManualPDF()
    pdf.set_fill_color(*C_BG)

    # Cover page (no dark bg rect — header/footer run on it)
    pdf.cover_page()

    # ── Parse and render markdown ─────────────────────────────────────────────
    with open(MD_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    pdf.add_page()
    # Dark page background
    pdf.set_fill_color(*C_BG)
    pdf.rect(0, 0, 210, 297, style="F")

    i = 0
    in_table      = False
    in_code       = False
    code_buf: list[str] = []
    toc_done      = False

    while i < len(lines):
        raw = lines[i].rstrip("\n")
        i += 1
        stripped = raw.strip()

        # Skip the very first H1 (used on cover)
        if stripped.startswith("# SonicFlow Studio v3"):
            continue

        # ── Table of Contents header — render minimally ──────────────────────
        if "Table of Contents" in stripped and stripped.startswith("##") and not toc_done:
            toc_done = True
            pdf.set_font("Arial", "B", 16)
            pdf.set_text_color(*C_CYAN)
            pdf.set_fill_color(*C_BG)
            pdf.ln(4)
            pdf.cell(0, 10, "Table of Contents", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*C_BORDER)
            pdf.line(MARGIN, pdf.get_y(), PAGE_W - MARGIN, pdf.get_y())
            pdf.ln(2)
            continue

        # ── Code block ───────────────────────────────────────────────────────
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                # Render code block
                if code_buf:
                    pdf.ln(2)
                    pdf.set_fill_color(*C_SURFACE)
                    block_h = len(code_buf) * 5 + 6
                    pdf.rect(MARGIN, pdf.get_y(), PAGE_W - 2 * MARGIN, block_h, style="F")
                    pdf.set_font("ArialUni", "", 8)
                    pdf.set_text_color(*C_LIME)
                    for cl in code_buf:
                        pdf.set_x(MARGIN + 3)
                        pdf.cell(0, 5, cl[:110], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                    pdf.ln(2)
                    pdf.set_fill_color(*C_BG)
            continue

        if in_code:
            code_buf.append(raw if raw else "")
            continue

        # ── Horizontal rule ──────────────────────────────────────────────────
        if stripped in ("---", "***", "___"):
            pdf.ln(2)
            pdf.set_draw_color(*C_BORDER)
            pdf.line(MARGIN, pdf.get_y(), PAGE_W - MARGIN, pdf.get_y())
            pdf.ln(3)
            continue

        # ── Table row ────────────────────────────────────────────────────────
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator rows (---|---)
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                in_table = True
                continue
            in_table = True
            col_w = (PAGE_W - 2 * MARGIN) / max(len(cells), 1)
            pdf.set_fill_color(*C_SURFACE)
            pdf.rect(MARGIN, pdf.get_y(), PAGE_W - 2 * MARGIN, 6, style="F")
            pdf.set_font("Arial", "", 8)
            pdf.set_text_color(*C_WHITE)
            pdf.set_x(MARGIN)
            for ci, cell in enumerate(cells):
                txt = _strip_md(cell)[:50]
                # Header row detection: bold first row
                if not hasattr(pdf, "_table_header_done"):
                    pdf._table_header_done = False
                is_header = not pdf._table_header_done and ci == 0
                if not pdf._table_header_done:
                    pdf.set_font("Arial", "B", 8)
                    pdf.set_text_color(*C_CYAN)
                else:
                    pdf.set_font("Arial", "", 8)
                    pdf.set_text_color(*C_WHITE)
                pdf.cell(col_w, 6, txt, border=0)
            pdf._table_header_done = True
            pdf.ln(6)
            continue
        else:
            if in_table:
                in_table = False
                pdf._table_header_done = False
                pdf.ln(1)

        # ── Headings ─────────────────────────────────────────────────────────
        if stripped.startswith("#### "):
            pdf.ln(3)
            pdf.set_font("Arial", "B", 10)
            pdf.set_text_color(*C_LIME)
            pdf.set_x(MARGIN)
            pdf.multi_cell(PAGE_W - 2 * MARGIN, 6, _strip_md(stripped[5:]))
            pdf.ln(1)
            continue

        if stripped.startswith("### "):
            pdf.ln(4)
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(*C_PURPLE)
            pdf.set_fill_color(*C_SURFACE)
            pdf.rect(MARGIN, pdf.get_y(), PAGE_W - 2 * MARGIN, 8, style="F")
            pdf.set_x(MARGIN + 3)
            pdf.cell(0, 8, _strip_md(stripped[4:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(2)
            continue

        if stripped.startswith("## "):
            pdf.add_page()
            pdf.set_fill_color(*C_BG)
            pdf.rect(0, 0, 210, 297, style="F")
            pdf.ln(2)
            # Accent bar
            pdf.set_fill_color(*C_CYAN)
            pdf.rect(MARGIN, pdf.get_y(), 3, 12, style="F")
            pdf.set_font("Arial", "B", 16)
            pdf.set_text_color(*C_CYAN)
            pdf.set_x(MARGIN + 6)
            pdf.cell(0, 12, _strip_md(stripped[3:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_draw_color(*C_BORDER)
            pdf.line(MARGIN, pdf.get_y(), PAGE_W - MARGIN, pdf.get_y())
            pdf.ln(4)
            continue

        if stripped.startswith("# "):
            pdf.ln(6)
            pdf.set_font("Arial", "B", 20)
            pdf.set_text_color(*C_CYAN)
            pdf.set_x(MARGIN)
            pdf.multi_cell(PAGE_W - 2 * MARGIN, 10, _strip_md(stripped[2:]))
            pdf.ln(3)
            continue

        # ── List items ───────────────────────────────────────────────────────
        if stripped.startswith("- ") or stripped.startswith("* "):
            txt = _strip_md(stripped[2:])
            pdf.set_font("Arial", "", 9)
            pdf.set_text_color(*C_WHITE)
            pdf.set_x(MARGIN + 5)
            pdf.set_fill_color(*C_CYAN)
            # Bullet dot
            pdf.rect(MARGIN + 1, pdf.get_y() + 2.5, 2, 2, style="F")
            pdf.multi_cell(PAGE_W - 2 * MARGIN - 5, 5, txt)
            continue

        if re.match(r"^\d+\.\s", stripped):
            txt = _strip_md(re.sub(r"^\d+\.\s", "", stripped))
            num = re.match(r"^(\d+)\.", stripped).group(1)
            pdf.set_font("Arial", "B", 9)
            pdf.set_text_color(*C_CYAN)
            pdf.set_x(MARGIN + 2)
            pdf.cell(6, 5, num + ".")
            pdf.set_font("Arial", "", 9)
            pdf.set_text_color(*C_WHITE)
            pdf.multi_cell(PAGE_W - 2 * MARGIN - 8, 5, txt)
            continue

        # ── TOC lines (indented with numbers/dashes) ─────────────────────────
        if stripped.startswith("   -") or stripped.startswith("    "):
            txt = _strip_md(stripped)
            pdf.set_font("Arial", "", 8)
            pdf.set_text_color(*C_MUTED)
            pdf.set_x(MARGIN + 8)
            pdf.multi_cell(PAGE_W - 2 * MARGIN - 8, 4.5, txt)
            continue

        # ── Blank line ───────────────────────────────────────────────────────
        if not stripped:
            pdf.ln(2)
            continue

        # ── Normal paragraph ─────────────────────────────────────────────────
        txt = _strip_md(stripped)
        if not txt:
            continue
        pdf.set_font("Arial", "", 9)
        pdf.set_text_color(*C_WHITE)
        pdf.set_x(MARGIN)
        pdf.multi_cell(PAGE_W - 2 * MARGIN, 5, txt)
        pdf.ln(1)

    pdf.output(PDF_PATH)
    print(f"PDF saved → {PDF_PATH}")
    size_kb = os.path.getsize(PDF_PATH) // 1024
    print(f"File size: {size_kb} KB")


if __name__ == "__main__":
    build_pdf()
