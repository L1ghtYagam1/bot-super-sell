# Clash of Clans Telegram Bot

Telegram-бот для поиска кланов Clash of Clans через официальный API.

## Что умеет

- Команда `/poisk` с фильтрами поиска
- Отдельные сохраненные параметры по каждому чату (`/ustanovit`, `/pokazat`, `/sbros`)
- Фильтр по длине тега (`tag_length`)
- Лимит поиска: 15 кланов в минуту
- Запуск в Docker Compose

## `.env` файл

Создай `.env` рядом с `docker-compose.yml`:

```env
TELEGRAM_BOT_TOKEN=ТВОЙ_TELEGRAM_BOT_TOKEN
COC_API_TOKEN=ТВОЙ_COC_API_TOKEN
```

## Запуск

```powershell
docker compose up -d --build
```

Проверка логов:

```powershell
docker compose logs -f bot
```

Остановка:

```powershell
docker compose down
```

## Команды в Telegram

- `/start`
- `/help`
- `/ustanovit key=value ...` - сохранить параметры для этого чата
- `/pokazat` - показать сохраненные параметры
- `/sbros` - сбросить сохраненные параметры
- `/poisk [key=value ...]` - поиск (если параметры не переданы, берутся из `/ustanovit`)
- Алиасы тоже работают: `/set`, `/show`, `/clear`, `/find`

Пример:

```text
/ustanovit name=fire min_members=30 min_clan_level=10 tag_length=9 limit=10
/poisk
/poisk name=ice limit=5
```

## Доступные параметры

- `name`
- `limit` (1..15)
- `min_members`
- `max_members`
- `min_clan_points`
- `min_clan_level`
- `location_id`
- `war_frequency` (`always`, `moreThanOncePerWeek`, `oncePerWeek`, `never`, `unknown`)
- `label_ids` (CSV id меток, например `56000000,56000001`)
- `before` (cursor для пагинации API)
- `after` (cursor для пагинации API)
- `tag_length` (точная длина тега, включая `#`)

Примечание: `/poisk` не чаще 1 раза в минуту на чат.
