"""
pdf_exporter.py - Export křížovky do formátu PDF (ReportLab) a tiskového HTML

Architektura výstupu:
- Archetype A: Warm Editorial & Technical Monograph (#F3F2EE / #FAF9F6 / #1C1B18 / #E04F16)
- Striktní sémantické CSS proměnné v :root pro samostatný tiskový HTML arch
- Vektorové A4 PDF v teplé monochromatické škále s jedním akcentem (International Orange)
"""

from __future__ import annotations

import html as html_lib
import io
import logging
import os
from typing import Optional

from generator import CrosswordPuzzle
from utils import remove_diacritics

logger = logging.getLogger("PdfExporter")


def get_available_font_name() -> str:
    """
    Pokusí se zaregistrovat český TTF font v ReportLabu.
    Pokud žádný není dostupný, vrátí Helvetica.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_paths = [
            "/System/Library/Fonts/Supplemental/Georgia.ttf",
            "/System/Library/Fonts/Supplemental/Verdana.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

        for path in font_paths:
            if os.path.exists(path):
                try:
                    pdfmetrics.registerFont(TTFont("CzechFont", path))
                    return "CzechFont"
                except Exception as e:
                    logger.debug(f"Nelze načíst font {path}: {e}")

    except ImportError:
        pass

    return "Helvetica"


def export_crossword_pdf(
    puzzle: CrosswordPuzzle,
    output_path: Optional[str] = None,
    show_solution: bool = False,
    title: str = "Pionýrská křížovka",
) -> bytes:
    """
    Vygeneruje PDF dokument s křížovkou v estetice Warm Editorial Monograph.
    Vrací bajty PDF souboru.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.pdfgen import canvas
    except ImportError:
        raise RuntimeError(
            "Knihovna 'reportlab' není nainstalována. Spusťte: pip install reportlab"
        )

    font_name = get_available_font_name()
    has_custom_font = font_name != "Helvetica"

    def safe_text(text: str) -> str:
        """Pokud nemáme font s plnou českou podporou, bezpečně odstraníme diakritiku."""
        if has_custom_font:
            return text
        return remove_diacritics(text)

    # Sémantické barevné tokeny (Archetype A: Warm Editorial & Technical Monograph)
    ink_primary = colors.HexColor("#1C1B18")
    ink_secondary = colors.HexColor("#5C5A54")
    ink_muted = colors.HexColor("#8A8780")
    surface_elevated = colors.HexColor("#FAF9F6")
    surface_secondary = colors.HexColor("#E8E6E0")
    accent_orange = colors.HexColor("#E04F16")

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4

    margin = 36
    usable_width = page_width - 2 * margin

    # -----------------------------------------------------------------------
    # 1. Asymetrické záhlaví (Tiráž)
    # -----------------------------------------------------------------------
    c.setFont(font_name, 20)
    c.setFillColor(ink_primary)
    c.drawString(margin, page_height - 46, safe_text(title))

    c.setFont(font_name, 9)
    c.setFillColor(ink_secondary)
    c.drawString(
        margin,
        page_height - 61,
        safe_text(
            f"Pionýr Crossword · Rozměr {puzzle.width}x{puzzle.height} · "
            f"{len(puzzle.words)} výrazů · pionyr.cz"
        ),
    )

    if show_solution:
        c.setFont(font_name, 10)
        c.setFillColor(accent_orange)
        c.drawRightString(
            page_width - margin,
            page_height - 46,
            safe_text("Kontrolní arch s řešením"),
        )

    # Dělící linka záhlaví
    c.setStrokeColor(surface_secondary)
    c.setLineWidth(1)
    c.line(margin, page_height - 70, page_width - margin, page_height - 70)

    # -----------------------------------------------------------------------
    # 2. Vykreslení mřížky (zarovnané k levé vertikální ose)
    # -----------------------------------------------------------------------
    max_grid_width = usable_width
    max_grid_height = 275

    cell_size = min(
        max_grid_width / puzzle.width,
        max_grid_height / puzzle.height,
        24,
    )

    grid_px_height = puzzle.height * cell_size
    grid_start_x = margin
    grid_start_y = page_height - 86

    secret_map = {(sc.x, sc.y): sc for sc in puzzle.secret_cells}

    for y in range(puzzle.height):
        for x in range(puzzle.width):
            char = puzzle.grid[y][x]
            cell_x = grid_start_x + x * cell_size
            cell_y = grid_start_y - (y + 1) * cell_size

            if char:
                is_secret = (x, y) in secret_map
                if is_secret:
                    c.setFillColor(surface_secondary)
                else:
                    c.setFillColor(surface_elevated)

                c.rect(cell_x, cell_y, cell_size, cell_size, fill=1, stroke=0)

                if is_secret:
                    c.setStrokeColor(accent_orange)
                    c.setLineWidth(1.2)
                else:
                    c.setStrokeColor(ink_primary)
                    c.setLineWidth(0.9)
                c.rect(cell_x, cell_y, cell_size, cell_size, fill=0, stroke=1)

                cell_num = puzzle.cell_numbers[y][x]
                if cell_num > 0:
                    c.setFont(font_name, max(6, cell_size * 0.30))
                    c.setFillColor(ink_secondary)
                    c.drawString(
                        cell_x + 2,
                        cell_y + cell_size - (cell_size * 0.34),
                        str(cell_num),
                    )

                if is_secret:
                    sc = secret_map[(x, y)]
                    c.setFont(font_name, max(5, cell_size * 0.27))
                    c.setFillColor(accent_orange)
                    c.drawRightString(
                        cell_x + cell_size - 2,
                        cell_y + 2,
                        f"({sc.order_index})",
                    )

                if show_solution:
                    c.setFont(font_name, max(9, cell_size * 0.56))
                    c.setFillColor(ink_primary)
                    c.drawCentredString(
                        cell_x + cell_size / 2,
                        cell_y + (cell_size * 0.24),
                        char,
                    )

    # -----------------------------------------------------------------------
    # 3. Řádek tajenky pod mřížkou
    # -----------------------------------------------------------------------
    clues_start_y = grid_start_y - grid_px_height - 22

    if puzzle.secret_cells:
        c.setFont(font_name, 10)
        c.setFillColor(ink_primary)
        c.drawString(margin, clues_start_y, safe_text("Tajenka:"))

        sec_box_size = 18
        sec_start_x = margin + 54
        for i, sc in enumerate(sorted(puzzle.secret_cells, key=lambda s: s.order_index)):
            bx = sec_start_x + i * (sec_box_size + 4)
            by = clues_start_y - 4

            c.setFillColor(surface_elevated)
            c.rect(bx, by, sec_box_size, sec_box_size, fill=1, stroke=0)
            c.setStrokeColor(accent_orange)
            c.setLineWidth(1)
            c.rect(bx, by, sec_box_size, sec_box_size, fill=0, stroke=1)

            c.setFont(font_name, 6)
            c.setFillColor(accent_orange)
            c.drawString(bx + 2, by + sec_box_size - 6, str(sc.order_index))

            if show_solution:
                c.setFont(font_name, 9.5)
                c.setFillColor(ink_primary)
                c.drawCentredString(bx + sec_box_size / 2, by + 3.5, sc.char)

        clues_start_y -= 26

    # -----------------------------------------------------------------------
    # 4. Dvousloupcový rejstřík otázek (Vodorovně | Svisle)
    # -----------------------------------------------------------------------
    col_width = (usable_width - 24) / 2
    col1_x = margin
    col2_x = margin + col_width + 24

    c.setStrokeColor(surface_secondary)
    c.setLineWidth(1)
    c.line(margin, clues_start_y + 8, page_width - margin, clues_start_y + 8)
    clues_start_y -= 8

    c.setFont(font_name, 11)
    c.setFillColor(ink_primary)
    c.drawString(col1_x, clues_start_y, safe_text("Vodorovně"))
    c.drawString(col2_x, clues_start_y, safe_text("Svisle"))

    def render_clues_column(clues_list, start_x, start_y):
        cur_y = start_y - 16
        for w in clues_list:
            if cur_y < 36:
                break

            line_prefix = f"{w.number}. "
            c.setFont(font_name, 8.5)
            c.setFillColor(ink_primary)

            full_text = safe_text(f"{line_prefix}{w.clue} ({len(w.word)} zn.)")
            if show_solution:
                full_text += f" · {w.word}"

            words_in_clue = full_text.split()
            current_line = ""

            for cw in words_in_clue:
                test_line = f"{current_line} {cw}".strip()
                text_w = c.stringWidth(test_line, font_name, 8.5)
                if text_w < col_width:
                    current_line = test_line
                else:
                    if cur_y >= 36:
                        c.drawString(start_x, cur_y, current_line)
                        cur_y -= 10.5
                    current_line = f"    {cw}"

            if current_line and cur_y >= 36:
                c.drawString(start_x, cur_y, current_line)
                cur_y -= 13

    render_clues_column(puzzle.across_clues, col1_x, clues_start_y)
    render_clues_column(puzzle.down_clues, col2_x, clues_start_y)

    # -----------------------------------------------------------------------
    # 5. Zápatí
    # -----------------------------------------------------------------------
    c.setFont(font_name, 8)
    c.setFillColor(ink_muted)
    c.drawString(
        margin,
        20,
        safe_text(
            "Pionýr Crossword · Redakční tiskový výstup pro oddíly spolku Pionýr (pionyr.cz)"
        ),
    )

    c.showPage()
    c.save()

    pdf_bytes = buffer.getvalue()
    buffer.close()

    if output_path:
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        logger.info(f"PDF bylo uloženo do: {output_path}")

    return pdf_bytes


