"""
generator.py - Pokročilý generátor křížovek s vysokou hustotou křížení a podporou tajenky

Tento modul načítá slovní zásobu z pionyr_otazky.json a využívá dynamický vyhledávací
algoritmus (greedy search s vícenásobným křížením a minimalizací bounding boxu),
který aktivně vyhledává pozice s 2 i více kříženími najednou.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from utils import normalize_answer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CrosswordGenerator")


@dataclass
class PlacedWord:
    """Reprezentace jednoho umístěného slova v mřížce."""
    word: str
    clue: str
    x: int
    y: int
    direction: str  # "across" (vodorovně) nebo "down" (svisle)
    number: int = 0


@dataclass
class SecretCell:
    """Políčko tvořící součást tajenky."""
    x: int
    y: int
    char: str
    order_index: int  # 1-indexed pořadí v tajence


@dataclass
class CrosswordPuzzle:
    """Kompletní reprezentace vygenerované křížovky."""
    width: int
    height: int
    grid: List[List[str]]  # Znak nebo prázdný řetězec ""
    cell_numbers: List[List[int]]  # Číslo buňky (1..) nebo 0
    words: List[PlacedWord]
    across_clues: List[PlacedWord]
    down_clues: List[PlacedWord]
    secret_word: Optional[str] = None
    secret_cells: List[SecretCell] = field(default_factory=list)

    @property
    def total_intersections(self) -> int:
        """Spočítá celkový počet křížení mezi slovy."""
        across_cells = set()
        for w in self.across_clues:
            for i in range(len(w.word)):
                across_cells.add((w.x + i, w.y))

        intersections = 0
        for w in self.down_clues:
            for i in range(len(w.word)):
                if (w.x, w.y + i) in across_cells:
                    intersections += 1
        return intersections

    @property
    def density_ratio(self) -> float:
        """Poměr křížení na jedno slovo (čím vyšší, tím propojenější křížovka)."""
        if not self.words:
            return 0.0
        return self.total_intersections / len(self.words)

    def to_dict(self) -> Dict:
        """Převede objekt křížovky do serializovatelného slovníku."""
        return {
            "width": self.width,
            "height": self.height,
            "grid": self.grid,
            "cell_numbers": self.cell_numbers,
            "words": [asdict(w) for w in self.words],
            "across_clues": [asdict(w) for w in self.across_clues],
            "down_clues": [asdict(w) for w in self.down_clues],
            "secret_word": self.secret_word,
            "secret_cells": [asdict(sc) for sc in self.secret_cells],
            "total_intersections": self.total_intersections,
            "density_ratio": round(self.density_ratio, 2)
        }


class CrosswordBuilder:
    """
    Stavový builder mřížky.
    Udržuje mapu buněk, seznam umístěných slov a aktuální bounding box.
    """

    def __init__(self):
        self.grid_map: Dict[Tuple[int, int], str] = {}
        self.placed_words: List[PlacedWord] = []
        self.used_words_set: Set[str] = set()

    def get_bounding_box(self) -> Tuple[int, int, int, int]:
        """Vrací (min_x, max_x, min_y, max_y)."""
        if not self.grid_map:
            return (0, 0, 0, 0)
        xs = [x for x, y in self.grid_map.keys()]
        ys = [y for x, y in self.grid_map.keys()]
        return (min(xs), max(xs), min(ys), max(ys))

    def can_place_word(self, word: str, start_x: int, start_y: int, direction: str) -> Tuple[bool, int]:
        """
        Ověří platnost umístění slova podle přísných pravidel křížovky.
        Vrací (is_valid, počet_křížení).
        """
        word_len = len(word)
        dx, dy = (1, 0) if direction == "across" else (0, 1)
        perp_dx, perp_dy = (0, 1) if direction == "across" else (1, 0)

        # 1. Buňka před začátkem slova musí být volná
        before_cell = (start_x - dx, start_y - dy)
        if before_cell in self.grid_map:
            return False, 0

        # 2. Buňka za koncem slova musí být volná
        after_cell = (start_x + dx * word_len, start_y + dy * word_len)
        if after_cell in self.grid_map:
            return False, 0

        intersections = 0

        for i, char in enumerate(word):
            cur_x = start_x + dx * i
            cur_y = start_y + dy * i
            cur_pos = (cur_x, cur_y)

            if cur_pos in self.grid_map:
                # Na průsečíku se písmeno musí shodovat
                if self.grid_map[cur_pos] != char:
                    return False, 0
                intersections += 1
            else:
                # Volné políčko: nesmí mít sousedy po stranách kolmo ke směru slova,
                # aby se slova nedotýkala boky a nevznikaly neplatné shluky
                side1 = (cur_x + perp_dx, cur_y + perp_dy)
                side2 = (cur_x - perp_dx, cur_y - perp_dy)
                if side1 in self.grid_map or side2 in self.grid_map:
                    return False, 0

        # První slovo nepotřebuje křížení; další slova musí mít alespoň 1 průnik
        if self.placed_words and intersections == 0:
            return False, 0

        return True, intersections

    def place_word(self, word_item: Dict[str, str], x: int, y: int, direction: str):
        """Umístí slovo do mřížky."""
        word = word_item["answer"]
        clue = word_item["clue"]
        dx, dy = (1, 0) if direction == "across" else (0, 1)

        for i, char in enumerate(word):
            self.grid_map[(x + dx * i, y + dy * i)] = char

        self.placed_words.append(
            PlacedWord(
                word=word,
                clue=clue,
                x=x,
                y=y,
                direction=direction
            )
        )
        self.used_words_set.add(word)

    def find_all_placements_for_word(
        self,
        word: str
    ) -> List[Tuple[int, int, str, int, int]]:
        """
        Nalezne všechna platná umístění pro dané slovo s existujícími slovy.
        Vrací (start_x, start_y, direction, intersections, new_area_expansion).
        """
        placements: List[Tuple[int, int, str, int, int]] = []
        if not self.placed_words:
            return [(0, 0, "across", 0, 0)]

        min_x, max_x, min_y, max_y = self.get_bounding_box()
        cur_area = (max_x - min_x + 1) * (max_y - min_y + 1)

        # Hledáme křížení s již položenými slovy
        for existing in self.placed_words:
            opp_direction = "down" if existing.direction == "across" else "across"
            dx_opp, dy_opp = (0, 1) if opp_direction == "down" else (1, 0)

            for i, char_ex in enumerate(existing.word):
                ex_x = existing.x + (i if existing.direction == "across" else 0)
                ex_y = existing.y + (0 if existing.direction == "across" else i)

                for j, char_new in enumerate(word):
                    if char_ex == char_new:
                        start_x = ex_x - dx_opp * j
                        start_y = ex_y - dy_opp * j

                        can_place, intersections = self.can_place_word(word, start_x, start_y, opp_direction)
                        if can_place:
                            # Vypočítáme nárůst plochy mřížky
                            end_x = start_x + (len(word) - 1 if opp_direction == "across" else 0)
                            end_y = start_y + (0 if opp_direction == "across" else len(word) - 1)

                            new_min_x = min(min_x, start_x, end_x)
                            new_max_x = max(max_x, start_x, end_x)
                            new_min_y = min(min_y, start_y, end_y)
                            new_max_y = max(max_y, start_y, end_y)

                            new_area = (new_max_x - new_min_x + 1) * (new_max_y - new_min_y + 1)
                            area_expansion = new_area - cur_area

                            placements.append((start_x, start_y, opp_direction, intersections, area_expansion))

        return placements


class CrosswordGenerator:
    """
    Pokročilý optimalizovaný generátor křížovek.
    Využívá dynamické hledání z celého slovníku pro dosažení maximální hustoty křížení.
    """

    def __init__(self, vocabulary_path: str = "pionyr_otazky.json"):
        self.vocabulary_path = vocabulary_path
        self.vocabulary: List[Dict[str, str]] = []
        self.load_vocabulary()

    def load_vocabulary(self):
        """Načte a zvaliduje slovní zásobu z JSON souboru."""
        p = Path(self.vocabulary_path)
        if not p.exists():
            logger.warning(f"Slovník '{self.vocabulary_path}' neexistuje.")
            self.vocabulary = []
            return

        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_items = data if isinstance(data, list) else data.get("items", [])
        valid_items: List[Dict[str, str]] = []
        seen = set()

        for it in raw_items:
            ans = normalize_answer(it.get("answer", ""))
            clue = it.get("clue", "").strip()
            if ans and clue and ans not in seen:
                seen.add(ans)
                valid_items.append({"answer": ans, "clue": clue})

        self.vocabulary = valid_items
        logger.info(f"Načteno {len(self.vocabulary)} validních slov ze slovníku.")

    def _attempt_build_dense(
        self,
        target_word_count: int,
        secret_word: Optional[str] = None,
        randomness: float = 0.2
    ) -> CrosswordBuilder:
        """
        Jeden optimalizační cyklus: dynamicky vybírá slova z celého slovníku
        tak, aby se maximalizoval počet křížení a minimalizoval rozměr mřížky.
        """
        builder = CrosswordBuilder()
        available_vocab = list(self.vocabulary)
        random.shuffle(available_vocab)

        norm_secret = normalize_answer(secret_word) if secret_word else None

        # 1. Výběr prvního slova
        # Pokud máme tajenku, preferujeme delší slovo obsahující písmeno tajenky
        first_candidates = []
        if norm_secret:
            for item in available_vocab:
                if any(c in item["answer"] for c in norm_secret):
                    first_candidates.append(item)

        if not first_candidates:
            first_candidates = [it for it in available_vocab if len(it["answer"]) >= 6]
        if not first_candidates:
            first_candidates = available_vocab

        first_word_item = random.choice(first_candidates[:min(8, len(first_candidates))])
        builder.place_word(first_word_item, 0, 0, "across")

        # 2. Dynamické rozšiřování mřížky:
        # V každém kroku projdeme všechna dostupná slova a vybereme tah s nejlepším skóre
        while len(builder.placed_words) < target_word_count:
            candidate_moves = []

            for item in available_vocab:
                ans = item["answer"]
                if ans in builder.used_words_set:
                    continue

                placements = builder.find_all_placements_for_word(ans)
                for start_x, start_y, direction, intersections, expansion in placements:
                    # Skórovací funkce:
                    # + 35 bodů za každé křížení
                    # + 40 bonus za 2 a více křížení najednou (multi-intersection!)
                    # - 0.8 bodu za každé zvětšení plochy mřížky (udrží mřížku hustou)
                    # + bonus pokud slovo obsahuje chybějící písmeno tajenky
                    score = (intersections * 35.0) - (expansion * 0.8)

                    if intersections >= 2:
                        score += 50.0  # Obrovský bonus za vícenásobné křížení!

                    if norm_secret:
                        # Bonus za písmena tajenky
                        placed_secret_chars = {
                            builder.grid_map[pos] for pos in builder.grid_map
                            if builder.grid_map[pos] in norm_secret
                        }
                        missing_chars = set(norm_secret) - placed_secret_chars
                        if any(c in ans for c in missing_chars):
                            score += 25.0

                    # Mírná náhoda pro pestrost výběru a zapojení všech slov
                    score += random.uniform(-5.0 * randomness, 5.0 * randomness)

                    candidate_moves.append((score, item, start_x, start_y, direction))

            if not candidate_moves:
                # Žádné další slovo nelze skřížit
                break

            # Seřadíme tahy podle skóre
            candidate_moves.sort(key=lambda m: m[0], reverse=True)

            # Vybereme jeden z top tahů (náhoda mezi top 3)
            top_moves = candidate_moves[:min(3, len(candidate_moves))]
            chosen_score, chosen_item, chosen_x, chosen_y, chosen_dir = random.choice(top_moves)
            builder.place_word(chosen_item, chosen_x, chosen_y, chosen_dir)

        return builder

    def _find_secret_cells(
        self,
        grid: List[List[str]],
        words: List[PlacedWord],
        secret_word: str
    ) -> List[SecretCell]:
        """
        Vyhledá v mřížce vhodné buňky pro sestavení tajenky.
        Každé písmeno tajenky se vybere z jiného slova a v odpovídajícím pořadí.
        """
        norm_secret = normalize_answer(secret_word) or secret_word.upper()
        secret_cells: List[SecretCell] = []
        used_cells: Set[Tuple[int, int]] = set()

        for idx, char in enumerate(norm_secret, start=1):
            candidates = []
            for y in range(len(grid)):
                for x in range(len(grid[0])):
                    if grid[y][x] == char and (x, y) not in used_cells:
                        candidates.append((x, y))

            if candidates:
                chosen_x, chosen_y = random.choice(candidates)
                used_cells.add((chosen_x, chosen_y))
                secret_cells.append(SecretCell(x=chosen_x, y=chosen_y, char=char, order_index=idx))
            else:
                return []

        return secret_cells

    def generate(
        self,
        word_count: int = 12,
        secret_word: Optional[str] = None,
        max_attempts: int = 50
    ) -> Optional[CrosswordPuzzle]:
        """
        Vygeneruje novou vysoce propojenou křížovku.
        Provádí více pokusů (Monte Carlo restarts) a vybere mřížku s nejvyšší
        hustotou křížení (intersections / words) a nejkompaktnějším rozměrem.
        """
        if len(self.vocabulary) < 5:
            logger.error("Ve slovníku je příliš málo slov pro generování křížovky.")
            return None

        target_count = max(8, min(word_count, len(self.vocabulary)))

        best_builder: Optional[CrosswordBuilder] = None
        best_quality_score = -999999.0
        best_density = 0.0

        for attempt in range(max_attempts):
            builder = self._attempt_build_dense(
                target_word_count=target_count,
                secret_word=secret_word,
                randomness=1.0 if attempt > 0 else 0.0
            )

            placed_count = len(builder.placed_words)
            if placed_count < 6:
                continue

            # Spočítáme počet křížení
            intersections_count = 0
            across_positions = set()
            for w in builder.placed_words:
                if w.direction == "across":
                    for i in range(len(w.word)):
                        across_positions.add((w.x + i, w.y))

            for w in builder.placed_words:
                if w.direction == "down":
                    for i in range(len(w.word)):
                        if (w.x, w.y + i) in across_positions:
                            intersections_count += 1

            min_x, max_x, min_y, max_y = builder.get_bounding_box()
            area = (max_x - min_x + 1) * (max_y - min_y + 1)
            density = intersections_count / max(1, placed_count)

            # Celkové skóre kvality:
            # - výrazná váha pro počet křížení (více křížení = mnohem lepší!)
            # - penalizace za zbytečně rozsáhlou prázdnou mřížku
            # - bonus za splnění cílového počtu slov
            quality_score = (intersections_count * 25.0) + (placed_count * 20.0) - (area * 0.35)

            if quality_score > best_quality_score and placed_count >= min(8, target_count - 2):
                best_quality_score = quality_score
                best_builder = builder
                best_density = density

        if not best_builder or len(best_builder.placed_words) < 4:
            logger.error("Nepodařilo se vygenerovat křížovku.")
            return None

        # -------------------------------------------------------------------
        # Bounding Box normalizace
        # -------------------------------------------------------------------
        all_cells = list(best_builder.grid_map.keys())
        min_x = min(x for x, y in all_cells)
        max_x = max(x for x, y in all_cells)
        min_y = min(y for x, y in all_cells)
        max_y = max(y for x, y in all_cells)

        width = max_x - min_x + 1
        height = max_y - min_y + 1

        grid: List[List[str]] = [["" for _ in range(width)] for _ in range(height)]
        for (gx, gy), ch in best_builder.grid_map.items():
            grid[gy - min_y][gx - min_x] = ch

        shifted_words: List[PlacedWord] = []
        for w in best_builder.placed_words:
            shifted_words.append(
                PlacedWord(
                    word=w.word,
                    clue=w.clue,
                    x=w.x - min_x,
                    y=w.y - min_y,
                    direction=w.direction
                )
            )

        # -------------------------------------------------------------------
        # Číslování otázek (shora dolů, zleva doprava)
        # -------------------------------------------------------------------
        cell_numbers: List[List[int]] = [[0 for _ in range(width)] for _ in range(height)]
        current_number = 1

        across_map: Dict[Tuple[int, int], PlacedWord] = {
            (w.x, w.y): w for w in shifted_words if w.direction == "across"
        }
        down_map: Dict[Tuple[int, int], PlacedWord] = {
            (w.x, w.y): w for w in shifted_words if w.direction == "down"
        }

        across_clues: List[PlacedWord] = []
        down_clues: List[PlacedWord] = []

        for y in range(height):
            for x in range(width):
                has_across = (x, y) in across_map
                has_down = (x, y) in down_map

                if has_across or has_down:
                    cell_numbers[y][x] = current_number

                    if has_across:
                        w = across_map[(x, y)]
                        w.number = current_number
                        across_clues.append(w)

                    if has_down:
                        w = down_map[(x, y)]
                        w.number = current_number
                        down_clues.append(w)

                    current_number += 1

        # -------------------------------------------------------------------
        # Tajenka
        # -------------------------------------------------------------------
        secret_cells: List[SecretCell] = []
        if secret_word:
            secret_cells = self._find_secret_cells(grid, shifted_words, secret_word)

        puzzle = CrosswordPuzzle(
            width=width,
            height=height,
            grid=grid,
            cell_numbers=cell_numbers,
            words=shifted_words,
            across_clues=across_clues,
            down_clues=down_clues,
            secret_word=secret_word if secret_cells else None,
            secret_cells=secret_cells
        )

        logger.info(
            f"Hustá křížovka vygenerována: {width}x{height}, "
            f"slov: {len(shifted_words)}, křížení: {puzzle.total_intersections} "
            f"(hustota: {puzzle.density_ratio:.2f} křížení/slovo)."
        )
        return puzzle


def generate_crossword(
    word_count: int = 12,
    secret_word: Optional[str] = None,
    vocabulary_path: str = "pionyr_otazky.json"
) -> Optional[CrosswordPuzzle]:
    """Pomocná funkce pro vygenerování křížovky."""
    gen = CrosswordGenerator(vocabulary_path=vocabulary_path)
    return gen.generate(word_count=word_count, secret_word=secret_word)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hustý generátor pionýrské křížovky")
    parser.add_argument("--words", type=int, default=12, help="Počet slov")
    parser.add_argument("--secret", type=str, default="PIONYR", help="Tajenka")
    parser.add_argument("--vocab", type=str, default="pionyr_otazky.json", help="Cesta ke slovníku")
    args = parser.parse_args()

    result = generate_crossword(word_count=args.words, secret_word=args.secret, vocabulary_path=args.vocab)
    if result:
        print(f"\n--- VYGENEROVANÁ KŘÍŽOVKA ({result.width}x{result.height}) ---")
        print(f"Celkem slov: {len(result.words)} | Celkem křížení: {result.total_intersections} | Hustota: {result.density_ratio:.2f}")
        for row in result.grid:
            print(" ".join(c if c else "·" for c in row))

        print("\nVODOROVNĚ:")
        for w in result.across_clues:
            print(f"  {w.number}. {w.clue} ({len(w.word)}) [{w.word}]")

        print("\nSVISLE:")
        for w in result.down_clues:
            print(f"  {w.number}. {w.clue} ({len(w.word)}) [{w.word}]")

        if result.secret_cells:
            print(f"\nTAJENKA: {result.secret_word}")
            for sc in result.secret_cells:
                print(f"  {sc.order_index}. písmeno '{sc.char}' na [{sc.x}, {sc.y}]")
    else:
        print("Křížovku se nepodařilo vygenerovat.")
