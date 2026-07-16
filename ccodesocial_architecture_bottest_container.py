import json, os
from pathlib import Path
from knowledge import KnowledgeBase
import httpx, asyncio

SYSTEM_PROMPT = """Ты — аналитик и практик социальной архитектуры. Отвечай по-русски и мысли в рамках приложенных источников.

Рабочая рамка:
- социальная архитектура — целенаправленное, научно обоснованное проектирование и организация общественно значимых изменений ради развития социальных систем и повышения качества жизни;
- не манипулируй людьми: вовлекай их как субъектов, учитывай ценности, интересы, достоинство, обратную связь и локальный контекст;
- рассуждай системно: диагностика -> образ желаемого будущего и измеримая цель -> стейкхолдеры и ресурсы -> гипотеза изменений -> пилот -> оценка -> корректировка -> масштабирование/институционализация;
- различай факт из источника, вывод и практическую рекомендацию;
- не приписывай источникам того, чего нет в предоставленных выдержках. Если данных недостаточно, прямо скажи об этом;
- делай ответ прикладным: показывай акторов, риски, метрики, обратные связи и возможные побочные эффекты;
- ссылайся внутри ответа в формате [Источник, стр. N].

Не раскрывай скрытые рассуждения. Давай краткое обоснование, вывод и, когда уместно, план действий."""

ROOT = Path('/app')
KB = KnowledgeBase(ROOT / 'data' / 'chunks.json')

async def ask(question: str, context_text: str):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({
        "role": "user",
        "content": f"ВЫДЕРЖКИ ИЗ ИСТОЧНИКОВ:\n{context_text}\n\nВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{question}",
    })
    payload = {
        "model": 'qwen/qwen3-vl-8b',
        "messages": messages,
        "temperature": 0.35,
        "top_p": 0.9,
        "max_tokens": 1400,
        "stream": False,
    }
    headers = {"Authorization": "Bearer lm-studio"}
    url = 'http://host.docker.internal:1234/v1/chat/completions'
    async with httpx.AsyncClient(timeout=180) as client:
        response = await client.post(url, json=payload, headers=headers)
        print('Status:', response.status_code)
        print('Body:', response.text[:2000])

async def main():
    question = 'Что такое социальная архитектура?'
    relevant_hits = KB.search(question, 7)
    hits = KB.foundational()
    seen = {(hit.source, hit.page, hit.text) for hit in hits}
    hits.extend(hit for hit in relevant_hits if (hit.source, hit.page, hit.text) not in seen)
    context_text = KB.format_context(hits, 18000)
    print('Hits:', len(hits), 'Context chars:', len(context_text))
    await ask(question, context_text)

asyncio.run(main())
