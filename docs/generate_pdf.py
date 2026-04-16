"""
Generate SonicFlow_Studio_Manual.pdf from the markdown source.
Standard white-background document — clean, readable, professional.

Run from project root with venv active:
    python docs/generate_pdf.py
"""

from fpdf import FPDF
from fpdf.enums import XPos, YPos
import re
import os

MD_PATH  = os.path.join(os.path.dirname(__file__), "SonicFlow_Studio_Manual.md")
PDF_PATH = os.path.join(os.path.dirname(__file__), "SonicFlow_Studio_Manual.pdf")

MARGIN  = 20
PAGE_W  = 210
CONTENT_W = PAGE_W - 2 * MARGIN   # 170mm

# Colour palette — clean document colours
C_BLACK      = (20, 20, 20)
C_HEADING1   = (15, 80, 160)     # deep blue
C_HEADING2   = (30, 100, 180)    # mid blue
C_HEADING3   = (50, 50, 50)      # dark grey
C_HEADING4   = (70, 70, 70)      # mid-dark grey
C_MUTED      = (110, 110, 110)   # grey for captions / footer
C_LINK       = (30, 100, 180)
C_TABLE_HDR  = (230, 237, 247)   # light blue-grey header fill
C_TABLE_ALT  = (248, 248, 248)   # very light grey alternate row
C_CODE_BG    = (245, 245, 245)   # near-white code background
C_CODE_TEXT  = (30, 30, 30)      # dark text in code
C_RULE       = (200, 200, 200)   # light grey rule
C_WHITE      = (255, 255, 255)
C_ACCENT     = (15, 80, 160)     # same as heading1


def _clean(text: str) -> str:
    """
    Strip markdown syntax and replace special Unicode characters
    with safe latin-1 equivalents so fpdf core fonts can render them.
    """
    # Inline markdown
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*",     r"\1", text)
    text = re.sub(r"`(.*?)`",       r"\1", text)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)   # links
    text = re.sub(r"^#{1,6}\s+",   "",     text)       # heading hashes

    # Emoji → text labels
    replacements = {
        "\U0001f9e0": "[AI]",       "\U0001f3a4": "[Vocal]",
        "\U0001f3b5": "[Music]",    "\U0001f50d": "[Search]",
        "\U0001f4dd": "[Lyrics]",   "\U0001f308": "[Variants]",
        "\U0001f4a1": "[Insights]", "\U0001f4ca": "[Stats]",
        "\U0001f5d1": "[Delete]",   "\u2715": "x",
        "\u2022": "-",              "\u2014": "--",
        "\u2013": "-",              "\u2019": "'",
        "\u201c": '"',              "\u201d": '"',
        "\u2192": "->",             "\u25ba": ">",
        "\u2713": "OK",             "\u2714": "OK",
    }
    for char, sub in replacements.items():
        text = text.replace(char, sub)

    # Drop anything still outside latin-1
    text = text.encode("latin-1", errors="replace").decode("latin-1")
    return text.strip()


class ManualPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*C_MUTED)
        self.cell(0, 8, "SonicFlow Studio v3  |  Complete User Manual & Reference Guide",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*C_RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*C_RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*C_MUTED)
        self.cell(0, 8, f"Page {self.page_no()}  |  AI Songwriting System V3  |  EC2 3.239.91.199",
                  align="C")

    def cover(self):
        self.add_page()

        # Top accent bar
        self.set_fill_color(*C_ACCENT)
        self.rect(0, 0, PAGE_W, 8, "F")

        self.ln(30)

        # Title block
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(*C_HEADING1)
        self.cell(0, 12, "SonicFlow Studio v3", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*C_HEADING2)
        self.cell(0, 9, "Complete User Manual & Reference Guide", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(4)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(*C_MUTED)
        self.cell(0, 7, "AI Songwriting  -  Voice Synthesis  -  Music Generation", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(12)
        # Divider
        self.set_draw_color(*C_RULE)
        self.line(MARGIN + 20, self.get_y(), PAGE_W - MARGIN - 20, self.get_y())
        self.ln(12)

        # Info table
        info = [
            ("System",         "SonicFlow Studio v3"),
            ("Deployment",     "AWS EC2  -  3.239.91.199  -  Ports 3001 (UI), 8000 (API)"),
            ("API Version",    "3.0.0"),
            ("Frontend",       "Next.js 14 (App Router) + Tailwind CSS"),
            ("Backend",        "FastAPI + Uvicorn (Python)"),
            ("Lyrics AI",      "OpenAI GPT-4o"),
            ("Voice Engine",   "ElevenLabs Multilingual v2"),
            ("Music Engine",   "Suno AI v4 (full song with vocals)"),
            ("Music Fallback", "HuggingFace MusicGen (instrumental)"),
            ("Retrieval",      "FAISS vector index + BM25 hybrid search"),
            ("Branch",         "feature/final-production-hardening"),
        ]
        for label, value in info:
            self.set_x(MARGIN + 20)
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(*C_HEADING2)
            self.cell(45, 6.5, label + ":")
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*C_BLACK)
            self.cell(0, 6.5, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(12)
        self.set_draw_color(*C_RULE)
        self.line(MARGIN + 20, self.get_y(), PAGE_W - MARGIN - 20, self.get_y())
        self.ln(8)

        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*C_MUTED)
        self.set_x(MARGIN + 20)
        self.multi_cell(CONTENT_W - 40, 5.5,
            "From a creative idea to a fully produced song with vocals and music in one click.",
            align="C")

        # Bottom accent bar
        self.set_y(-8)
        self.set_fill_color(*C_ACCENT)
        self.rect(0, self.get_y(), PAGE_W, 8, "F")

    # ── Rendering helpers ─────────────────────────────────────────────────────

    def h1(self, text: str):
        self.add_page()
        self.ln(2)
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*C_HEADING1)
        self.multi_cell(CONTENT_W, 9, _clean(text))
        self.ln(1)
        self.set_draw_color(*C_HEADING1)
        self.set_line_width(0.5)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.set_line_width(0.2)
        self.ln(4)

    def h2(self, text: str):
        self.ln(5)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*C_HEADING2)
        self.multi_cell(CONTENT_W, 7, _clean(text))
        self.set_draw_color(*C_RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(3)

    def h3(self, text: str):
        self.ln(4)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*C_HEADING3)
        self.multi_cell(CONTENT_W, 6.5, _clean(text))
        self.ln(1)

    def h4(self, text: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*C_HEADING4)
        self.multi_cell(CONTENT_W, 6, _clean(text))
        self.ln(0.5)

    def para(self, text: str):
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*C_BLACK)
        self.set_x(MARGIN)
        self.multi_cell(CONTENT_W, 5.5, _clean(text))
        self.ln(1)

    def bullet(self, text: str, indent: int = 0):
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*C_BLACK)
        x = MARGIN + indent * 4
        self.set_x(x + 4)
        self.set_fill_color(*C_HEADING2)
        self.rect(x + 0.5, self.get_y() + 2.2, 1.8, 1.8, "F")
        self.multi_cell(CONTENT_W - indent * 4 - 4, 5.5, _clean(text))

    def numbered(self, n: int, text: str):
        self.set_font("Helvetica", "B", 9.5)
        self.set_text_color(*C_HEADING2)
        self.set_x(MARGIN + 2)
        self.cell(7, 5.5, f"{n}.")
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(*C_BLACK)
        self.multi_cell(CONTENT_W - 9, 5.5, _clean(text))

    def code_block(self, lines: list):
        if not lines:
            return
        self.ln(2)
        block_h = len(lines) * 5 + 6
        self.set_fill_color(*C_CODE_BG)
        self.rect(MARGIN, self.get_y(), CONTENT_W, block_h, "F")
        self.set_draw_color(*C_RULE)
        self.rect(MARGIN, self.get_y(), CONTENT_W, block_h, "D")
        self.set_font("Courier", "", 8)
        self.set_text_color(*C_CODE_TEXT)
        for line in lines:
            self.set_x(MARGIN + 3)
            self.cell(CONTENT_W - 6, 5, _clean(line)[:105],
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def rule(self):
        self.ln(2)
        self.set_draw_color(*C_RULE)
        self.line(MARGIN, self.get_y(), PAGE_W - MARGIN, self.get_y())
        self.ln(3)

    def table_row(self, cells: list, is_header: bool = False, alt: bool = False):
        n = len(cells)
        if n == 0:
            return
        col_w = CONTENT_W / n
        row_h = 6.5

        if is_header:
            self.set_fill_color(*C_TABLE_HDR)
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(*C_HEADING1)
        elif alt:
            self.set_fill_color(*C_TABLE_ALT)
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(*C_BLACK)
        else:
            self.set_fill_color(*C_WHITE)
            self.set_font("Helvetica", "", 8.5)
            self.set_text_color(*C_BLACK)

        self.set_draw_color(*C_RULE)
        self.set_x(MARGIN)
        for cell in cells:
            self.cell(col_w, row_h, _clean(cell)[:55], border=1, fill=True)
        self.ln(row_h)


def build_pdf():
    pdf = ManualPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(MARGIN, MARGIN, MARGIN)

    pdf.cover()

    # ── Parse markdown ────────────────────────────────────────────────────────
    with open(MD_PATH, encoding="utf-8") as f:
        lines = f.readlines()

    i = 0
    in_code  = False
    code_buf: list[str] = []
    in_table = False
    table_rows: list[list[str]] = []
    ol_counter = 0

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            return
        pdf.ln(2)
        for ri, row in enumerate(table_rows):
            pdf.table_row(row, is_header=(ri == 0), alt=(ri > 0 and ri % 2 == 0))
        pdf.ln(2)
        table_rows.clear()
        in_table = False

    while i < len(lines):
        raw = lines[i].rstrip("\n")
        i += 1
        stripped = raw.strip()

        # ── Code block toggle ─────────────────────────────────────────────
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                flush_table()
                pdf.code_block(code_buf)
            continue
        if in_code:
            code_buf.append(raw)
            continue

        # ── Table row ─────────────────────────────────────────────────────
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator line (|---|---|)
            if all(re.match(r"^[-: ]+$", c) for c in cells if c):
                in_table = True
                continue
            in_table = True
            table_rows.append(cells)
            continue
        else:
            if in_table:
                flush_table()
            ol_counter = 0

        # ── Horizontal rule ───────────────────────────────────────────────
        if stripped in ("---", "***", "___"):
            pdf.rule()
            continue

        # ── Blank line ────────────────────────────────────────────────────
        if not stripped:
            pdf.ln(2)
            ol_counter = 0
            continue

        # ── Headings ──────────────────────────────────────────────────────
        if stripped.startswith("# ") and not stripped.startswith("##"):
            pdf.h1(stripped[2:])
            continue
        if stripped.startswith("## ") and not stripped.startswith("###"):
            pdf.h2(stripped[3:])
            continue
        if stripped.startswith("### ") and not stripped.startswith("####"):
            pdf.h3(stripped[4:])
            continue
        if stripped.startswith("#### "):
            pdf.h4(stripped[5:])
            continue

        # ── Ordered list ──────────────────────────────────────────────────
        m = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m:
            ol_counter += 1
            pdf.numbered(ol_counter, m.group(2))
            continue

        # ── Unordered list ────────────────────────────────────────────────
        if stripped.startswith("- ") or stripped.startswith("* "):
            indent = (len(raw) - len(raw.lstrip())) // 2
            pdf.bullet(stripped[2:], indent=indent)
            continue

        # ── TOC entries (indented with spaces) ────────────────────────────
        if raw.startswith("   "):
            pdf.set_font("Helvetica", "", 8.5)
            pdf.set_text_color(*C_MUTED)
            pdf.set_x(MARGIN + 6)
            pdf.multi_cell(CONTENT_W - 6, 5, _clean(stripped))
            continue

        # ── Normal paragraph ──────────────────────────────────────────────
        if stripped:
            pdf.para(stripped)

    # Final flush
    flush_table()

    pdf.output(PDF_PATH)
    size_kb = os.path.getsize(PDF_PATH) // 1024
    print(f"PDF saved  -> {PDF_PATH}")
    print(f"File size  -> {size_kb} KB")


if __name__ == "__main__":
    build_pdf()
