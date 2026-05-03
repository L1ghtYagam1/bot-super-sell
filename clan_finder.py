import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes


API_BASE = "https://api.clashofclans.com/v1"
MAX_LIMIT = 15
FIND_COOLDOWN_SECONDS = 60
SETTINGS_PATH = Path("chat_settings.json")
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


INT_FIELDS = {
    "limit": "limit",
    "min_members": "min_members",
    "max_members": "max_members",
    "min_clan_points": "min_clan_points",
    "min_clan_level": "min_clan_level",
    "location_id": "location_id",
    "tag_length": "tag_length",
}
STR_FIELDS = {
    "name": "name",
    "war_frequency": "war_frequency",
    "label_ids": "label_ids",
    "before": "before",
    "after": "after",
}
ALL_FIELDS = list(INT_FIELDS.keys()) + list(STR_FIELDS.keys())


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


def parse_kv_args(args: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw in args:
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if key and value:
            result[key] = value
    return result


def parse_find_args(args: List[str]) -> SearchConfig:
    cfg = SearchConfig()
    kv = parse_kv_args(args)

    for key, value in kv.items():
        if key in INT_FIELDS:
            setattr(cfg, INT_FIELDS[key], int(value))
        elif key in STR_FIELDS:
            setattr(cfg, STR_FIELDS[key], value)

    cfg.limit = max(1, min(cfg.limit, MAX_LIMIT))
    return cfg


def merge_configs(base: SearchConfig, override: SearchConfig) -> SearchConfig:
    merged = SearchConfig(**asdict(base))
    for field, value in asdict(override).items():
        if field == "limit":
            if value != MAX_LIMIT:
                setattr(merged, field, value)
            continue
        if value is not None:
            setattr(merged, field, value)
    merged.limit = max(1, min(merged.limit, MAX_LIMIT))
    return merged


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


def load_chat_settings() -> Dict[str, Dict[str, Any]]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_chat_settings(data: Dict[str, Dict[str, Any]]) -> None:
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_default_config(chat_id: int) -> SearchConfig:
    settings = load_chat_settings()
    raw = settings.get(str(chat_id), {})
    cfg = SearchConfig()
    for key, value in raw.items():
        if key in INT_FIELDS.values() and value is not None:
            setattr(cfg, key, int(value))
        elif key in STR_FIELDS.values() and value:
            setattr(cfg, key, str(value))
    cfg.limit = max(1, min(cfg.limit, MAX_LIMIT))
    return cfg


def set_chat_default_config(chat_id: int, cfg: SearchConfig) -> None:
    settings = load_chat_settings()
    settings[str(chat_id)] = asdict(cfg)
    save_chat_settings(settings)


def clear_chat_default_config(chat_id: int) -> None:
    settings = load_chat_settings()
    if str(chat_id) in settings:
        del settings[str(chat_id)]
        save_chat_settings(settings)


def format_config(cfg: SearchConfig) -> str:
    data = asdict(cfg)
    lines = ["Текущие параметры:"]
    for k in ALL_FIELDS:
        v = data.get(k)
        lines.append(f"- {k}={v}")
    return "\n".join(lines)


HELP_TEXT = """Команды:
/start - запуск бота
/help - справка
/set key=value ... - сохранить параметры поиска для этого чата
/show - показать сохраненные параметры
/clear - сбросить сохраненные параметры
/find [key=value ...] - поиск кланов

Примеры:
/set name=fire min_members=30 min_clan_level=10 tag_length=9 limit=10
/find
/find name=ice limit=5

Параметры:
name, limit, min_members, max_members, min_clan_points, min_clan_level,
location_id, war_frequency, label_ids, before, after, tag_length

Ограничение:
/find не чаще 1 раза в минуту, максимум 15 кланов за запрос.
"""


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Бот запущен. Используй /find для поиска кланов Clash of Clans.\n\n" + HELP_TEXT
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT)


async def set_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    try:
        cfg = parse_find_args(context.args)
    except Exception as exc:
        await update.message.reply_text(f"Ошибка в параметрах: {exc}")
        return

    set_chat_default_config(chat.id, cfg)
    await update.message.reply_text("Параметры сохранены.\n" + format_config(cfg))


async def show_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    cfg = get_chat_default_config(chat.id)
    await update.message.reply_text(format_config(cfg))


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    clear_chat_default_config(chat.id)
    await update.message.reply_text("Сохраненные параметры сброшены для этого чата.")


async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
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
        saved_cfg = get_chat_default_config(chat.id)
        one_time_cfg = parse_find_args(context.args)
        cfg = merge_configs(saved_cfg, one_time_cfg)

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
    for clan in clans[:15]:
        lines.append(format_clan(clan))

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
    app.add_handler(CommandHandler("set", set_cmd))
    app.add_handler(CommandHandler("show", show_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("find", find_cmd))
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
