# Clash of Clans Clan Finder

Бот для поиска кланов через Clash of Clans API с фильтрами, включая фильтр по длине тега.

## Локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Токен API

Получи токен на [developer.clashofclans.com](https://developer.clashofclans.com).

Вариант 1 (переменная окружения):

```powershell
setx COC_API_TOKEN "ТВОЙ_ТОКЕН"
```

Вариант 2 (`.env` рядом со скриптом):

```env
COC_API_TOKEN=ТВОЙ_ТОКЕН
```

## Docker

### Запуск через docker compose up -d

1. Создай `.env` с токеном.
2. При необходимости поменяй фильтры в `docker-compose.yml` -> `services.bot.command`.
3. Запусти:

```powershell
docker compose up -d --build
```

Логи:

```powershell
docker compose logs -f bot
```

Остановка и удаление контейнера:

```powershell
docker compose down
```

## Доступные фильтры

- `--name`
- `--limit` (1..50)
- `--min-members`
- `--max-members`
- `--min-clan-points`
- `--min-clan-level`
- `--location-id`
- `--war-frequency` (`always`, `moreThanOncePerWeek`, `oncePerWeek`, `never`, `unknown`)
- `--label-ids` (CSV id меток, например `56000000,56000001`)
- `--before` (cursor для пагинации API)
- `--after` (cursor для пагинации API)
- `--tag-length` (точная длина тега, включая `#`)
