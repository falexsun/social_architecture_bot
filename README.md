# Telegram-бот «Социальная архитектура»

Локальный RAG-бот отвечает на вопросы по двум источникам и формирует ответы через модель `qwen/qwen3-vl-8b` в LM Studio. Поиск выполняется локально по 443 фрагментам с привязкой к страницам.

## Как устроен бот

1. Пользователь пишет вопрос в Telegram.
2. Бот локально находит подходящие фрагменты книги и презентации.
3. В LM Studio отправляются вопрос, найденные выдержки и короткая история диалога.
4. Ответ возвращается в Telegram со ссылками на источник и страницы.

Облачный AI API не используется. При этом сами сообщения проходят через серверы Telegram.

## Подготовка LM Studio на Windows

1. Установите LM Studio и загрузите `qwen/qwen3-vl-8b`.
2. Откройте **Developer**, загрузите модель и включите **Start server**.
3. Убедитесь, что идентификатор в списке моделей совпадает со значением `LM_STUDIO_MODEL` в `.env`.
4. Для запуска бота в Docker включите в настройках сервера **Serve on Local Network** и разрешите LM Studio в Windows Firewall для частных сетей.

Стандартный API: `http://127.0.0.1:1234/v1`. Проверка из PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:1234/v1/models
```

## Настройка Telegram

1. Создайте бота через `@BotFather` и получите токен.
2. Скопируйте `.env.example` в `.env`:

   ```powershell
   Copy-Item .env.example .env
   ```

3. Откройте `.env` и замените `TELEGRAM_BOT_TOKEN`.

Файл `.env` исключен из Git и Docker-образа. Никогда не публикуйте токен.

## Запуск на Windows без Docker

Установите Python 3.12, затем из PowerShell в папке проекта выполните:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

При ручном запуске `LM_STUDIO_URL` должен оставаться `http://127.0.0.1:1234/v1`.

## Запуск через Docker Desktop

LM Studio остается запущенным непосредственно в Windows, а в контейнер помещается только Telegram-бот:

```powershell
docker compose up --build -d
docker compose logs -f bot
```

Compose автоматически использует `http://host.docker.internal:1234/v1`, потому что `localhost` внутри контейнера указывает на сам контейнер.

Остановка и повторный запуск:

```powershell
docker compose down
docker compose up -d
```

После изменения кода или базы знаний:

```powershell
docker compose up --build -d
```

## Проверка работы

В Telegram:

- `/status` — доступность LM Studio и список моделей;
- `/sources` — используемые источники;
- `/reset` — очистить историю беседы;
- `/whoami` — показать Telegram user ID.

Если бот должен быть личным, сначала отправьте `/whoami`, затем укажите ID в `.env`:

```dotenv
ALLOWED_TELEGRAM_USER_IDS=123456789
```

Для нескольких пользователей перечислите ID через запятую. После изменения перезапустите бот.

## Обновление базы знаний

Исходные PDF не нужны для обычного запуска: готовая база уже находится в `data/chunks.json`. Чтобы пересобрать ее:

```powershell
.\.venv\Scripts\python.exe ingest.py `
  --book "C:\путь\Социальная архитектура.pdf" `
  --slides "C:\путь\Семенов - соцарх.pdf"
```

После этого пересоберите Docker-образ.

## Настройки `.env`

- `TELEGRAM_BOT_TOKEN` — обязательный токен от BotFather.
- `LM_STUDIO_URL` — API для запуска без Docker.
- `LM_STUDIO_MODEL` — точный идентификатор модели из `/v1/models`.
- `LM_STUDIO_API_TOKEN` — токен LM Studio, если авторизация включена; иначе значение-заглушка допустимо.
- `DOCKER_LM_STUDIO_URL` — необязательная замена адреса LM Studio для Docker.
- `TOP_K` — количество найденных фрагментов.
- `MAX_CONTEXT_CHARS` — максимальный объем выдержек в запросе к модели.
- `MAX_QUESTION_CHARS` — ограничение длины пользовательского вопроса.
- `ALLOWED_TELEGRAM_USER_IDS` — необязательный белый список пользователей.

## Тесты

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

GitHub Actions автоматически проверяет Python-код, поиск по базе и сборку Docker-образа.

## Частые проблемы

- **`LM Studio недоступен`** — сервер выключен, адрес неверен либо Windows Firewall блокирует соединение.
- **HTTP 400/404 при вопросе** — значение `LM_STUDIO_MODEL` не совпадает с идентификатором модели в LM Studio.
- **Бот получает Conflict** — один Telegram-токен одновременно запущен в двух экземплярах; остановите лишний процесс или контейнер.
- **Docker не видит LM Studio** — включите **Serve on Local Network**, проверьте порт 1234 и `DOCKER_LM_STUDIO_URL`.
- **Ответ обрывается** — увеличьте контекст модели в LM Studio; для 8B-модели рекомендуется не менее 16K токенов.
