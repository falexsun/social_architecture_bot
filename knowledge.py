from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

WORD_RE = re.compile(r"[а-яёa-z0-9]{2,}", re.IGNORECASE)
STOP = {
    "это", "как", "что", "для", "при", "или", "его", "она", "они", "мы",
    "вы", "так", "уже", "еще", "быть", "есть", "над", "под", "где", "когда",
    "который", "которая", "которые", "также", "более", "может", "свой", "всех",
    "того", "этой", "этого", "если", "чтобы", "через", "между", "была", "были",
}
RU_SUFFIXES = sorted({
    "иями", "ями", "ами", "его", "ого", "ему", "ому", "ими", "ыми", "ией",
    "ией", "иям", "ием", "иях", "ирование", "ирования", "ировать", "ируется",
    "ировать", "ический", "ическая", "ические", "ического", "енность", "ности",
    "ство", "ства", "ству", "ством", "ствам", "ация", "ации", "аций", "ацию",
    "ение", "ения", "ений", "ению", "ением", "ов", "ев", "ей", "ий", "ый",
    "ой", "ая", "яя", "ое", "ее", "ые", "ие", "ам", "ям", "ах", "ях", "ом",
    "ем", "ую", "юю", "ать", "ять", "ить", "еть", "уть", "ться", "ся", "ть",
    "ы", "и", "а", "я", "у", "ю", "е", "о",
}, key=len, reverse=True)


def normalize(word: str) -> str:
    word = word.lower().replace("ё", "е")
    if re.fullmatch(r"[а-я]+", word):
        for suffix in RU_SUFFIXES:
            if len(word) - len(suffix) >= 4 and word.endswith(suffix):
                return word[:-len(suffix)]
    return word


def tokens(text: str) -> list[str]:
    return [normalize(w) for w in WORD_RE.findall(text) if w.lower().replace("ё", "е") not in STOP]


@dataclass(frozen=True)
class Hit:
    source: str
    page: int
    text: str
    score: float


class KnowledgeBase:
    def __init__(self, path: Path):
        self.items = json.loads(path.read_text(encoding="utf-8"))
        self.docs = [tokens(x["text"]) for x in self.items]
        self.freqs = [Counter(x) for x in self.docs]
        self.avg_len = sum(map(len, self.docs)) / max(1, len(self.docs))
        document_frequency = Counter()
        for doc in self.docs:
            document_frequency.update(set(doc))
        n = len(self.docs)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in document_frequency.items()}

    def search(self, query: str, limit: int = 7) -> list[Hit]:
        query_terms = tokens(query)
        if not query_terms:
            return []
        scored: list[tuple[float, int]] = []
        k1, b = 1.5, 0.72
        for i, (doc, freq) in enumerate(zip(self.docs, self.freqs)):
            score = 0.0
            length_norm = k1 * (1 - b + b * len(doc) / max(1, self.avg_len))
            for term in query_terms:
                tf = freq.get(term, 0)
                if tf:
                    score += self.idf.get(term, 0.0) * tf * (k1 + 1) / (tf + length_norm)
            if score:
                scored.append((score, i))
        scored.sort(reverse=True)
        return [Hit(**self.items[i], score=score) for score, i in scored[:limit]]

    def foundational(self) -> list[Hit]:
        """Core definition and project cycle from the short presentation."""
        wanted_pages = {4, 6}
        return [
            Hit(**item, score=0.0)
            for item in self.items
            if item["source"].startswith("Семёнов") and item["page"] in wanted_pages
        ]

    @staticmethod
    def format_context(hits: list[Hit], max_chars: int) -> str:
        blocks, used = [], 0
        for hit in hits:
            block = f"[Источник: {hit.source}, стр. {hit.page}]\n{hit.text.strip()}"
            if blocks and used + len(block) > max_chars:
                break
            blocks.append(block[:max_chars - used])
            used += len(block)
        return "\n\n---\n\n".join(blocks)
