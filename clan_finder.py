import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


API_BASE = "https://api.clashofclans.com/v1"
MAX_LIMIT = 15
SETTINGS_PATH = Path("chat_settings.json")
MAX_SCAN_PAGES = 10
API_PAGE_LIMIT = 50
CURSORS_PATH = Path("chat_cursors.json")
END_CURSOR = "__END__"
SEEN_TAGS_PATH = Path("chat_seen_tags.json")


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
    clan_type: Optional[str] = None
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
    "clan_type": "clan_type",
    "label_ids": "label_ids",
    "before": "before",
    "after": "after",
}
ALL_FIELDS = list(INT_FIELDS.keys()) + list(STR_FIELDS.keys())
FIELD_LABELS = {
    "name": "Название",
    "limit": "Лимит",
    "min_members": "Мин. участники",
    "max_members": "Макс. участники",
    "min_clan_points": "Мин. очки",
    "min_clan_level": "Мин. уровень",
    "location_id": "Location ID",
    "war_frequency": "Частота войн",
    "clan_type": "Тип клана",
    "label_ids": "Label IDs",
    "before": "Курсор before",
    "after": "Курсор after",
    "tag_length": "Длина тега",
}


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


def normalize_config(cfg: SearchConfig) -> SearchConfig:
    cfg.limit = max(1, min(cfg.limit, MAX_LIMIT))

    if cfg.min_members is not None and cfg.min_members < 2:
        cfg.min_members = 2
    if cfg.max_members is not None and cfg.max_members < 2:
        cfg.max_members = 2
    if (
        cfg.min_members is not None
        and cfg.max_members is not None
        and cfg.min_members > cfg.max_members
    ):
        cfg.max_members = cfg.min_members

    if cfg.min_clan_level is not None and cfg.min_clan_level < 1:
        cfg.min_clan_level = 1
    if cfg.min_clan_points is not None and cfg.min_clan_points < 0:
        cfg.min_clan_points = 0
    if cfg.tag_length is not None and cfg.tag_length < 2:
        cfg.tag_length = 2
    if cfg.clan_type:
        normalized = cfg.clan_type.strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        aliases = {
            "open": "open",
            "opened": "open",
            "otkrytyi": "open",
            "otkrytyy": "open",
            "открытый": "open",
            "closed": "closed",
            "zakrytyi": "closed",
            "zakrytyy": "closed",
            "закрытый": "closed",
            "inviteonly": "inviteOnly",
            "invite": "inviteOnly",
            "popriglasheniyu": "inviteOnly",
            "поприглашению": "inviteOnly",
        }
        cfg.clan_type = aliases.get(normalized, cfg.clan_type)

    return cfg


def build_params(cfg: SearchConfig) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": API_PAGE_LIMIT}
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
    if cfg.clan_type:
        params["type"] = cfg.clan_type
    if cfg.label_ids:
        params["labelIds"] = cfg.label_ids
    if cfg.before:
        params["before"] = cfg.before
    if cfg.after:
        params["after"] = cfg.after

    has_real_filter = any(
        [
            cfg.name,
            cfg.min_members is not None,
            cfg.max_members is not None,
            cfg.min_clan_points is not None,
            cfg.min_clan_level is not None,
            cfg.location_id is not None,
            cfg.war_frequency,
            cfg.clan_type,
            cfg.label_ids,
        ]
    )
    if not has_real_filter:
        params["minMembers"] = 2
    return params


def fetch_clans(api_token: str, cfg: SearchConfig) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_token}"}
    collected: List[Dict[str, Any]] = []
    seen_tags = set()
    next_after: Optional[str] = cfg.after

    for _ in range(MAX_SCAN_PAGES):
        page_cfg = SearchConfig(**asdict(cfg))
        page_cfg.after = next_after
        response = requests.get(
            f"{API_BASE}/clans", headers=headers, params=build_params(page_cfg), timeout=20
        )
        if response.status_code >= 400:
            try:
                api_error = response.json()
            except ValueError:
                api_error = {"message": response.text}
            reason = api_error.get("reason", "")
            message = api_error.get("message", "")
            raise RuntimeError(f"API {response.status_code}: {reason} {message}".strip())

        data = response.json()
        items = data.get("items", [])
        if cfg.tag_length is not None:
            items = [clan for clan in items if len(clan.get("tag", "")) == cfg.tag_length]
        for item in items:
            tag = item.get("tag")
            if tag and tag in seen_tags:
                continue
            if tag:
                seen_tags.add(tag)
            collected.append(item)

        if len(collected) >= cfg.limit:
            break

        next_after = (
            data.get("paging", {})
            .get("cursors", {})
            .get("after")
        )
        if not next_after:
            break

    return collected[: cfg.limit]


