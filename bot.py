from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from knowledge import KnowledgeBase

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.getenv("LM_STUDIO_URL", "http://127.0.0.1:1234/v1").rstrip("/")
MODEL = os.getenv("LM_STUDIO_MODEL", "qwen/qwen3-vl-8b")
API_TOKEN = os.getenv("LM_STUDIO_API_TOKEN", "lm-studio")
TOP_K = int(os.getenv("TOP_K", "7"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "18000"))
MAX_QUESTION_CHARS = int(os.getenv("MAX_QUESTION_CHARS", "4000"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2400"))
MAX_CONTINUATIONS = int(os.getenv("MAX_CONTINUATIONS", "1"))
ALLOWED_USER_IDS = {
    int(value.strip())
    for value in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if value.strip()
}

SYSTEM_PROMPT = """Ты — аналитик и практик социальной архитектуры. Отвечай по-русски и мысли в рамках приложенных источников.

Рабочая рамка:
- социальная архитектура — целенаправленное, научно обоснованное проектирование и организация общественно значимых изменений ради развития социальных систем и повышения качества жизни;
- не манипулируй людьми: вовлекай их как субъектов, учитывай ценности, интересы, достоинство, обратную связь и локальный контекст;
- рассуждай системно: диагностика -> образ желаемого будущего и измеримая цель -> стейкхолдеры и ресурсы -> гипотеза изменений -> пилот -> оценка -> корректировка -> масштабирование/институционализация;
- различай факт из источника, вывод и практическую рекомендацию;
- не приписывай источникам того, чего нет в предоставленных выдержках. Если данных недостаточно, прямо скажи об этом;
- делай ответ прикладным: показывай акторов, риски, метрики, обратные связи и возможные побочные эффекты;
- ссылайся внутри ответа в формате [Источник, стр. N].

Требования к оформлению для Telegram:
- используй только обычный текст без Markdown и HTML;
- не используй символы # и *, Markdown, HTML, обратные кавычки, горизонтальные разделители, таблицы и эмодзи;
- начинай сразу с краткого ответа в 2–3 предложениях;
- для перечислений используй короткие пункты с символом «•» или обычную нумерацию;
- не делай много заголовков; допустимы короткие подписи вида «Практический смысл:»;
- пиши компактно, без повторения одной мысли разными словами;
- старайся уложить полный ответ в 6000 символов и обязательно закончи мысль и вывод.

Не раскрывай скрытые рассуждения. Давай краткое обоснование, вывод и, когда уместно, план действий."""

KB = KnowledgeBase(ROOT / "data" / "chunks.json")


def generation_was_truncated(finish_reason: object) -> bool:
    return str(finish_reason or "").lower() in {
        "length",
        "max_tokens",
        "maxpredictedtokensreached",
    }


def is_allowed(update: Update) -> bool:
    return not ALLOWED_USER_IDS or (
        update.effective_user is not None and update.effective_user.id in ALLOWED_USER_IDS
    )


async def reject_if_forbidden(update: Update) -> bool:
    if is_allowed(update):
        return False
    if update.effective_message:
        await update.effective_message.reply_text("У вас нет доступа к этому боту.")
    return True


async def ask_lm_studio(question: str, context_text: str, history: list[dict]) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history[-6:])
    messages.append({
        "role": "user",
        "content": f"ВЫДЕРЖКИ ИЗ ИСТОЧНИКОВ:\n{context_text}\n\nВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{question}",
    })
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    parts: list[str] = []
    async with httpx.AsyncClient(timeout=180) as client:
        for attempt in range(MAX_CONTINUATIONS + 1):
            payload = {
                "model": MODEL,
                "messages": messages,
                "temperature": 0.35,
                "top_p": 0.9,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "stream": False,
            }
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            content = (choice["message"].get("content") or "").strip()
            if content:
                parts.append(content)

            if not generation_was_truncated(choice.get("finish_reason")):
                break
            if attempt >= MAX_CONTINUATIONS or not content:
                break

            messages.extend([
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "Продолжи ровно с места остановки. Не повторяй уже написанное. "
                        "Кратко заверши оставшиеся пункты и обязательно дай итоговый вывод."
                    ),
                },
            ])

    return "\n\n".join(parts).strip()


