import json
import tempfile
import unittest
from pathlib import Path

from knowledge import KnowledgeBase, normalize, tokens
import httpx

from bot import (
    build_messages,
    generation_was_truncated,
    is_case_question,
    is_context_overflow,
    remove_case_meta_sections,
    split_message,
    telegram_plain_text,
)


class KnowledgeTests(unittest.TestCase):
    def test_case_mode_uses_silent_methodology(self):
        question = "Рыбаки оставляют мусор. Реши кейс"
        self.assertTrue(is_case_question(question))
        prompt = build_messages(question, "контекст", [])[-1]["content"]
        self.assertIn("Примени методологию молча", prompt)
        self.assertIn("причинные гипотезы", prompt)

    def test_case_meta_section_is_removed(self):
        response = """Решение:
Установить контейнеры и проверить график вывоза.

• Ключевая идея:
Социальная архитектура — это проектирование будущего вместе с людьми.

• Итог:
Начать с двух береговых участков и измерить массу мусора."""
        self.assertEqual(
            remove_case_meta_sections(response),
            "Решение:\nУстановить контейнеры и проверить график вывоза.\n\n"
            "• Итог:\nНачать с двух береговых участков и измерить массу мусора.",
        )

    def test_standalone_textbook_definition_is_removed_from_case(self):
        response = (
            "Сначала измерить объем мусора на трех участках.\n\n"
            "Социальная архитектура — это проектирование будущего вместе с людьми.\n\n"
            "Пилот провести в течение четырех недель."
        )
        self.assertEqual(
            remove_case_meta_sections(response),
            "Сначала измерить объем мусора на трех участках.\n\n"
            "Пилот провести в течение четырех недель.",
        )

    def test_context_overflow_detection(self):
        request = httpx.Request("POST", "http://localhost/v1/chat/completions")
        overflow = httpx.Response(400, request=request, text="The request exceeds the context window")
        other = httpx.Response(400, request=request, text="Model not found")
        self.assertTrue(is_context_overflow(overflow))
        self.assertFalse(is_context_overflow(other))

    def test_truncation_detection_and_telegram_split(self):
        self.assertTrue(generation_was_truncated("length"))
        self.assertTrue(generation_was_truncated("maxPredictedTokensReached"))
        self.assertFalse(generation_was_truncated("stop"))
        parts = list(split_message("слово " * 1500, limit=4000))
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 4000 for part in parts))

    def test_telegram_markdown_cleanup(self):
        source = """### Заголовок

**Главная мысль** и *важный вывод*.

---

- Первый пункт
> Цитата

| Принцип | Обоснование |
|---|---|
| Системность | Все взаимосвязано |
"""
        self.assertEqual(
            telegram_plain_text(source),
            "Заголовок\n\nГлавная мысль и важный вывод.\n\n• Первый пункт\nЦитата\n\n"
            "Принцип — Обоснование\nСистемность — Все взаимосвязано",
        )

    def test_source_references_are_removed(self):
        source = (
            "Социальная архитектура повышает качество жизни [Источник, стр. 4]. "
            "Изменения проверяют на пилоте [Семёнов А. Ю., стр. 6]. "
            "Затем решение корректируют (стр. 6)."
        )
        result = telegram_plain_text(source)
        self.assertNotIn("Источник", result)
        self.assertNotIn("Семёнов", result)
        self.assertNotIn("стр.", result)
        self.assertEqual(
            result,
            "Социальная архитектура повышает качество жизни. Изменения проверяют на пилоте. "
            "Затем решение корректируют.",
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
