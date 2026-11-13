"""
app.py - Webové rozhraní Streamlit pro generování a tisk křížovek spolku Pionýr

Architektura UI:
- Archetype A: Warm Editorial & Technical Monograph (Newsreader + Plus Jakarta Sans + JetBrains Mono)
- Striktní sémantické CSS proměnné v :root, nulové inline hex barvy, nulové emoji v UI
- Asymetrická tiráž (8/4 sloupce), architektonická mřížka křížovky a dvoustránkový rejstřík nápověd
"""

from __future__ import annotations

import html
import os
from typing import Optional

import streamlit as st

from crawler import PionyrCrawler
from extractor import (
    GeminiExtractor,
    deduplicate_items,
    load_questions,
    save_questions,
)
from generator import CrosswordGenerator, CrosswordPuzzle
from pdf_exporter import export_crossword_pdf, generate_printable_html
from utils import normalize_answer

# ---------------------------------------------------------------------------
# Konfigurace stránky Streamlit
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Pionýr Crossword — Redakční generátor křížovek",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Architektonický CSS systém (Warm Editorial & Technical Monograph)
# ---------------------------------------------------------------------------
st.markdown(
    """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=Plus+Jakarta+Sans:wght@400;500;600&display=swap" rel="stylesheet">

<style>
    @layer base, theme, components, utilities;

    @layer theme {
        :root {
            --bg-paper: #F3F2EE;
            --bg-secondary: #E8E6E0;
            --bg-elevated: #FAF9F6;
            --ink-primary: #1C1B18;
            --ink-secondary: #5C5A54;
            --ink-muted: #8A8780;
            --accent: #E04F16;
            --accent-surface: color-mix(in oklab, var(--accent) 12%, var(--bg-elevated));
            --border-hairline: rgba(28, 27, 24, 0.14);
            --border-grid: rgba(28, 27, 24, 0.28);
            --border-strong: #1C1B18;
            --font-display: 'Newsreader', Georgia, serif;
            --font-body: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --radius-none: 0px;
            --radius-tactile: 4px;
            --ease-out: cubic-bezier(0.22, 1, 0.36, 1);
        }
    }

    @layer base {
        .stApp {
            background-color: var(--bg-paper);
            color: var(--ink-primary);
            font-family: var(--font-body);
            overflow-x: hidden;
        }

        section[data-testid="stSidebar"] {
            background-color: var(--bg-secondary);
            border-inline-end: 1px solid var(--border-hairline);
        }

        section[data-testid="stSidebar"] .block-container {
            padding-block-start: 2rem;
        }

        .main .block-container {
            max-width: 1280px;
            padding-block: 2.25rem 4rem;
            container-type: inline-size;
            container-name: editorial-workspace;
        }

        h1, h2, h3, h4 {
            font-family: var(--font-display);
            font-style: normal;
            font-weight: 400;
            letter-spacing: -0.02em;
            color: var(--ink-primary);
        }

        p, li, label, div[data-testid="stMarkdownContainer"] {
            font-family: var(--font-body);
            color: var(--ink-primary);
            line-height: 1.6;
        }

        hr {
            border: none;
            border-block-start: 1px solid var(--border-hairline);
            margin-block: 1.5rem;
        }
    }

    @layer components {
        /* Tlačítka a formulářové prvky ve Streamlitu */
        .stButton > button,
        .stDownloadButton > button {
            border-radius: var(--radius-tactile);
            border: 1px solid var(--border-grid);
            background-color: var(--bg-elevated);
            color: var(--ink-primary);
            font-family: var(--font-body);
            font-weight: 500;
            font-size: 0.875rem;
            padding: 0.5rem 0.9rem;
            transition: transform 160ms var(--ease-out), opacity 160ms var(--ease-out);
        }

        .stButton > button:hover:not(:disabled),
        .stDownloadButton > button:hover:not(:disabled) {
            border-color: var(--ink-primary);
            color: var(--ink-primary);
            transform: translateY(-1px);
        }

        .stButton > button[kind="primary"] {
            background-color: var(--accent);
            border-color: var(--accent);
            color: var(--bg-elevated);
        }

        .stButton > button[kind="primary"]:hover:not(:disabled) {
            background-color: var(--ink-primary);
            border-color: var(--ink-primary);
            color: var(--bg-elevated);
        }

        /* Asymetrická tiráž (Masthead: 8 sloupců vlevo | 4 sloupce vpravo) */
        .editorial-masthead {
            display: grid;
            grid-template-columns: 8fr 4fr;
            gap: 2.5rem;
            align-items: end;
            padding-block-end: 1.75rem;
            margin-block-end: 1.75rem;
            border-block-end: 1px solid var(--border-hairline);
        }

        .masthead-title {
            font-family: var(--font-display);
            font-size: clamp(2rem, 1.4rem + 2.2vw, 3.25rem);
            font-weight: 400;
            font-style: normal;
            letter-spacing: -0.025em;
            line-height: 1.08;
            color: var(--ink-primary);
            margin: 0 0 0.65rem 0;
        }

        .masthead-lead {
            font-family: var(--font-body);
            font-size: 1rem;
            line-height: 1.6;
            color: var(--ink-secondary);
            max-width: 62ch;
            margin: 0;
        }

        .masthead-lead a,
        .editorial-link {
            color: var(--ink-primary);
            text-decoration: underline;
            text-decoration-color: var(--accent);
            text-underline-offset: 3px;
            transition: opacity 150ms var(--ease-out);
        }

        .masthead-lead a:hover,
        .editorial-link:hover {
            opacity: 0.72;
        }

        .masthead-meta {
            border-inline-start: 1px solid var(--border-hairline);
            padding-inline-start: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
        }

        .meta-row {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            font-size: 0.84rem;
            padding-block: 0.2rem;
        }

        .meta-row:not(:last-child) {
            border-block-end: 1px solid var(--border-hairline);
        }

        .meta-label {
            color: var(--ink-secondary);
            font-family: var(--font-body);
        }

        .meta-value {
            color: var(--ink-primary);
            font-family: var(--font-mono);
            font-size: 0.82rem;
            font-weight: 500;
        }

        /* Architektonický list křížovky */
        .crossword-sheet {
            background-color: var(--bg-elevated);
            border: 1px solid var(--border-hairline);
            border-radius: var(--radius-none);
            margin-block: 1.25rem 2rem;
        }

        .sheet-header {
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            padding: 0.75rem 1.25rem;
            border-block-end: 1px solid var(--border-hairline);
            background-color: var(--bg-paper);
        }

        .sheet-heading {
            font-family: var(--font-body);
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--ink-primary);
        }

        .sheet-metrics {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--ink-secondary);
        }

        .crossword-viewport {
            padding: 2rem 1.5rem;
            overflow-x: auto;
            display: flex;
            justify-content: flex-start;
        }

        .crossword-table {
            border-collapse: collapse;
            background-color: transparent;
        }

        .cw-cell {
            width: 40px;
            height: 40px;
            min-width: 40px;
            min-height: 40px;
            text-align: center;
            vertical-align: middle;
            position: relative;
            padding: 0;
            font-family: var(--font-mono);
            font-size: 1.05rem;
            font-weight: 600;
            line-height: 1;
        }

        .cw-cell.empty {
            background-color: var(--bg-paper);
            border: 1px solid var(--border-hairline);
        }

        .cw-cell.active {
            background-color: var(--bg-elevated);
            border: 1.5px solid var(--border-strong);
            color: var(--ink-primary);
        }

        .cw-cell.active.secret {
            background-color: var(--accent-surface);
            border: 1.5px solid var(--accent);
            box-shadow: inset 0 0 0 1px var(--accent);
        }

        .cw-num {
            position: absolute;
            top: 2px;
            left: 3px;
            font-family: var(--font-mono);
            font-size: 0.62rem;
            font-weight: 500;
            color: var(--ink-secondary);
            line-height: 1;
        }

        .cw-sec-num {
            position: absolute;
            bottom: 2px;
            right: 3px;
            font-family: var(--font-mono);
            font-size: 0.6rem;
            font-weight: 600;
            color: var(--accent);
            line-height: 1;
        }

        /* Řádek tajenky integrovaný do paty archu */
        .secret-ledger {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1rem 1.25rem;
            border-block-start: 1px solid var(--border-hairline);
            background-color: var(--bg-paper);
        }

        .secret-label-group {
            display: flex;
            flex-direction: column;
            gap: 0.15rem;
        }

        .secret-title {
            font-family: var(--font-body);
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--ink-primary);
        }

        .secret-caption {
            font-family: var(--font-body);
            font-size: 0.8rem;
            color: var(--ink-secondary);
        }

        .secret-cells-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
        }

        .sec-letter-box {
            width: 36px;
            height: 36px;
            border: 1.5px solid var(--accent);
            background-color: var(--bg-elevated);
            border-radius: var(--radius-none);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: var(--font-mono);
            font-weight: 600;
            font-size: 1rem;
            color: var(--ink-primary);
            position: relative;
            padding-block-start: 4px;
        }

        .sec-letter-idx {
            position: absolute;
            top: 2px;
            left: 3px;
            font-family: var(--font-mono);
            font-size: 0.58rem;
            color: var(--accent);
            font-weight: 600;
            line-height: 1;
        }

        /* Rejstřík nápověd (Vodorovně / Svisle) */
        .clues-ledger {
            display: grid;
            grid-template-columns: 1fr 1fr;
            border-block: 1px solid var(--border-hairline);
            margin-block: 1.5rem 2.5rem;
        }

        .clues-column {
            padding-block: 1.25rem;
        }

        .clues-column:first-child {
            padding-inline-end: 2rem;
            border-inline-end: 1px solid var(--border-hairline);
        }

        .clues-column:last-child {
            padding-inline-start: 2rem;
        }

        .clues-heading {
            font-family: var(--font-display);
            font-size: clamp(1.25rem, 1rem + 0.6vw, 1.65rem);
            font-weight: 400;
            font-style: normal;
            margin: 0 0 1rem 0;
            padding-block-end: 0.6rem;
            border-block-end: 1px solid var(--border-strong);
            color: var(--ink-primary);
        }

        .clue-row {
            display: grid;
            grid-template-columns: 2.4rem 1fr auto;
            gap: 0.75rem;
            align-items: baseline;
            padding-block: 0.55rem;
            font-size: 0.925rem;
        }

        .clue-row:not(:last-child) {
            border-block-end: 1px solid var(--border-hairline);
        }

        .clue-num {
            font-family: var(--font-mono);
            font-size: 0.82rem;
            font-weight: 600;
            color: var(--ink-primary);
        }

        .clue-text {
            font-family: var(--font-body);
            color: var(--ink-primary);
            line-height: 1.5;
        }

        .clue-meta {
            font-family: var(--font-mono);
            font-size: 0.78rem;
            color: var(--ink-muted);
            white-space: nowrap;
            text-align: right;
        }

        .clue-solution {
            color: var(--accent);
            font-weight: 600;
            margin-inline-start: 0.4rem;
        }

        /* Technická specifikace (2-sloupcový rejstřík na konci stránky) */
        .spec-index {
            border-block-start: 1px solid var(--border-hairline);
            padding-block-start: 1.5rem;
            margin-block-start: 2rem;
        }

        .spec-index-title {
            font-family: var(--font-display);
            font-size: clamp(1.15rem, 0.95rem + 0.5vw, 1.4rem);
            font-weight: 400;
            margin: 0 0 0.85rem 0;
        }

        .spec-table {
            width: 100%;
            border-collapse: collapse;
        }

        .spec-table tr:not(:last-child) {
            border-block-end: 1px solid var(--border-hairline);
        }

        .spec-table th {
            width: 28%;
            text-align: left;
            vertical-align: top;
            padding: 0.6rem 1rem 0.6rem 0;
            font-family: var(--font-body);
            font-weight: 500;
            font-size: 0.875rem;
            color: var(--ink-secondary);
        }

        .spec-table td {
            padding: 0.6rem 0;
            font-family: var(--font-body);
            font-size: 0.875rem;
            color: var(--ink-primary);
        }

        .spec-code {
            font-family: var(--font-mono);
            font-size: 0.82rem;
            color: var(--ink-primary);
        }

        /* Boční panel (Sidebar) typografie */
        .sidebar-header {
            padding-block-end: 0.85rem;
            margin-block-end: 1rem;
            border-block-end: 1px solid var(--border-hairline);
        }

        .sidebar-brand {
            font-family: var(--font-display);
            font-size: 1.35rem;
            font-weight: 400;
            color: var(--ink-primary);
            margin: 0;
        }

        .sidebar-sub {
            font-family: var(--font-body);
            font-size: 0.8rem;
            color: var(--ink-secondary);
            margin: 0.15rem 0 0 0;
        }

        .sidebar-section-title {
            font-family: var(--font-display);
            font-size: 1.1rem;
            font-weight: 400;
            color: var(--ink-primary);
            margin: 0 0 0.65rem 0;
        }

        .status-notice {
            padding: 0.65rem 0.85rem;
            border: 1px solid var(--border-grid);
            background-color: var(--bg-elevated);
            font-size: 0.84rem;
            color: var(--ink-primary);
            margin-block: 0.65rem;
        }

        .status-notice.accent {
            border-color: var(--accent);
        }
    }

    @layer utilities {
        @container editorial-workspace (max-width: 768px) {
            .editorial-masthead {
                grid-template-columns: 1fr;
                gap: 1.25rem;
            }

            .masthead-meta {
                border-inline-start: none;
                border-block-start: 1px solid var(--border-hairline);
                padding-inline-start: 0;
                padding-block-start: 1rem;
            }

            .clues-ledger {
                grid-template-columns: 1fr;
            }

            .clues-column:first-child {
                padding-inline-end: 0;
                border-inline-end: none;
                border-block-end: 1px solid var(--border-hairline);
            }

            .clues-column:last-child {
                padding-inline-start: 0;
            }
        }

        @media (max-width: 768px) {
            .editorial-masthead {
                grid-template-columns: 1fr;
                gap: 1.25rem;
            }

            .masthead-meta {
                border-inline-start: none;
                border-block-start: 1px solid var(--border-hairline);
                padding-inline-start: 0;
                padding-block-start: 1rem;
            }

            .clues-ledger {
                grid-template-columns: 1fr;
            }

            .clues-column:first-child {
                padding-inline-end: 0;
                border-inline-end: none;
                border-block-end: 1px solid var(--border-hairline);
            }

            .clues-column:last-child {
                padding-inline-start: 0;
            }

            .spec-table th,
            .spec-table td {
                display: block;
                width: 100%;
                padding-block: 0.3rem;
            }
        }

        @media (forced-colors: active) {
            .cw-cell.active {
                border: 1.5px solid CanvasText;
            }
            .cw-cell.active.secret {
                border: 2px dashed Highlight;
                outline: 1px solid Highlight;
            }
            .sec-letter-box {
                border: 2px solid Highlight;
            }
        }
    }
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Inicializace stavu (Session State)
# ---------------------------------------------------------------------------
VOCABULARY_FILE = "pionyr_otazky.json"

if "puzzle" not in st.session_state:
    st.session_state.puzzle = None

if "show_solution" not in st.session_state:
    st.session_state.show_solution = False

if "generator" not in st.session_state:
    st.session_state.generator = CrosswordGenerator(vocabulary_path=VOCABULARY_FILE)

if "status_message" not in st.session_state:
    st.session_state.status_message = None


def reload_generator() -> None:
    """Znovu načte slovník do generátoru."""
    st.session_state.generator = CrosswordGenerator(vocabulary_path=VOCABULARY_FILE)


# ---------------------------------------------------------------------------
# Boční panel (Sidebar) — Konfigurace mřížky a správa slovníku
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-header">
            <h2 class="sidebar-brand">Pionýr Crossword</h2>
            <p class="sidebar-sub">Konfigurace mřížky a datového zdroje</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<h3 class="sidebar-section-title">Parametry mřížky</h3>', unsafe_allow_html=True)

    word_count = st.slider(
        "Počet výrazů v křížovce",
        min_value=8,
        max_value=18,
        value=12,
        help="Algoritmus vybere zadaný počet slov a vyhledá mřížku s nejvyšší hustotou křížení.",
    )

    secret_input = st.text_input(
        "Slovo tajenky (volitelné)",
        value="PIONYR",
        help="Cílové slovo složené z označených buněk (např. PIONYR, PRIRODA, TABOR, PARTA).",
    ).strip()

    if st.button("Sestavit novou mřížku", type="primary", use_container_width=True):
        with st.spinner("Probíhá výpočet průniků a ořez mřížky..."):
            norm_secret = normalize_answer(secret_input) if secret_input else None
            puzzle_result = st.session_state.generator.generate(
                word_count=word_count,
                secret_word=norm_secret,
            )
            if puzzle_result:
                st.session_state.puzzle = puzzle_result
                st.session_state.show_solution = False
                st.session_state.status_message = (
                    f"Mřížka {puzzle_result.width}×{puzzle_result.height} "
                    f"byla sestavena ({len(puzzle_result.words)} slov, "
                    f"{puzzle_result.total_intersections} křížení)."
                )
            else:
                st.session_state.status_message = (
                    "Se zadanými parametry se nepodařilo najít souvislou mřížku. "
                    "Upravte počet výrazů nebo tajenku."
                )

    if st.session_state.status_message:
        st.markdown(
            f'<div class="status-notice">{html.escape(st.session_state.status_message)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        '<h3 class="sidebar-section-title">Slovníková databáze a Gemini API</h3>',
        unsafe_allow_html=True,
    )

    vocab_count = len(st.session_state.generator.vocabulary)
    st.markdown(
        f"""
        <div class="meta-row" style="margin-block-end: 0.75rem;">
            <span class="meta-label">Aktivní slovník ({VOCABULARY_FILE})</span>
            <span class="meta-value">{vocab_count} pojmů</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    api_key_input = st.text_input(
        "Klíč Gemini API",
        type="password",
        value=os.getenv("GEMINI_API_KEY", ""),
        help="API klíč z Google AI Studio pro model gemini-2.5-flash.",
    )

    custom_url_input = st.text_input(
        "Extrakce z konkrétní adresy (URL)",
        placeholder="https://pionyr.cz/o-pionyru/historie/",
        key="custom_url_input",
    ).strip()

    if st.button("Extrahovat pojmy ze zadané adresy", type="secondary", use_container_width=True):
        if not api_key_input:
            st.markdown(
                '<div class="status-notice accent">Zadejte platný klíč Gemini API.</div>',
                unsafe_allow_html=True,
            )
        elif not custom_url_input or not custom_url_input.startswith("http"):
            st.markdown(
                '<div class="status-notice accent">Zadejte platnou adresu začínající http:// nebo https://.</div>',
                unsafe_allow_html=True,
            )
        else:
            with st.spinner("Stahuji dokument a extrahuji pojmy přes Gemini 2.5 Flash..."):
                try:
                    extractor = GeminiExtractor(api_key=api_key_input)
                    extracted_items = extractor.extract_from_url(custom_url_input)

                    if not extracted_items:
                        st.markdown(
                            '<div class="status-notice">Ze zadané adresy nebyly získány žádné nové pojmy.</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        existing = load_questions(VOCABULARY_FILE)
                        existing_answers = {it["answer"] for it in existing}

                        new_words = []
                        for it in extracted_items:
                            if it["answer"] not in existing_answers:
                                new_words.append(it)
                                existing_answers.add(it["answer"])

                        if new_words:
                            updated_all = existing + new_words
                            save_questions(updated_all, VOCABULARY_FILE)
                            reload_generator()
                            st.markdown(
                                f'<div class="status-notice accent">Přidáno {len(new_words)} nových hesel. '
                                f'Celkem v databázi: {len(updated_all)}.</div>',
                                unsafe_allow_html=True,
                            )
                            with st.expander(f"Přehled přidaných hesel ({len(new_words)})", expanded=True):
                                for w in new_words:
                                    st.markdown(f"- `{w['answer']}` — {w['clue']}")
                        else:
                            st.markdown(
                                f'<div class="status-notice">Získáno {len(extracted_items)} pojmů, '
                                f'všechny se již v databázi nacházejí.</div>',
                                unsafe_allow_html=True,
                            )
                except Exception as e:
                    st.markdown(
                        f'<div class="status-notice accent">Chyba při zpracování adresy: {html.escape(str(e))}</div>',
                        unsafe_allow_html=True,
                    )

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(
        '<h3 class="sidebar-section-title">Hromadný sběr z pionyr.cz</h3>',
        unsafe_allow_html=True,
    )

    crawl_pages_count = st.number_input(
        "Maximální počet procházených stránek",
        min_value=3,
        max_value=30,
        value=8,
        step=1,
    )

    if st.button("Spustit průchod webu a aktualizovat slovník", use_container_width=True):
        if not api_key_input:
            st.markdown(
                '<div class="status-notice accent">Pro spuštění extrakce vyplňte klíč Gemini API výše.</div>',
                unsafe_allow_html=True,
            )
        else:
            progress_bar = st.progress(0, text="Inicializace průchodu sitemap.xml na pionyr.cz...")
            try:
                crawler = PionyrCrawler()
                progress_bar.progress(15, text="Stahuji textový obsah podstránek pionyr.cz...")
                pages = crawler.crawl(max_pages=crawl_pages_count)
                progress_bar.progress(
                    50,
                    text=f"Staženo {len(pages)} stránek. Zpracování přes Gemini 2.5 Flash...",
                )

                extractor = GeminiExtractor(api_key=api_key_input)
                new_items = extractor.process_crawled_data(pages)
                progress_bar.progress(85, text="Normalizace NFKD a deduplikace slovníku...")

                if new_items:
                    existing = load_questions(VOCABULARY_FILE)
                    combined = deduplicate_items(existing + new_items)
                    save_questions(combined, VOCABULARY_FILE)
                    reload_generator()
                    progress_bar.progress(100, text="Aktualizace dokončena.")
                    st.markdown(
                        f'<div class="status-notice accent">Extrahováno {len(new_items)} pojmů. '
                        f'Celkem v databázi: {len(combined)}.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        '<div class="status-notice">Z procházených stránek nebyly získány žádné nové pojmy.</div>',
                        unsafe_allow_html=True,
                    )
            except Exception as e:
                st.markdown(
                    f'<div class="status-notice accent">Chyba při stahování dat: {html.escape(str(e))}</div>',
                    unsafe_allow_html=True,
                )


# ---------------------------------------------------------------------------
# Výchozí sestavení křížovky při prvním načtení
# ---------------------------------------------------------------------------
if st.session_state.puzzle is None:
    norm_secret = normalize_answer(secret_input) if secret_input else None
    st.session_state.puzzle = st.session_state.generator.generate(
        word_count=word_count,
        secret_word=norm_secret,
    )

puzzle: Optional[CrosswordPuzzle] = st.session_state.puzzle


# ---------------------------------------------------------------------------
# Asymetrická tiráž (Masthead: 8 sloupců vlevo | 4 sloupce technických dat vpravo)
# ---------------------------------------------------------------------------
grid_dims = f"{puzzle.width}×{puzzle.height}" if puzzle else "—"
placed_count = f"{len(puzzle.words)}" if puzzle else "0"
intersection_info = (
    f"{puzzle.total_intersections} ({puzzle.density_ratio:.1f})" if puzzle else "—"
)

st.markdown(
    f"""
    <header class="editorial-masthead">
        <div>
            <h1 class="masthead-title">Pionýr Crossword</h1>
            <p class="masthead-lead">
                Redakční generátor křížovkových mřížek pro oddíly a publikace spolku Pionýr.
                Slovní zásoba je extrahována z veřejného archivu
                <a href="https://pionyr.cz" target="_blank" rel="noopener noreferrer">pionyr.cz ↗</a>
                pomocí strukturovaného schématu v modelu Gemini 2.5 Flash a skládána
                do ortogonální mřížky s automatickou kontrolou sousednosti.
            </p>
        </div>
        <div class="masthead-meta" aria-label="Technické parametry sestavy">
            <div class="meta-row">
                <span class="meta-label">Slovníkový korpus</span>
                <span class="meta-value">{len(st.session_state.generator.vocabulary)} hesel</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">Rozměr aktivní mřížky</span>
                <span class="meta-value">{grid_dims} buněk</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">Zařazené výrazy</span>
                <span class="meta-value">{placed_count} slov</span>
            </div>
            <div class="meta-row">
                <span class="meta-label">Průniky (hustota)</span>
                <span class="meta-value">{intersection_info}</span>
            </div>
        </div>
    </header>
    """,
    unsafe_allow_html=True,
)

if not puzzle:
    st.markdown(
        '<div class="status-notice accent">'
        "Nebyla sestavena žádná platná mřížka. V levém panelu upravte počet výrazů nebo tajenku "
        "a stiskněte tlačítko Sestavit novou mřížku."
        "</div>",
        unsafe_allow_html=True,
    )
    st.stop()


# ---------------------------------------------------------------------------
# Řídicí lišta (Řešení a tiskové výstupy)
# ---------------------------------------------------------------------------
ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([1.4, 1.4, 1.4, 1.8])

with ctrl_col1:
    toggle_label = "Skrýt řešení v mřížce" if st.session_state.show_solution else "Zobrazit řešení v mřížce"
    if st.button(toggle_label, use_container_width=True):
        st.session_state.show_solution = not st.session_state.show_solution
        st.rerun()

with ctrl_col2:
    try:
        pdf_bytes_clean = export_crossword_pdf(puzzle, show_solution=False)
        st.download_button(
            label="Stáhnout PDF k luštění",
            data=pdf_bytes_clean,
            file_name="pionyrska_krizovka.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception:
        html_clean = generate_printable_html(puzzle, show_solution=False)
        st.download_button(
            label="Stáhnout tiskové HTML",
            data=html_clean,
            file_name="pionyrska_krizovka.html",
            mime="text/html",
            use_container_width=True,
        )

with ctrl_col3:
    try:
        pdf_bytes_sol = export_crossword_pdf(puzzle, show_solution=True)
        st.download_button(
            label="Stáhnout PDF s řešením",
            data=pdf_bytes_sol,
            file_name="pionyrska_krizovka_reseni.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception:
        html_sol = generate_printable_html(puzzle, show_solution=True)
        st.download_button(
            label="Stáhnout HTML s řešením",
            data=html_sol,
            file_name="pionyrska_krizovka_reseni.html",
            mime="text/html",
            use_container_width=True,
        )

with ctrl_col4:
    html_print_view = generate_printable_html(puzzle, show_solution=st.session_state.show_solution)
    st.download_button(
        label="Exportovat samostatné HTML (A4)",
        data=html_print_view,
        file_name="pionyrska_krizovka_arch.html",
        mime="text/html",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Architektonický arch křížovky + integrovaný řádek tajenky
# ---------------------------------------------------------------------------
secret_map = {(sc.x, sc.y): sc for sc in puzzle.secret_cells}
show_sol = st.session_state.show_solution

rows_html = []
for y in range(puzzle.height):
    cells_html = []
    for x in range(puzzle.width):
        char = puzzle.grid[y][x]
        if char:
            is_secret = (x, y) in secret_map
            num = puzzle.cell_numbers[y][x]

            num_span = f'<span class="cw-num">{num}</span>' if num > 0 else ""
            sec_span = (
                f'<span class="cw-sec-num">({secret_map[(x, y)].order_index})</span>'
                if is_secret
                else ""
            )
            char_disp = html.escape(char) if show_sol else ""
            cell_cls = "cw-cell active secret" if is_secret else "cw-cell active"

            cells_html.append(f'<td class="{cell_cls}">{num_span}{sec_span}{char_disp}</td>')
        else:
            cells_html.append('<td class="cw-cell empty" aria-hidden="true"></td>')

    rows_html.append("<tr>" + "".join(cells_html) + "</tr>")

secret_ledger_html = ""
if puzzle.secret_cells:
    sorted_secret = sorted(puzzle.secret_cells, key=lambda s: s.order_index)
    sec_boxes = []
    for sc in sorted_secret:
        letter = html.escape(sc.char) if show_sol else "&nbsp;"
        sec_boxes.append(
            f'<div class="sec-letter-box">'
            f'<span class="sec-letter-idx">{sc.order_index}</span>'
            f"{letter}"
            f"</div>"
        )

    secret_ledger_html = (
        f'<div class="secret-ledger">'
        f'<div class="secret-label-group">'
        f'<span class="secret-title">Tajenka ({len(sorted_secret)} znaků)</span>'
        f'<span class="secret-caption">Pořadí písmen odpovídá indexům v závorce v pravém dolním rohu zvýrazněných políček.</span>'
        f"</div>"
        f'<div class="secret-cells-row">{"".join(sec_boxes)}</div>'
        f"</div>"
    )

mode_label = "Kontrolní arch s řešením" if show_sol else "Luštitelský arch bez nápovědy"
sheet_markup = (
    f'<section class="crossword-sheet" aria-label="Křížovková mřížka">'
    f'<div class="sheet-header">'
    f'<span class="sheet-heading">{mode_label}</span>'
    f'<span class="sheet-metrics">{puzzle.width}×{puzzle.height} · '
    f'vodorovně {len(puzzle.across_clues)} · svisle {len(puzzle.down_clues)}</span>'
    f"</div>"
    f'<div class="crossword-viewport">'
    f'<table class="crossword-table">{"".join(rows_html)}</table>'
    f"</div>"
    f"{secret_ledger_html}"
    f"</section>"
)
st.markdown(sheet_markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Dvousloupcový rejstřík otázek (Vodorovně | Svisle)
# ---------------------------------------------------------------------------
def build_clue_rows(clues_list, show_solution_flag: bool) -> str:
    if not clues_list:
        return '<div class="clue-row"><span class="clue-num">—</span><span class="clue-text">Žádné položky v tomto směru.</span><span class="clue-meta"></span></div>'

    items = []
    for w in clues_list:
        sol_html = (
            f'<span class="clue-solution">{html.escape(w.word)}</span>'
            if show_solution_flag
            else ""
        )
        items.append(
            f'<div class="clue-row">'
            f'<span class="clue-num">{w.number}.</span>'
            f'<span class="clue-text">{html.escape(w.clue)}</span>'
            f'<span class="clue-meta">{len(w.word)} zn.{sol_html}</span>'
            f"</div>"
        )
    return "".join(items)


across_rows_html = build_clue_rows(puzzle.across_clues, show_sol)
down_rows_html = build_clue_rows(puzzle.down_clues, show_sol)

clues_markup = f"""
<section class="clues-ledger" aria-label="Seznam křížovkových nápověd">
    <div class="clues-column">
        <h2 class="clues-heading">Vodorovně</h2>
        {across_rows_html}
    </div>
    <div class="clues-column">
        <h2 class="clues-heading">Svisle</h2>
        {down_rows_html}
    </div>
</section>
"""
st.markdown(clues_markup, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Technická specifikace a parametry tisku (nahrazuje dekorativní nápovědu)
# ---------------------------------------------------------------------------
st.markdown(
    """
<footer class="spec-index">
    <h2 class="spec-index-title">Technická specifikace a tisková příprava</h2>
    <table class="spec-table">
        <tr>
            <th>Tiskový výstup A4</th>
            <td>Vektorový dokument PDF sestavený knihovnou ReportLab nebo samostatný soubor HTML se stylopisem <span class="spec-code">@page { size: A4 portrait; }</span> pro přímý tisk z prohlížeče.</td>
        </tr>
        <tr>
            <th>Normalizace hesel</th>
            <td>Odpovědi jsou převáděny přes <span class="spec-code">unicodedata.normalize('NFKD')</span> na bezdiakritická velká písmena v rozsahu <span class="spec-code">3–12</span> znaků.</td>
        </tr>
        <tr>
            <th>Algoritmus mřížky</th>
            <td>Vícenásobný hladový průchod s maximalizací počtu ortogonálních průniků, automatickou kontrolou nežádoucích dotyků sousedních slov a ořezem na minimální obdélník.</td>
        </tr>
    </table>
</footer>
""",
    unsafe_allow_html=True,
)