def telegram_plain_text(text: str) -> str:
    """Remove common Markdown that Telegram would otherwise show literally."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\[([^\]]+)]\((?:https?://|mailto:)[^)]+\)", r"\1", text)
    text = text.replace("```", "").replace("`", "")
    text = text.replace("*", "").replace("__", "").replace("~~", "")

    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.fullmatch(r"[-*_]{3,}", line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"^[-+*]\s+", "• ", line)

        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
                continue
            line = " — ".join(cell for cell in cells if cell)

        cleaned.append(line)

    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def split_message(text: str, limit: int = 4000):
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        yield text[:cut]
        text = text[cut:].lstrip()
    if text:
        yield text


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_forbidden(update):
        return
    await update.message.reply_text(
        "Я отвечаю на вопросы с точки зрения социальной архитектуры по двум загруженным источникам. "
        "Опишите ситуацию, проблему или проект — я предложу анализ, акторов, риски, метрики и следующие шаги.\n\n"
        "Команды: /sources — источники, /reset — очистить контекст беседы, /status — проверить LM Studio."
    )


async def sources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_forbidden(update):
        return
    await update.message.reply_text(
        "Источники:\n"
        "1. «Социальная архитектура: теория и практика социальных изменений», учебник, 2026.\n"
        "2. Семёнов А. Ю. «К определению социальной архитектуры», презентация."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_forbidden(update):
        return
    context.user_data["history"] = []
    await update.message.reply_text("Контекст беседы очищен.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_forbidden(update):
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.get(
                f"{BASE_URL}/models",
                headers={"Authorization": f"Bearer {API_TOKEN}"},
            )
            result.raise_for_status()
            ids = [x.get("id", "?") for x in result.json().get("data", [])]
        await update.message.reply_text(f"LM Studio доступен. Модель бота: {MODEL}\nДоступные модели: {', '.join(ids) or 'не указаны'}")
    except Exception as exc:
        await update.message.reply_text(
            f"LM Studio недоступен: {type(exc).__name__}. Проверьте Local Server и адрес {BASE_URL}."
        )


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id if update.effective_user else "неизвестен"
    await update.effective_message.reply_text(f"Ваш Telegram user ID: {user_id}")


async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_forbidden(update):
        return
    question = (update.message.text or "").strip()
    if not question:
        return
    if len(question) > MAX_QUESTION_CHARS:
        await update.message.reply_text(f"Вопрос слишком длинный. Максимум: {MAX_QUESTION_CHARS} символов.")
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    relevant_hits = KB.search(question, TOP_K)
    if not relevant_hits:
        await update.message.reply_text("В источниках не нашлось достаточно близкого материала. Попробуйте уточнить проблему, участников или желаемое изменение.")
        return
    hits = KB.foundational()
    seen = {(hit.source, hit.page, hit.text) for hit in hits}
    hits.extend(
        hit for hit in relevant_hits
        if (hit.source, hit.page, hit.text) not in seen
    )
    source_context = KB.format_context(hits, MAX_CONTEXT_CHARS)
    history = context.user_data.setdefault("history", [])
    try:
        result = telegram_plain_text(await ask_lm_studio(question, source_context, history))
    except httpx.ConnectError:
        await update.message.reply_text("Не удаётся подключиться к LM Studio. Запустите Local Server и загрузите модель qwen/qwen3-vl-8b.")
        return
    except httpx.HTTPStatusError as exc:
        await update.message.reply_text(f"LM Studio вернул ошибку HTTP {exc.response.status_code}. Проверьте имя загруженной модели командой /status.")
        return
    except Exception:
        logging.exception("LM Studio request failed")
        await update.message.reply_text("Локальная модель не смогла сформировать ответ. Подробности записаны в журнал бота.")
        return
    if not result:
        await update.message.reply_text("Модель вернула пустой ответ. Попробуйте переформулировать вопрос.")
        return
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": result}])
    del history[:-6]
    for part in split_message(result):
        await update.message.reply_text(part)


def main():
    if not TOKEN:
        raise SystemExit("Укажите TELEGRAM_BOT_TOKEN в файле .env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("sources", sources))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, answer))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