def generate_printable_html(
    puzzle: CrosswordPuzzle,
    show_solution: bool = False,
    title: str = "Pionýrská křížovka",
) -> str:
    """
    Vygeneruje samostatný arch HTML v estetice Warm Editorial & Technical Monograph,
    optimalizovaný jak pro prohlížení v prohlížeči, tak pro přímý tisk A4 (@media print).
    """
    secret_map = {(sc.x, sc.y): sc for sc in puzzle.secret_cells}

    grid_rows_html = []
    for y in range(puzzle.height):
        cells_html = []
        for x in range(puzzle.width):
            char = puzzle.grid[y][x]
            if char:
                is_secret = (x, y) in secret_map
                num = puzzle.cell_numbers[y][x]
                num_html = f'<span class="num">{num}</span>' if num > 0 else ""
                secret_sub = (
                    f'<span class="sec-num">({secret_map[(x, y)].order_index})</span>'
                    if is_secret
                    else ""
                )
                letter_html = (
                    f'<span class="char">{html_lib.escape(char)}</span>'
                    if show_solution
                    else ""
                )
                bg_class = "cell active secret" if is_secret else "cell active"
                cells_html.append(
                    f'<td class="{bg_class}">{num_html}{secret_sub}{letter_html}</td>'
                )
            else:
                cells_html.append('<td class="cell empty" aria-hidden="true"></td>')
        grid_rows_html.append("<tr>" + "".join(cells_html) + "</tr>")

    table_html = '<table class="grid-table">' + "\n".join(grid_rows_html) + "</table>"

    secret_html = ""
    if puzzle.secret_cells:
        sec_boxes = []
        for sc in sorted(puzzle.secret_cells, key=lambda s: s.order_index):
            val = html_lib.escape(sc.char) if show_solution else "&nbsp;"
            sec_boxes.append(
                f'<div class="sec-box"><span class="sec-idx">{sc.order_index}</span>{val}</div>'
            )
        secret_html = f"""
        <div class="secret-container">
            <span class="secret-label">Tajenka ({len(puzzle.secret_cells)} znaků)</span>
            <div class="sec-boxes">{"".join(sec_boxes)}</div>
        </div>
        """

    across_items = "".join(
        f'<li><span class="clue-idx">{w.number}.</span> '
        f'<span class="clue-body">{html_lib.escape(w.clue)}</span> '
        f'<span class="clue-len">{len(w.word)} zn.'
        + (f' · <strong class="sol">{html_lib.escape(w.word)}</strong>' if show_solution else "")
        + "</span></li>"
        for w in puzzle.across_clues
    )

    down_items = "".join(
        f'<li><span class="clue-idx">{w.number}.</span> '
        f'<span class="clue-body">{html_lib.escape(w.clue)}</span> '
        f'<span class="clue-len">{len(w.word)} zn.'
        + (f' · <strong class="sol">{html_lib.escape(w.word)}</strong>' if show_solution else "")
        + "</span></li>"
        for w in puzzle.down_clues
    )

    mode_meta = "Kontrolní arch s řešením" if show_solution else "Luštitelský arch"

    html = f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_lib.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
    @layer base, components, print;

    @layer base {{
        :root {{
            --bg-paper: #F3F2EE;
            --bg-secondary: #E8E6E0;
            --bg-elevated: #FAF9F6;
            --ink-primary: #1C1B18;
            --ink-secondary: #5C5A54;
            --ink-muted: #8A8780;
            --accent: #E04F16;
            --accent-surface: color-mix(in oklab, var(--accent) 14%, var(--bg-elevated));
            --border-hairline: rgba(28, 27, 24, 0.14);
            --border-strong: #1C1B18;
            --font-display: 'Newsreader', Georgia, serif;
            --font-body: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }}

        @page {{
            size: A4 portrait;
            margin: 12mm 15mm;
        }}

        body {{
            font-family: var(--font-body);
            color: var(--ink-primary);
            background-color: var(--bg-paper);
            margin: 0;
            padding: 2rem;
            line-height: 1.5;
        }}
    }}

    @layer components {{
        .sheet {{
            max-width: 920px;
            margin: 0 auto;
        }}

        .header {{
            display: grid;
            grid-template-columns: 8fr 4fr;
            gap: 1.5rem;
            align-items: end;
            border-block-end: 1px solid var(--border-strong);
            padding-block-end: 0.75rem;
            margin-block-end: 1.25rem;
        }}

        .header h1 {{
            margin: 0;
            font-family: var(--font-display);
            font-weight: 400;
            font-style: normal;
            font-size: clamp(1.6rem, 1.2rem + 1.5vw, 2.25rem);
            letter-spacing: -0.02em;
            color: var(--ink-primary);
        }}

        .header p {{
            margin: 0.25rem 0 0 0;
            font-size: 0.82rem;
            color: var(--ink-secondary);
        }}

        .header-meta {{
            text-align: right;
            font-family: var(--font-mono);
            font-size: 0.76rem;
            color: var(--ink-secondary);
        }}

        .mode-status {{
            color: var(--accent);
            font-weight: 600;
            display: block;
        }}

        .grid-container {{
            display: flex;
            justify-content: flex-start;
            margin-block: 1rem;
            overflow-x: auto;
        }}

        .grid-table {{
            border-collapse: collapse;
        }}

        .cell {{
            width: 28px;
            height: 28px;
            text-align: center;
            vertical-align: middle;
            position: relative;
            padding: 0;
            font-family: var(--font-mono);
            font-size: 14px;
            font-weight: 600;
        }}

        .cell.empty {{
            background-color: transparent;
            border: 1px solid var(--border-hairline);
        }}

        .cell.active {{
            background-color: var(--bg-elevated);
            border: 1.5px solid var(--border-strong);
            color: var(--ink-primary);
        }}

        .cell.active.secret {{
            background-color: var(--accent-surface);
            border: 1.5px solid var(--accent);
        }}

        .num {{
            position: absolute;
            top: 1px;
            left: 2px;
            font-family: var(--font-mono);
            font-size: 7.5px;
            font-weight: 500;
            color: var(--ink-secondary);
            line-height: 1;
        }}

        .sec-num {{
            position: absolute;
            bottom: 1px;
            right: 2px;
            font-family: var(--font-mono);
            font-size: 7.5px;
            font-weight: 600;
            color: var(--accent);
            line-height: 1;
        }}

        .secret-container {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.75rem;
            padding-block: 0.75rem;
            margin-block: 0.75rem;
            border-block: 1px solid var(--border-hairline);
            font-size: 0.85rem;
        }}

        .secret-label {{
            font-weight: 600;
            color: var(--ink-primary);
        }}

        .sec-boxes {{
            display: flex;
            gap: 4px;
        }}

        .sec-box {{
            width: 26px;
            height: 26px;
            border: 1.5px solid var(--accent);
            background-color: var(--bg-elevated);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: 13px;
            padding-block-start: 3px;
        }}

        .sec-box .sec-idx {{
            position: absolute;
            top: 1px;
            left: 2px;
            font-size: 7px;
            color: var(--accent);
            line-height: 1;
        }}

        .clues-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2rem;
            margin-block-start: 1rem;
        }}

        .clues-col h2 {{
            font-family: var(--font-display);
            font-weight: 400;
            font-style: normal;
            font-size: 1.15rem;
            color: var(--ink-primary);
            margin: 0 0 0.5rem 0;
            border-block-end: 1px solid var(--border-strong);
            padding-block-end: 0.25rem;
        }}

        .clues-col ul {{
            list-style: none;
            padding: 0;
            margin: 0;
            font-size: 0.78rem;
            line-height: 1.45;
        }}

        .clues-col li {{
            display: grid;
            grid-template-columns: 1.8rem 1fr auto;
            gap: 0.4rem;
            padding-block: 0.3rem;
        }}

        .clues-col li:not(:last-child) {{
            border-block-end: 1px solid var(--border-hairline);
        }}

        .clue-idx {{
            font-family: var(--font-mono);
            font-weight: 600;
        }}

        .clue-len {{
            font-family: var(--font-mono);
            color: var(--ink-muted);
            white-space: nowrap;
        }}

        .sol {{
            color: var(--accent);
            font-weight: 600;
        }}

        .footer {{
            margin-block-start: 1.25rem;
            display: flex;
            justify-content: space-between;
            font-size: 0.72rem;
            color: var(--ink-muted);
            border-block-start: 1px solid var(--border-hairline);
            padding-block-start: 0.5rem;
        }}
    }}

    @layer print {{
        @media print {{
            body {{
                padding: 0;
                background-color: var(--bg-elevated);
            }}
        }}
    }}
</style>
</head>
<body>
    <main class="sheet">
        <header class="header">
            <div>
                <h1>{html_lib.escape(title)}</h1>
                <p>Pionýr, z. s. · Redakční sestava křížovkové mřížky · https://pionyr.cz</p>
            </div>
            <div class="header-meta">
                <span class="mode-status">{mode_meta}</span>
                <span>Mřížka {puzzle.width}×{puzzle.height} · {len(puzzle.words)} slov</span>
            </div>
        </header>

        <div class="grid-container">
            {table_html}
        </div>

        {secret_html}

        <section class="clues-grid">
            <div class="clues-col" data-direction="VODOROVNĚ">
                <h2>Vodorovně</h2>
                <ul>{across_items}</ul>
            </div>
            <div class="clues-col" data-direction="SVISLE">
                <h2>Svisle</h2>
                <ul>{down_items}</ul>
            </div>
        </section>

        <footer class="footer">
            <span>Pionýr Crossword</span>
            <span>Archiv pojmů: pionyr.cz</span>
        </footer>
    </main>
</body>
</html>
"""
    return html
