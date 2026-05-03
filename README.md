# Clash of Clans Telegram Bot

Telegram-бот для поиска кланов Clash of Clans через официальный API.

## Что умеет

- Команда `/find` с фильтрами поиска
- Отдельные сохраненные параметры по каждому чату (`/set`, `/show`, `/clear`)
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
- `/set key=value ...` - сохранить параметры для этого чата
- `/show` - показать сохраненные параметры
- `/clear` - сбросить сохраненные параметры
- `/find [key=value ...]` - поиск (если параметры не переданы, берутся из `/set`)

Пример:

```text
/set name=fire min_members=30 min_clan_level=10 tag_length=9 limit=10
/find
/find name=ice limit=5
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

Примечание: `/find` не чаще 1 раза в минуту на чат.
