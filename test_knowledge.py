import json
import tempfile
import unittest
from pathlib import Path

from knowledge import KnowledgeBase, normalize, tokens
from bot import telegram_plain_text


class KnowledgeTests(unittest.TestCase):
    def test_telegram_markdown_cleanup(self):
        source = """### Заголовок

**Главная мысль**

---

- Первый пункт
> Цитата

| Принцип | Обоснование |
|---|---|
| Системность | Все взаимосвязано |
"""
        self.assertEqual(
            telegram_plain_text(source),
            "Заголовок\n\nГлавная мысль\n\n• Первый пункт\nЦитата\n\n"
            "Принцип — Обоснование\nСистемность — Все взаимосвязано",
        )

    def test_russian_normalization(self):
        self.assertEqual(normalize("проектирования"), normalize("проектирование"))
        self.assertIn(normalize("изменения"), tokens("Проектирование социальных изменений"))

    def test_search_and_context(self):
        items = [
            {"source": "A", "page": 1, "text": "Диагностика и проектирование социальных изменений"},
            {"source": "B", "page": 2, "text": "История городского транспорта"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunks.json"
            path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
            kb = KnowledgeBase(path)
            hits = kb.search("Как проектировать социальные изменения?", 1)
            self.assertEqual((hits[0].source, hits[0].page), ("A", 1))
            self.assertIn("[Источник: A, стр. 1]", kb.format_context(hits, 1000))


if __name__ == "__main__":
    unittest.main()
