from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader


def clean(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\xa0", " ")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def windows(text: str, target: int = 2400, overlap: int = 300):
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    current = ""
    for paragraph in paragraphs:
        if current and len(current) + len(paragraph) + 2 > target:
            yield current
            current = current[-overlap:] + "\n\n" + paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        yield current


def extract(pdf: Path, label: str):
    for page_no, page in enumerate(PdfReader(str(pdf)).pages, 1):
        text = clean(page.extract_text() or "")
        for part in windows(text):
            if len(part) >= 80:
                yield {"source": label, "page": page_no, "text": part}


def main():
    parser = argparse.ArgumentParser(description="Создать локальную базу знаний из PDF")
    parser.add_argument("--book", type=Path, required=True)
    parser.add_argument("--slides", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/chunks.json"))
    args = parser.parse_args()
    items = [
        *extract(args.book, "Социальная архитектура: теория и практика социальных изменений"),
        *extract(args.slides, "Семёнов А. Ю. — К определению социальной архитектуры"),
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    print(f"Готово: {len(items)} фрагментов -> {args.output}")


if __name__ == "__main__":
    main()
