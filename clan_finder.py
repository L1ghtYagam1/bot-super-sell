import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


API_BASE = "https://api.clashofclans.com/v1"
MAX_LIMIT = 15
FIND_COOLDOWN_SECONDS = 60
LAST_FIND_TS_BY_CHAT: Dict[int, float] = {}


@dataclass
class SearchConfig:
    name: Optional[str] = None
    limit: int = MAX_LIMIT
    min_members: Optional[int] = None
    max_members: Optional[int] = None
    min_clan_points: Optional[int] = None
    min_clan_level: Optional[int] = None
    location_id: Optional[int] = None
    war_frequency: Optional[str] = None
    label_ids: Optional[str] = None
    before: Optional[str] = None
    after: Optional[str] = None
    tag_length: Optional[int] = None


def load_env_file_if_present(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def build_params(cfg: SearchConfig) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": max(1, min(cfg.limit, MAX_LIMIT))}
    if cfg.name:
        params["name"] = cfg.name
    if cfg.min_members is not None:
        params["minMembers"] = cfg.min_members
    if cfg.max_members is not None:
        params["maxMembers"] = cfg.max_members
    if cfg.min_clan_points is not None:
        params["minClanPoints"] = cfg.min_clan_points
    if cfg.min_clan_level is not None:
        params["minClanLevel"] = cfg.min_clan_level
    if cfg.location_id is not None:
        params["locationId"] = cfg.location_id
    if cfg.war_frequency:
        params["warFrequency"] = cfg.war_frequency
    if cfg.label_ids:
        params["labelIds"] = cfg.label_ids
    if cfg.before:
        params["before"] = cfg.before
    if cfg.after:
        params["after"] = cfg.after
    return params


def fetch_clans(api_token: str, cfg: SearchConfig) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_token}"}
    response = requests.get(
        f"{API_BASE}/clans", headers=headers, params=build_params(cfg), timeout=20
    )
    if response.status_code >= 400:
        try:
            api_error = response.json()
        except ValueError:
            api_error = {"message": response.text}
        reason = api_error.get("reason", "")
        message = api_error.get("message", "")
        raise RuntimeError(f"API {response.status_code}: {reason} {message}".strip())

    items = response.json().get("items", [])
    if cfg.tag_length is not None:
        items = [clan for clan in items if len(clan.get("tag", "")) == cfg.tag_length]
    return items


def format_clan(c: Dict[str, Any]) -> str:
    return (
        f"{c.get('name', 'Unknown')} | {c.get('tag', '-')}"
        f" | lvl {c.get('clanLevel', '-')}"
        f" | members {c.get('members', '-')}"
        f" | points {c.get('clanPoints', '-')}"
    )


def parse_find_args(args: List[str]) -> SearchConfig:
    cfg = SearchConfig()
    int_fields = {
        "limit": "limit",
        "min_members": "min_members",
        "max_members": "max_members",
        "min_clan_points": "min_clan_points",
        "min_clan_level": "min_clan_level",
        "location_id": "location_id",
        "tag_length": "tag_length",
    }
    str_fields = {
        "name": "name",
        "war_frequency": "war_frequency",
        "label_ids": "label_ids",
        "before": "before",
        "after": "after",
    }

    for raw in args:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not value:
            continue

        if key in int_fields:
            setattr(cfg, int_fields[key], int(value))
        elif key in str_fields:
            setattr(cfg, str_fields[key], value)

    cfg.limit = max(1, min(cfg.limit, MAX_LIMIT))
    return cfg


HELP_TEXT = """Команды:
/start - запуск бота
/help - справка
/find key=value ... - поиск кланов

Пример:
/find name=fire min_members=30 min_clan_level=10 tag_length=9 limit=10

Параметры:
name, limit, min_members, max_members, min_clan_points, min_clan_level,
location_id, war_frequency, label_ids, before, after, tag_length

Ограничение:
/find не чаще 1 раза в минуту, максимум 15 кланов за запрос.
"""


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Бот запущен. Используй /find для поиска кланов Clash of Clans.\n\n" + HELP_TEXT
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    now = time.time()
    last_ts = LAST_FIND_TS_BY_CHAT.get(chat.id, 0.0)
    remaining = int(FIND_COOLDOWN_SECONDS - (now - last_ts))
    if remaining > 0:
        await update.message.reply_text(
            f"Подожди {remaining} сек. Лимит: 15 кланов в минуту."
        )
        return

    try:
        cfg = parse_find_args(context.args)
        api_token = require_env("COC_API_TOKEN")
        clans = fetch_clans(api_token, cfg)
    except Exception as exc:
        await update.message.reply_text(f"Ошибка: {exc}")
        return
    LAST_FIND_TS_BY_CHAT[chat.id] = now

    if not clans:
        await update.message.reply_text("Кланы не найдены по заданным фильтрам.")
        return

    lines = [f"Найдено кланов: {len(clans)}"]
    for clan in clans[:20]:
        lines.append(format_clan(clan))
    if len(clans) > 20:
        lines.append("Показаны первые 20 результатов.")

    await update.message.reply_text("\n".join(lines))


def main() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )

    load_env_file_if_present()
    tg_token = require_env("TELEGRAM_BOT_TOKEN")

    app = Application.builder().token(tg_token).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