def load_chat_cursors() -> Dict[str, str]:
    if not CURSORS_PATH.exists():
        return {}
    try:
        with open(CURSORS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        pass
    return {}


def load_seen_tags() -> Dict[str, List[str]]:
    if not SEEN_TAGS_PATH.exists():
        return {}
    try:
        with open(SEEN_TAGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                str(k): [str(x) for x in v if x]
                for k, v in data.items()
                if isinstance(v, list)
            }
    except Exception:
        pass
    return {}


def save_seen_tags(data: Dict[str, List[str]]) -> None:
    with open(SEEN_TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_seen_tags(chat_id: int) -> set[str]:
    return set(load_seen_tags().get(str(chat_id), []))


def add_chat_seen_tags(chat_id: int, tags: List[str]) -> None:
    data = load_seen_tags()
    key = str(chat_id)
    existing = set(data.get(key, []))
    existing.update([t for t in tags if t])
    data[key] = sorted(existing)
    save_seen_tags(data)


def clear_chat_seen_tags(chat_id: int) -> None:
    data = load_seen_tags()
    key = str(chat_id)
    if key in data:
        del data[key]
        save_seen_tags(data)


def save_chat_cursors(data: Dict[str, str]) -> None:
    with open(CURSORS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_chat_cursor(chat_id: int) -> Optional[str]:
    return load_chat_cursors().get(str(chat_id))


def set_chat_cursor(chat_id: int, cursor: Optional[str]) -> None:
    data = load_chat_cursors()
    key = str(chat_id)
    if cursor is not None:
        data[key] = cursor
    elif key in data:
        del data[key]
    save_chat_cursors(data)


def fetch_clans_with_next_cursor(
    api_token: str, cfg: SearchConfig
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    headers = {"Authorization": f"Bearer {api_token}"}
    collected: List[Dict[str, Any]] = []
    seen_tags = set()
    next_after: Optional[str] = cfg.after

    for _ in range(MAX_SCAN_PAGES):
        page_cfg = SearchConfig(**asdict(cfg))
        page_cfg.after = next_after
        response = requests.get(
            f"{API_BASE}/clans", headers=headers, params=build_params(page_cfg), timeout=20
        )
        if response.status_code >= 400:
            try:
                api_error = response.json()
            except ValueError:
                api_error = {"message": response.text}
            reason = api_error.get("reason", "")
            message = api_error.get("message", "")
            raise RuntimeError(f"API {response.status_code}: {reason} {message}".strip())

        data = response.json()
        items = data.get("items", [])
        if cfg.tag_length is not None:
            items = [clan for clan in items if len(clan.get("tag", "")) == cfg.tag_length]
        for item in items:
            tag = item.get("tag")
            if tag and tag in seen_tags:
                continue
            if tag:
                seen_tags.add(tag)
            collected.append(item)

        next_after = data.get("paging", {}).get("cursors", {}).get("after")
        if len(collected) >= cfg.limit or not next_after:
            break

    return collected[: cfg.limit], next_after


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
    cfg = normalize_config(cfg)
    settings = load_chat_settings()
    settings[str(chat_id)] = asdict(cfg)
    save_chat_settings(settings)


def clear_chat_default_config(chat_id: int) -> None:
    settings = load_chat_settings()
    if str(chat_id) in settings:
        del settings[str(chat_id)]
        save_chat_settings(settings)
    set_chat_cursor(chat_id, None)
    clear_chat_seen_tags(chat_id)


def format_config(cfg: SearchConfig) -> str:
    cfg = normalize_config(cfg)
    data = asdict(cfg)
    lines = ["Текущие параметры:"]
    for k in ALL_FIELDS:
        v = data.get(k)
        lines.append(f"- {k}={v}")
    return "\n".join(lines)


def settings_keyboard() -> InlineKeyboardMarkup:
    rows = []
    row: List[InlineKeyboardButton] = []
    for field in ALL_FIELDS:
        row.append(InlineKeyboardButton(FIELD_LABELS[field], callback_data=f"setfield:{field}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    rows.append([
        InlineKeyboardButton("Показать", callback_data="action:show"),
        InlineKeyboardButton("Сброс", callback_data="action:clear"),
    ])
    rows.append([InlineKeyboardButton("Искать", callback_data="action:find")])
    return InlineKeyboardMarkup(rows)


HELP_TEXT = """Команды:
/start - запуск бота
/help - справка
/ustanovit key=value ... - сохранить параметры поиска для этого чата
/pokazat - показать сохраненные параметры
/sbros - сбросить сохраненные параметры
/poisk [key=value ...] - поиск кланов
/knopki - открыть кнопки настройки

Примеры:
/ustanovit name=fire min_members=30 min_clan_level=10 tag_length=9 limit=10
/ustanovit clan_type=inviteOnly
/poisk
/poisk name=ice limit=5

Ограничение:
максимум 15 кланов за запрос.
"""


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Бот запущен. Используй /knopki для настройки параметров.\n\n" + HELP_TEXT,
            reply_markup=settings_keyboard(),
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT, reply_markup=settings_keyboard())


async def buttons_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("Выбери параметр для настройки:", reply_markup=settings_keyboard())


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
    await update.message.reply_text("Параметры сохранены.\n" + format_config(cfg), reply_markup=settings_keyboard())


async def show_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    cfg = get_chat_default_config(chat.id)
    await update.message.reply_text(format_config(cfg), reply_markup=settings_keyboard())


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None or update.message is None:
        return

    clear_chat_default_config(chat.id)
    await update.message.reply_text("Сохраненные параметры сброшены для этого чата.", reply_markup=settings_keyboard())


async def run_find(update: Update, context: ContextTypes.DEFAULT_TYPE, override_args: Optional[List[str]] = None) -> None:
    chat = update.effective_chat
    message = update.effective_message
    if chat is None or message is None:
        return

    try:
        saved_cfg = get_chat_default_config(chat.id)
        args = override_args if override_args is not None else context.args
        one_time_cfg = parse_find_args(args)
        cfg = normalize_config(merge_configs(saved_cfg, one_time_cfg))
        if cfg.after is None:
            stored_cursor = get_chat_cursor(chat.id)
            if stored_cursor == END_CURSOR:
                await message.reply_text("Новых кланов по этим фильтрам больше нет. Нажми Сброс (/sbros), чтобы начать сначала.")
                return
            cfg.after = stored_cursor
        api_token = require_env("COC_API_TOKEN")
        clans, next_cursor = fetch_clans_with_next_cursor(api_token, cfg)
        seen_tags = get_chat_seen_tags(chat.id)
        clans = [c for c in clans if c.get("tag") not in seen_tags]
        add_chat_seen_tags(chat.id, [c.get("tag", "") for c in clans])
        set_chat_cursor(chat.id, next_cursor if next_cursor else END_CURSOR)
    except Exception as exc:
        await message.reply_text(f"Ошибка: {exc}")
        return

    if not clans:
        await message.reply_text("Кланы не найдены по заданным фильтрам.")
        return

    lines = [f"Найдено кланов: {len(clans)}"]
    for clan in clans[:15]:
        lines.append(format_clan(clan))
    await message.reply_text("\n".join(lines))


async def find_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_find(update, context)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.message is None:
        return

    await query.answer()
    chat = query.message.chat

    data = query.data or ""
    if data.startswith("setfield:"):
        field = data.split(":", 1)[1]
        if field not in ALL_FIELDS:
            await query.message.reply_text("Неизвестное поле.")
            return
        context.user_data["pending_field"] = field
        await query.message.reply_text(
            f"Введи значение для {FIELD_LABELS[field]} ({field}).\n"
            "Чтобы очистить параметр, отправь: -"
        )
        return

    if data == "action:show":
        cfg = get_chat_default_config(chat.id)
        await query.message.reply_text(format_config(cfg), reply_markup=settings_keyboard())
        return

    if data == "action:clear":
        clear_chat_default_config(chat.id)
        await query.message.reply_text("Сохраненные параметры сброшены.", reply_markup=settings_keyboard())
        return

    if data == "action:find":
        await run_find(update, context, override_args=[])


async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.effective_chat is None:
        return

    pending_field = context.user_data.get("pending_field")
    if not pending_field:
        return

    value_raw = (update.message.text or "").strip()
    context.user_data.pop("pending_field", None)

    cfg = get_chat_default_config(update.effective_chat.id)

    try:
        if value_raw == "-":
            if pending_field == "limit":
                setattr(cfg, pending_field, MAX_LIMIT)
            else:
                setattr(cfg, pending_field, None)
        elif pending_field in INT_FIELDS:
            setattr(cfg, pending_field, int(value_raw))
        else:
            setattr(cfg, pending_field, value_raw)

        cfg = normalize_config(cfg)
        set_chat_default_config(update.effective_chat.id, cfg)
        await update.message.reply_text(
            f"Параметр {pending_field} обновлен.\n" + format_config(cfg),
            reply_markup=settings_keyboard(),
        )
    except ValueError:
        await update.message.reply_text("Неверный формат числа. Попробуй снова через /knopki.")


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
    app.add_handler(CommandHandler("knopki", buttons_cmd))

    app.add_handler(CommandHandler("set", set_cmd))
    app.add_handler(CommandHandler("show", show_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("find", find_cmd))

    app.add_handler(CommandHandler("ustanovit", set_cmd))
    app.add_handler(CommandHandler("pokazat", show_cmd))
    app.add_handler(CommandHandler("sbros", clear_cmd))
    app.add_handler(CommandHandler("poisk", find_cmd))

    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler))

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
