"""
crawler.py - Webový crawler pro stránky organizace Pionýr (https://pionyr.cz)

Tento modul prochází sitemap.xml a zanořené podstránky webu pionyr.cz,
filtruje nechtěné adresy (PDF, obrázky, admin, kontakty apod.)
a pomocí BeautifulSoup extrahuje čistý text článků a stránek.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse, urldefrag

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

# Nastavení logování
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("PionyrCrawler")


class PionyrCrawler:
    """
    Aktivní pavouk (crawler) pro web pionyr.cz.
    Prochází sitemap a zanořené odkazy, čistí HTML a extrahuje textový obsah.
    """

    BASE_URL = "https://pionyr.cz"
    SITEMAP_URLS = [
        "https://pionyr.cz/sitemap.xml",
        "https://pionyr.cz/wp-sitemap.xml",
        "https://pionyr.cz/wp-sitemap-posts-page-1.xml",
        "https://pionyr.cz/wp-sitemap-posts-post-1.xml",
    ]

    # Výchozí klíčové sekce pro zajištění bohatého obsahu o Pionýru
    SEED_URLS = [
        "https://pionyr.cz/",
        "https://pionyr.cz/o-pionyru/",
        "https://pionyr.cz/o-pionyru/idealy/",
        "https://pionyr.cz/o-pionyru/idealy/pamet/",
        "https://pionyr.cz/o-pionyru/idealy/pomoc/",
        "https://pionyr.cz/o-pionyru/idealy/poznani/",
        "https://pionyr.cz/o-pionyru/idealy/pravda/",
        "https://pionyr.cz/o-pionyru/idealy/pratelstvi/",
        "https://pionyr.cz/o-pionyru/idealy/prekonani/",
        "https://pionyr.cz/o-pionyru/idealy/priroda/",
        "https://pionyr.cz/o-pionyru/znak-maskot-a-logo-pionyra/",
        "https://pionyr.cz/o-pionyru/stanovy-a-program/",
        "https://pionyr.cz/o-pionyru/historie/",
        "https://pionyr.cz/cinnost/",
        "https://pionyr.cz/cinnost/souteze/sedmikvitek/",
        "https://pionyr.cz/rodice/dobryoddil/",
        "https://pionyr.cz/prehled-clanku/",
    ]

    # Přípony nechtěných souborů
    IGNORED_EXTENSIONS = (
        ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
        ".zip", ".rar", ".7z", ".tar", ".gz",
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".mp3", ".mp4", ".avi", ".mov", ".wav"
    )

    # Cesty a vzory URL k ignorování (admin, kontakty, účty, feedy)
    IGNORED_PATH_PATTERNS = [
        r"/wp-admin",
        r"/wp-login",
        r"/wp-json",
        r"/xmlrpc\.php",
        r"/feed",
        r"/comments",
        r"/kontakty",
        r"/vypis-zakladen",
        r"/login",
        r"/logout",
        r"/nastenka",
        r"/author",
        r"/tag/",
        r"/category/",
        r"returl=",
    ]

    def __init__(self, request_timeout: int = 10, user_agent: str | None = None):
        self.request_timeout = request_timeout
        self.headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 (PionyrCrosswordBot/1.0)",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        }
        self.visited_urls: Set[str] = set()

    def is_valid_url(self, url: str) -> bool:
        """
        Zkontroluje, zda daná URL patří na web pionyr.cz a není na černé listině.
        """
        if not url:
            return False

        parsed = urlparse(url)
        # Pouze HTTP a HTTPS na doméně pionyr.cz
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = (parsed.hostname or "").lower()
        if hostname not in ("pionyr.cz", "www.pionyr.cz"):
            return False

        path_lower = parsed.path.lower()

        # Filtrace souborových přípon
        for ext in self.IGNORED_EXTENSIONS:
            if path_lower.endswith(ext):
                return False

        # Filtrace ignorovaných vzorů
        full_url_lower = url.lower()
        for pattern in self.IGNORED_PATH_PATTERNS:
            if re.search(pattern, full_url_lower):
                return False

        return True

    def normalize_url(self, raw_url: str, current_page_url: str = BASE_URL) -> str | None:
        """
        Převede relativní odkaz na absolutní, odstraní kotvu (#fragment) a standardizuje.
        """
        if not raw_url or raw_url.startswith(("mailto:", "tel:", "javascript:", "#")):
            return None

        # Převod na absolutní URL
        abs_url = urljoin(current_page_url, raw_url)
        # Odstranění kotvy
        abs_url, _ = urldefrag(abs_url)

        # Standardizace schématu na https:// a oříznutí koncového lomítka (kromě kořene)
        if abs_url.startswith("http://"):
            abs_url = "https://" + abs_url[len("http://"):]

        parsed = urlparse(abs_url)
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        reconstructed = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            reconstructed += f"?{parsed.query}"

        return reconstructed

    def fetch_sitemap_urls(self) -> List[str]:
        """
        Pokusí se stáhnout a rozparsovat XML sitemap z několika známých umístění.
        Vrací seznam nalezených platných URL.
        """
        if requests is None:
            logger.warning("Knihovna 'requests' není nainstalována. Spusťte: pip install requests beautifulsoup4")
            return []

        found_urls: Set[str] = set()

        for sitemap_url in self.SITEMAP_URLS:
            try:
                logger.info(f"Pokus o stažení sitemap: {sitemap_url}")
                resp = requests.get(sitemap_url, headers=self.headers, timeout=self.request_timeout)
                if resp.status_code != 200:
                    continue

                content = resp.content.strip()
                if not content.startswith(b"<"):
                    continue

                root = ET.fromstring(content)
                # Ošetření XML namespaces (např. {http://www.sitemaps.org/schemas/sitemap/0.9})
                for elem in root.iter():
                    if elem.tag.endswith("loc") and elem.text:
                        loc = elem.text.strip()
                        # Pokud odkazuje na pod-sitemapu (sitemap index)
                        if loc.endswith(".xml") and loc != sitemap_url:
                            # Můžeme rekurzivně stáhnout nebo přidat
                            pass
                        norm = self.normalize_url(loc)
                        if norm and self.is_valid_url(norm):
                            found_urls.add(norm)

                if found_urls:
                    logger.info(f"Ze sitemap '{sitemap_url}' bylo získáno {len(found_urls)} URL.")
                    break
            except Exception as e:
                logger.debug(f"Chyba při čtení sitemap {sitemap_url}: {e}")

        return list(found_urls)

    def clean_html_content(self, html: str) -> tuple[str, str]:
        """
        Očistí HTML stránky od navigačních prvků, záhlaví, zápatí, stylů a skriptů.
        Vrací (titulek, čistý text).
        """
        soup = BeautifulSoup(html, "html.parser")

        # Získání titulku stránky
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
            # Oříznutí standardního konce " – Pionýr"
            title = re.sub(r"\s*[–\-|]\s*Pionýr.*$", "", title, flags=re.IGNORECASE).strip()

        # Odstranění nežádoucích tagů
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
            tag.decompose()

        # Odstranění běžných tříd a ID pro navigaci, záhlaví, zápatí a bannery na pionyr.cz
        unwanted_selectors = [
            ".header", "#header", ".hdrnavigace", ".head",
            ".footer", "#footer", ".paticka",
            ".menu", ".menumain", ".menutabletwrp", ".sub-menu",
            ".navigacewrp", ".navigace", ".navigacelinky",
            ".cookie-banner", ".banner", ".sdileni", ".social",
            ".searchform", ".srchtextwrp"
        ]
        for sel in unwanted_selectors:
            for match in soup.select(sel):
                match.decompose()

        # Hledání hlavní obsahové části
        main_content = (
            soup.find("article")
            or soup.find(class_=re.compile(r"content|mainarticle|post-entry|entry-content", re.I))
            or soup.find(id=re.compile(r"content|main", re.I))
            or soup.find("main")
            or soup.body
        )

        if not main_content:
            return title, ""

        # Extrakce textu z odstavců a nadpisů pro zachování kontextu
        text_blocks: List[str] = []
        for element in main_content.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
            t = element.get_text(" ", strip=True)
            # Ignorovat příliš krátké texty (např. copyright, jedno slovo)
            if len(t) > 20:
                text_blocks.append(t)

        cleaned_text = "\n\n".join(text_blocks)
        # Nahrazení vícenásobných bílých znaků
        cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

        return title, cleaned_text

    def extract_links(self, html: str, current_url: str) -> List[str]:
        """
        Vyhledá a normalizuje všechny vnitřní odkazy na stránce.
        """
        soup = BeautifulSoup(html, "html.parser")
        links: List[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            norm = self.normalize_url(href, current_url)
            if norm and self.is_valid_url(norm) and norm not in self.visited_urls:
                links.append(norm)

        return links

    def crawl(self, max_pages: int = 15) -> List[Dict[str, str]]:
        """
        Spustí crawling až do nastaveného počtu stránek (max_pages).
        Kombinuje URL ze sitemap s aktivním procházením dalších odkazů (spider/BFS).
        """
        if requests is None or BeautifulSoup is None:
            raise RuntimeError(
                "Knihovny 'requests' a 'beautifulsoup4' nejsou nainstalovány. "
                "Spusťte: pip install requests beautifulsoup4"
            )

        logger.info(f"Zahajuji crawling webu pionyr.cz (limit: {max_pages} stránek)...")

        # 1. Počáteční fronta URL: sitemap + seed URLs
        queue: List[str] = []
        sitemap_urls = self.fetch_sitemap_urls()

        # Přidáme prioritní SEED URLs (aby obsahovaly hlavní sekce a ideály Pionýra)
        for seed in self.SEED_URLS:
            norm = self.normalize_url(seed)
            if norm and norm not in queue:
                queue.append(norm)

        # Přidáme URLs ze sitemap
        for s_url in sitemap_urls:
            if s_url not in queue:
                queue.append(s_url)

        results: List[Dict[str, str]] = []

        while queue and len(results) < max_pages:
            current_url = queue.pop(0)

            if current_url in self.visited_urls:
                continue

            self.visited_urls.add(current_url)

            try:
                logger.info(f"[{len(results)+1}/{max_pages}] Stahuji: {current_url}")
                resp = requests.get(
                    current_url,
                    headers=self.headers,
                    timeout=self.request_timeout,
                    allow_redirects=True
                )

                if resp.status_code != 200:
                    logger.warning(f"Chyba HTTP {resp.status_code} u {current_url}")
                    continue

                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    continue

                html = resp.text
                title, clean_text = self.clean_html_content(html)

                # Zkontrolujeme, zda stránka obsahuje dostatečný text
                if len(clean_text) >= 150:
                    results.append({
                        "url": current_url,
                        "title": title or "Pionýr",
                        "text": clean_text
                    })
                    logger.info(f"✓ Úspěšně zpracováno: '{title}' ({len(clean_text)} znaků)")

                # Extrakce nových zanořených odkazů pro pavouka
                if len(results) < max_pages:
                    discovered_links = self.extract_links(html, current_url)
                    for link in discovered_links:
                        if link not in self.visited_urls and link not in queue:
                            queue.append(link)

            except requests.RequestException as e:
                logger.warning(f"Chyba spojení u {current_url}: {e}")
            except Exception as e:
                logger.error(f"Neočekávaná chyba při zpracování {current_url}: {e}")

        logger.info(f"Crawling dokončen. Získáno celkem {len(results)} stránek.")
        return results


def crawl_pionyr(max_pages: int = 15, output_file: str | None = None) -> List[Dict[str, str]]:
    """
    Hlavní vstupní funkce pro spuštění crawleru.
    Volitelně uloží výsledek do zadaného souboru JSON.
    """
    crawler = PionyrCrawler()
    pages = crawler.crawl(max_pages=max_pages)

    if output_file:
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(pages, f, ensure_ascii=False, indent=2)
            logger.info(f"Uloženo do souboru: {output_file}")
        except IOError as e:
            logger.error(f"Nelze zapsat do souboru {output_file}: {e}")

    return pages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawler pro web pionyr.cz")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximální počet stažených stránek")
    parser.add_argument("--output", type=str, default="pionyr_obsah.json", help="Výstupní JSON soubor")
    args = parser.parse_args()

    pages_result = crawl_pionyr(max_pages=args.max_pages, output_file=args.output)
    print(f"Hotovo! Staženo {len(pages_result)} stránek do {args.output}")
