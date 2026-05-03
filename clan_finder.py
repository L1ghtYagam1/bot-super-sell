import argparse
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests


API_BASE = "https://api.clashofclans.com/v1"


@dataclass
class SearchConfig:
    name: Optional[str]
    limit: int
    min_members: Optional[int]
    max_members: Optional[int]
    min_clan_points: Optional[int]
    min_clan_level: Optional[int]
    location_id: Optional[int]
    war_frequency: Optional[str]
    label_ids: Optional[str]
    before: Optional[str]
    after: Optional[str]
    tag_length: Optional[int]


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


def get_api_token() -> str:
    token = os.getenv("COC_API_TOKEN")
    if not token:
        raise RuntimeError(
            "Не найден COC_API_TOKEN. Добавь переменную окружения или .env через setx."
        )
    return token


def build_params(cfg: SearchConfig) -> Dict[str, Any]:
    params: Dict[str, Any] = {"limit": cfg.limit}

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


def fetch_clans(cfg: SearchConfig) -> List[Dict[str, Any]]:
    token = get_api_token()
    headers = {"Authorization": f"Bearer {token}"}
    params = build_params(cfg)

    response = requests.get(
        f"{API_BASE}/clans",
        headers=headers,
        params=params,
        timeout=20,
    )
    if response.status_code >= 400:
        try:
            api_error = response.json()
        except ValueError:
            api_error = {"message": response.text}
        raise RuntimeError(
            f"Ошибка API {response.status_code}: {api_error.get('reason', '')} {api_error.get('message', '')}".strip()
        )
    data = response.json()
    items = data.get("items", [])

    if cfg.tag_length is not None:
        items = [c for c in items if len(c.get("tag", "")) == cfg.tag_length]

    return items


def format_clan(c: Dict[str, Any]) -> str:
    return (
        f"{c.get('name', 'Unknown')} | "
        f"{c.get('tag', '-'):<10} | "
        f"lvl {c.get('clanLevel', '-')} | "
        f"members {c.get('members', '-')} | "
        f"points {c.get('clanPoints', '-')}"
    )


def parse_args() -> SearchConfig:
    parser = argparse.ArgumentParser(
        description="Поиск кланов Clash of Clans с фильтром по длине тега."
    )
    parser.add_argument("--name", type=str, help="Имя клана (часть имени).")
    parser.add_argument("--limit", type=int, default=50, help="Лимит выдачи API (max 50).")
    parser.add_argument("--min-members", type=int, help="Минимум участников.")
    parser.add_argument("--max-members", type=int, help="Максимум участников.")
    parser.add_argument("--min-clan-points", type=int, help="Минимум очков клана.")
    parser.add_argument("--min-clan-level", type=int, help="Минимум уровня клана.")
    parser.add_argument("--location-id", type=int, help="ID региона (locationId).")
    parser.add_argument(
        "--war-frequency",
        type=str,
        choices=["always", "moreThanOncePerWeek", "oncePerWeek", "never", "unknown"],
        help="Частота войн.",
    )
    parser.add_argument(
        "--label-ids",
        type=str,
        help="CSV список id меток клана, например 56000000,56000001",
    )
    parser.add_argument(
        "--before",
        type=str,
        help="Курсор страницы до указанного значения (paging cursor).",
    )
    parser.add_argument(
        "--after",
        type=str,
        help="Курсор страницы после указанного значения (paging cursor).",
    )
    parser.add_argument(
        "--tag-length",
        type=int,
        help="Точная длина тега клана, например 9 для #XXXXXXXX.",
    )

    args = parser.parse_args()

    return SearchConfig(
        name=args.name,
        limit=max(1, min(args.limit, 50)),
        min_members=args.min_members,
        max_members=args.max_members,
        min_clan_points=args.min_clan_points,
        min_clan_level=args.min_clan_level,
        location_id=args.location_id,
        war_frequency=args.war_frequency,
        label_ids=args.label_ids,
        before=args.before,
        after=args.after,
        tag_length=args.tag_length,
    )


def main() -> None:
    load_env_file_if_present()
    cfg = parse_args()
    clans = fetch_clans(cfg)

    if not clans:
        print("Кланы не найдены по заданным фильтрам.")
        return

    print(f"Найдено кланов: {len(clans)}")
    for clan in clans:
        print(format_clan(clan))


if __name__ == "__main__":
    main()
