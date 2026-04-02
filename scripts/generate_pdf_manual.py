import os
import re
from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, 'PROJECT: AI SONGWRITING SYSTEM', border=0, align='L')
        self.cell(0, 10, 'CONFIDENTIAL', border=0, align='R')
        self.ln(15)

    def footer(self):
        self.set_y(-15)
        self.set_font('helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Page {self.page_no()} | Technical White Paper v1.0', 0, 0, 'C')

def sanitize_text(text):
    """Sanitize text for Latin-1 encoding."""
    replacements = {
        "’": "'", "‘": "'", "“": "\"", "”": "\"",
        "–": "-", "—": "--", "✅": "[OK]", "🧪": "",
        "📖": "", "⚙️": "", "🚦": "", "🏗️": "",
        "🎶": "", "🎼": "", "🎵": "", "📑": "",
        "✨": "*", "🟢": "(High)", "🟡": "(Fair)", "🔴": "(Low)",
        "⏱": "[Time]", "⭐": "*", "🔥": "!"
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # Simple formatting cleanup for table cells (remove MD bold/italic markers)
    text = text.replace("**", "").replace("_", "")
    
    return text.encode('latin-1', 'replace').decode('latin-1')

def apply_text_formatting(text):
    """Apply basic HTML formatting for write_html."""
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    # Italic
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    # Code
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # Character sanitize
    replacements = {
        "’": "'", "‘": "'", "“": "\"", "”": "\"",
        "–": "-", "—": "--", "✅": "[OK]", "🟢": "(High)", "🟡": "(Fair)", "🔴": "(Low)",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
        
    return text.encode('latin-1', 'replace').decode('latin-1')

def md_to_blocks(md_text):
    """Split markdown into logical blocks."""
    lines = md_text.split('\n')
    blocks = []
    current_block = []
    block_type = None

    for line in lines:
        stripped = line.strip()
        
        # 1. Headers
        if re.match(r'^#+ ', stripped):
            if current_block:
                blocks.append((block_type, current_block))
            blocks.append(('header', [stripped]))
            current_block = []
            block_type = None
            continue
            
        # 2. Horizontal Rules
        if stripped == '---':
            if current_block:
                blocks.append((block_type, current_block))
            blocks.append(('hr', [stripped]))
            current_block = []
            block_type = None
            continue
            
        # 3. Tables
        if stripped.startswith('|'):
            if block_type != 'table' and current_block:
                blocks.append((block_type, current_block))
                current_block = []
            block_type = 'table'
            current_block.append(stripped)
            continue
            
        # 4. Empty Lines (end current block)
        if stripped == '':
            if current_block:
                blocks.append((block_type, current_block))
                current_block = []
                block_type = None
            continue
            
        # Default: Text block (Paragraphs or Lists)
        if block_type == 'table':
            blocks.append(('table', current_block))
            current_block = [stripped]
            block_type = 'text'
        else:
            if block_type is None: block_type = 'text'
            current_block.append(stripped)
            
    if current_block:
        blocks.append((block_type, current_block))
        
    return blocks

def generate_pdf():
    # Use relative paths from script location or absolute paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    input_path = os.path.join(base_dir, "docs", "SYSTEM_MANUAL.md")
    output_path = os.path.join(base_dir, "AI_Songwriting_System_Manual.pdf")

    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    blocks = md_to_blocks(md_content)

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    
    for b_type, b_lines in blocks:
        if b_type == 'header':
            line = b_lines[0]
            m = re.match(r'^(#+) (.*)$', line)
            level = len(m.group(1))
            text = apply_text_formatting(m.group(2))
            tag = f"h{min(level, 3)}"
            pdf.write_html(f"<{tag}>{text}</{tag}>")
            pdf.ln(2)
            
        elif b_type == 'hr':
            pdf.ln(5)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(5)
            
        elif b_type == 'table':
            # Pre-process rows to filter out MD separators
            table_rows = []
            for r in b_lines:
                if re.match(r'^\|[:\s-]+\|$', r) or '---' in r:
