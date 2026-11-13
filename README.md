# Pionýr CrissGen — Generátor křížovek pro spolek Pionýr

Modulární aplikace v jazyce Python pro automatizovaný sběr textového obsahu z webu organizace Pionýr ([pionyr.cz](https://pionyr.cz)), extrakci křížovkových hesel a nápověd pomocí modelu Google Gemini se strukturovaným výstupem, výpočet ortogonální křížovkové mřížky s tajenkou a export do tiskového PDF či samostatného HTML archu formátu A4.

---

## Přehled vlastností

- **Vlastní křížovkový algoritmus s maximalizací průniků:** Generátor staví mřížku metodou vícenásobného hladového vyhledávání s váženou pokutou za rozměr opísaného obdélníku (bounding box) a bonusem za vícenásobná kolmá křížení. Striktně vynucuje pravidla křížovkové sousednosti (zákaz nechtěných bočních dotyků a navazujících slov bez mezery).
- **Podpora tajenky:** Automaticky vyhledává a zvýrazňuje políčka pro zadané cílové slovo (např. `PIONYR`, `TABOR`, `PRIRODA`) a generuje samostatný číslovaný řádek tajenky pod mřížkou.
- **Předpřipravený slovníkový korpus:** Součástí repozitáře je databáze `pionyr_otazky.json` obsahující přes 250 ověřených křížovkových pojmů a otázek z historie, ideálů, symboliky a činnosti Pionýra. Aplikace proto generuje křížovky okamžitě i bez připojeného API klíče.
- **Automatická extrakce a rozšiřování slovníku:** Webový crawler prochází `sitemap.xml` a podstránky `pionyr.cz` (nebo konkrétní zadanou URL adresu), čistí HTML přes BeautifulSoup a pomocí SDK `google-genai` a schématu Pydantic extrahuje nová jednoslovná hesla bez diakritiky.
- **Redakční webové rozhraní i příkazová řádka:** Interaktivní rozhraní postavené nad knihovnou Streamlit v typografickém stylu tištěné publikace, doplněné o plnohodnotné CLI rozhraní pro dávkové generování a skriptování.
- **Tiskové výstupy A4:** Vektorový export do PDF (ReportLab) a samostatný tiskový HTML dokument s pravidly `@page { size: A4 portrait; }` připravený pro přímý tisk v prohlížeči (`Cmd+P` / `Ctrl+P`).

---

## Architektura projektu

Projekt je rozdělen do samostatných modulů s jasně vymezenou odpovědností:

| Soubor | Popis modulu |
| :--- | :--- |
| `app.py` | Webové rozhraní ve Streamlitu. Zajišťuje konfiguraci parametrů mřížky, živý náhled luštitelského i kontrolního archu, správu slovníku a stahování tiskových souborů PDF/HTML. |
| `generator.py` | Výpočetní jádro křížovky (`CrosswordGenerator`, `CrosswordBuilder`). Načítá slovník, hledá optimální rozložení slov v 2D mřížce, ořezává souřadnice, čísluje počáteční buňky a mapuje políčka tajenky. |
| `pdf_exporter.py` | Tiskový exportér. Vykresluje vektorové PDF na formát A4 pomocí knihovny ReportLab (včetně podpory českých TTF písem) a sestavuje samostatné tiskové HTML. |
| `crawler.py` | Webový crawler (`PionyrCrawler`). Čte `sitemap.xml` na doméně `pionyr.cz`, filtruje binární soubory a administrativní cesty a extrahuje čistý text článků. |
| `extractor.py` | Klient pro Google Gemini API (`GeminiExtractor`). Pomocí knihovny Pydantic vynucuje JSON schéma odpovědi (3–12 znaků, velká písmena, bez diakritiky), provádí deduplikaci a ukládá data do `pionyr_otazky.json`. |
| `utils.py` | Bezzávislostní pomocné funkce pro dekompozici znaků (`unicodedata.normalize('NFKD')`), odstranění diakritiky, validaci odpovědí a úpravu interpunkce v nápovědách. |
| `main.py` | Jednotný vstupní bod pro příkazovou řádku (spuštění UI, terminálové generování mřížky, export do PDF/HTML a spouštění crawleru). |
| `pionyr_otazky.json` | JSON databáze křížovkových otázek a normalizovaných odpovědí. |
| `pionyrska_krizovka.pdf` | Ukázkový výstup vygenerovaného křížovkového archu ve formátu PDF. |
| `test_app.py` | Sada jednotkových testů (`unittest`) ověřující normalizaci textu, filtry crawleru, neporušenost křížení v mřížce a export do PDF/HTML. |

---

## Požadavky a instalace

### Systémové předpoklady
- Python `3.9` nebo novější
- Připojení k internetu (pouze při stahování nových článků z `pionyr.cz` a volání Gemini API; samotné generování křížovek z lokálního slovníku funguje plně offline)

### Postup instalace

```bash
# 1. Naklonování repozitáře
git clone https://github.com/nedo44/CrissGen.git
cd CrissGen

# 2. Vytvoření a aktivace virtuálního prostředí
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# 3. Instalace závislostí
pip install -r requirements.txt
```

### Konfigurace klíče Gemini API (volitelné)

Klíč Gemini API je vyžadován pouze tehdy, pokud chcete stahovat nové články z webu a rozšiřovat slovník `pionyr_otazky.json` o nová hesla.

1. Vytvořte si API klíč v [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Zkopírujte šablonu `.env.example` do souboru `.env`:
   ```bash
   cp .env.example .env
   ```
3. Do souboru `.env` vložte svůj klíč:
   ```env
   GEMINI_API_KEY=vas_api_klic
   ```
Klíč lze zadat také přímo v bočním panelu webového rozhraní nebo předat parametrem `--api-key` v příkazové řádce.

---

## Spuštění a ovládání

### 1. Webové rozhraní (Streamlit)

Spusťte interaktivní aplikaci příkazem:

```bash
streamlit run app.py
```

nebo přes hlavní skript:

```bash
python main.py --ui
```

Rozhraní bude dostupné v prohlížeči na adrese `http://localhost:8501`.

Hlavní možnosti webového rozhraní:
- **Sestavení mřížky:** Volba cílového počtu slov (8–18) a volitelného slova tajenky (např. `PIONYR`, `TABOR`, `PRIRODA`, `ODDIL`).
- **Kontrola řešení:** Přepínání mezi čistým luštitelským archem a kontrolním archem s vyplněnými písmeny v mřížce, v tajence i u jednotlivých nápověd.
- **Tiskový export:** Okamžité stažení PDF k luštění, PDF s řešením nebo samostatného HTML archu formátu A4.
- **Rozšíření slovníku z URL nebo celého webu:** Zadání konkrétní adresy z `pionyr.cz` nebo spuštění dávkového průchodu webu s automatickou extrakcí a deduplikací nových pojmů.

### 2. Příkazová řádka (CLI)

Všechny funkce generátoru i extraktoru lze volat přímo z terminálu:

```bash
# Vygenerování křížovky s tajenkou přímo do terminálu
python main.py --words 12 --secret PIONYR

# Export čisté křížovky k luštění do PDF
python main.py --words 12 --secret TABOR --pdf krizovka.pdf

# Export křížovky včetně vyplněného řešení do PDF
python main.py --words 12 --secret TABOR --pdf krizovka_reseni.pdf --solution

# Export do samostatného tiskového HTML souboru (formát A4)
python main.py --words 10 --secret PRIRODA --html krizovka.html

# Extrakce nových křížovkových pojmů z konkrétní stránky na pionyr.cz
python main.py --url https://pionyr.cz/o-pionyru/historie/

# Spuštění crawleru (např. 10 stránek) a rozšíření slovníku přes Gemini API
python main.py --crawl --pages 10
```

---

## Technické řešení a algoritmus

### Normalizace českých pojmů
Všechna hesla procházejí v modulu `utils.py` dekompozicí `unicodedata.normalize('NFKD', text)` a filtrací kombinujících diakritických značek (`unicodedata.combining`). Slova jsou převedena na velká písmena `A–Z` bez mezer a interpunkce a validována na délku `3` až `12` znaků (např. `Přátelství` -> `PRATELSTVI`).

### Sestavování křížovkové mřížky
Algoritmus v `generator.py` pracuje ve třech krocích:
1. **Výběr kandidátů:** Ze slovníku vybere podmnožinu slov se zastoupením všech znaků požadované tajenky a doplní ji slovy s vysokou frekvencí samohlásek a běžných souhlásek.
2. **Hladové prohledávání s vícenásobnými restarty:** Ve výchozím nastavení provede desítky nezávislých pokusů o sestavení mřížky. V každém kroku hodnotí všechny přípustné pozice nového slova podle účelové funkce:
   - vysoký kladný zisk za každé kolmé protnutí s již umístěnými slovy (zejména za prodchnutí dvou a více slov současně),
   - penalizace za zvětšení šířky či výšky opísaného obdélníku a za odchylku od čtvercového poměru stran,
   - přísná kontrola kolizí: zakázáno je přímé navazování slov ve stejném směru i souběžný boční dotyk dvou slov bez platného křížení.
3. **Ořez a číslování:** Nejlepší nalezená mřížka je transformována do minimálního souřadnicového rámce `(0..width-1, 0..height-1)` a počáteční políčka slov jsou očíslována v přirozeném pořadí čtení (shora dolů, zleva doprava).

---

## Testování

Sadu jednotkových testů spustíte příkazem:

```bash
python3 -m unittest test_app.py -v
```

Testy ověřují odstranění diakritiky, normalizaci hraničních délek slov, URL filtry crawleru, integritu křížení ve vygenerované mřížce a vygenerování platného PDF i HTML výstupu.
