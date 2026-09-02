"""PESDB eFootball 2027 scraper for Standard players only.

The 2027 PESDB website no longer exposes the legacy table and ?id= routes.
This module uses the public Standard-player search endpoint and the new
semantic player pages, while preserving the final FMC import schema.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from scraping_pesdb_unificato import (
    DEFAULT_EXCLUDED_COLUMNS,
    POSITION_CODES,
    POSITION_TRANSLATIONS,
    build_diff,
    load_custom_rules,
    normalize_final_player_values,
    normalize_text,
    split_into_chunks,
    transform_dataframe,
)


SITE_ROOT = "https://pesdb.net"
PLAYERS_URL = f"{SITE_ROOT}/efootball/players/"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
CHUNKS_DIR = OUTPUT_DIR / "chunks_2027"
STATE_FILE = Path(__file__).resolve().parent / "data" / "pesdb_2027_state.json"
PREVIOUS_DATA_FILE = Path(__file__).resolve().parent / "data" / "pesdb_players_it.json"

REQUEST_TIMEOUT = int(os.getenv("PESDB_2027_REQUEST_TIMEOUT", "30"))
# The public search endpoint starts rate-limiting sustained fast pagination.
# Keep discovery intentionally conservative; it runs before any detail requests.
LIST_DELAY_SECONDS = float(os.getenv("PESDB_2027_LIST_DELAY_SECONDS", "2.5"))
DETAIL_DELAY_SECONDS = float(os.getenv("PESDB_2027_DETAIL_DELAY_SECONDS", "0.35"))
REQUEST_RETRIES = int(os.getenv("PESDB_2027_REQUEST_RETRIES", "5"))
LIST_RETRIES = int(os.getenv("PESDB_2027_LIST_RETRIES", "2"))
RETRY_BASE_SECONDS = float(os.getenv("PESDB_2027_RETRY_BASE_SECONDS", "12"))
CHUNK_SIZE = int(os.getenv("PESDB_2027_CHUNK_SIZE", "75"))
FORCE_FULL = os.getenv("PESDB_2027_FORCE_FULL", "0").lower() in {"1", "true", "yes"}

# PESDB 2027 renamed a few entries compared with the labels used by the
# historical FMC translation rules. Convert them before the common transform.
SITE_VALUE_ALIASES = {
    "First Time Shot": "Tiro di Prima",
    "One Touch Pass": "Passaggio di Prima",
    "Super Sub": "Super Riserva",
    "Cut Behind Turn": "Doppio Passo e Giro",
    "Long Range Curler": "Tiro a Giro da Lontano",
    "Full-back Finisher": "Terzino Finalizzatore",
    "Covering Role": "Copertura",
}


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; FMC-PESDB/2027; +https://github.com/riccardopetruzzellis/scraping_pesdb)",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_attempts: int | None = None,
    fail_fast_on_rate_limit: bool = False,
    **kwargs,
) -> requests.Response:
    last_error: Exception | None = None
    attempts = max_attempts or REQUEST_RETRIES
    for attempt in range(1, attempts + 1):
        try:
            response = session.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
            if response.status_code == 429 and fail_fast_on_rate_limit:
                raise RuntimeError(
                    "PESDB rate limit during discovery. The workflow stopped before wasting time; retry later."
                )
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            last_error = requests.HTTPError(f"HTTP {response.status_code} for {url}", response=response)
        except requests.RequestException as exc:
            last_error = exc

        if attempt == attempts:
            break
        retry_after = getattr(getattr(last_error, "response", None), "headers", {}).get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else RETRY_BASE_SECONDS * attempt
        delay += random.uniform(0, 1.5)
        print(f"[RETRY] {method} {url} attempt {attempt}/{attempts}, waiting {delay:.1f}s", flush=True)
        time.sleep(delay)
    raise last_error or RuntimeError(f"Request failed for {url}")


def player_id_from_url(url: str) -> str:
    match = re.search(r"-(\d+)$", url.rstrip("/"))
    if not match:
        raise ValueError(f"PESDB player id missing from URL: {url}")
    return match.group(1)


def parse_page_count(soup: BeautifulSoup) -> int:
    status = soup.select_one(".pagination-status")
    if not status:
        return 1
    match = re.search(r"of\s+([\d,]+)", status.get_text(" ", strip=True), flags=re.IGNORECASE)
    return int(match.group(1).replace(",", "")) if match else 1


def parse_standard_result_cards(soup: BeautifulSoup) -> list[dict]:
    players: list[dict] = []
    for card in soup.select("article.efootball-result-card"):
        link = card.select_one("a.efootball-result-image[href]") or card.select_one("h2 a[href]")
        if not link:
            continue
        url = urljoin(SITE_ROOT, link["href"])
        card_type_node = card.select_one(".card-type")
        card_type = normalize_text(card_type_node.get_text(" ", strip=True)) if card_type_node else ""
        if card_type != "Standard":
            continue
        image = card.select_one("img[alt]")
        alt = normalize_text(image.get("alt", "")) if image else ""
        match = re.search(r"[\u2014-]\s*([A-Z]+),\s*OVR\s*(\d+),\s*MAX\s*(\d+)$", alt)
        name_node = card.select_one("h2")
        players.append(
            {
                "pesdb_id": player_id_from_url(url),
                "url": url,
                "name": normalize_text(name_node.get_text(" ", strip=True)) if name_node else "",
                "role": match.group(1) if match else "",
                "overall": match.group(2) if match else "",
                "max_overall": match.group(3) if match else "",
            }
        )
    return players


def discover_standard_players(max_pages: int | None = None) -> tuple[list[dict], list[dict]]:
    session = build_session()
    players_by_id: dict[str, dict] = {}
    logs: list[dict] = []
    page = 1
    total_pages: int | None = None
    while total_pages is None or page <= total_pages:
        if max_pages is not None and page > max_pages:
            break
        response = request_with_retry(
            session,
            "GET",
            PLAYERS_URL,
            max_attempts=LIST_RETRIES,
            fail_fast_on_rate_limit=True,
            params={"availability": "standard", "page": page},
        )
        soup = BeautifulSoup(response.text, "html.parser")
        total_pages = parse_page_count(soup) if total_pages is None else total_pages
        page_players = parse_standard_result_cards(soup)
        logs.append({"page": page, "players": len(page_players), "etag": response.headers.get("ETag", "")})
        if not page_players:
            raise RuntimeError(f"No Standard players found on page {page}; source layout may have changed")
        for player in page_players:
            players_by_id[player["pesdb_id"]] = player
        print(f"[DISCOVERY] Standard page {page}/{total_pages}: {len(page_players)} players", flush=True)
        page += 1
        time.sleep(LIST_DELAY_SECONDS)
    return list(players_by_id.values()), logs


def section_details(soup: BeautifulSoup, heading: str) -> dict[str, str]:
    for section in soup.select("section.player-info-panel"):
        title = section.find("h2")
        if title and normalize_text(title.get_text(" ", strip=True)) == heading:
            return {
                normalize_text(row.find("dt").get_text(" ", strip=True)): normalize_text(row.find("dd").get_text(" ", strip=True))
                for row in section.select("dl > div")
                if row.find("dt") and row.find("dd")
            }
    return {}


def normalize_site_value(value: str) -> str:
    clean_value = normalize_text(value)
    return SITE_VALUE_ALIASES.get(clean_value, clean_value)


def numeric_measure(value: str) -> str:
    match = re.search(r"\d+", normalize_text(value))
    return match.group(0) if match else normalize_text(value)


def pipe_values(section: BeautifulSoup | None) -> str:
    if not section:
        return ""
    return " | ".join(
        normalize_site_value(item.get_text(" ", strip=True)) for item in section.select(".skill-chips span")
    )


def positions_payload(soup: BeautifulSoup) -> dict[str, object]:
    details = section_details(soup, "Positions")
    primary = normalize_text(details.get("Primary Position", ""))
    full_positions, partial_positions = [], []
    for zone in soup.select(".position-pitch-zone"):
        classes = zone.get("class", [])
        position_class = next((item for item in classes if item.startswith("position-pitch-")), "")
        position = position_class.removeprefix("position-pitch-").upper()
        if position not in POSITION_CODES:
            continue
        if "is-full" in classes:
            full_positions.append(position)
        elif "is-partial" in classes:
            partial_positions.append(position)
    if not full_positions and primary:
        full_positions = [primary]
    playable = list(dict.fromkeys([*full_positions, *partial_positions]))
    payload: dict[str, object] = {
        "Position:": primary,
        "Strong Positions": " | ".join(POSITION_TRANSLATIONS.get(item, item) for item in full_positions),
        "Secondary Positions": " | ".join(POSITION_TRANSLATIONS.get(item, item) for item in partial_positions),
        "Playable Positions": " | ".join(POSITION_TRANSLATIONS.get(item, item) for item in playable),
    }
    for position in POSITION_CODES:
        payload[f"Pos_{position}"] = 2 if position in full_positions else (1 if position in partial_positions else 0)
    return payload


def parse_standard_player_detail(summary: dict) -> tuple[dict, dict]:
    session = build_session()
    response = request_with_retry(session, "GET", summary["url"])
    soup = BeautifulSoup(response.text, "html.parser")
    player_details = section_details(soup, "Player Details")
    card_type = normalize_text(player_details.get("Card Type", ""))
    if card_type != "Standard":
        raise RuntimeError(f"Expected Standard player {summary['pesdb_id']}, got {card_type or 'unknown'}")

    player: dict[str, object] = {
        "player_id": summary["pesdb_id"],
        "Player Name:": player_details.get("Player Name", summary.get("name", "")),
        "Team Name:": player_details.get("Club", ""),
        "League:": player_details.get("League", ""),
        "Nationality:": player_details.get("Nationality", ""),
        "Region:": player_details.get("Region", ""),
        "Height:": numeric_measure(player_details.get("Height", "")),
        "Weight:": numeric_measure(player_details.get("Weight", "")),
        "Age:": player_details.get("Age", ""),
        "Foot:": player_details.get("Stronger Foot", ""),
        "Overall Rating:": player_details.get("Overall Rating", summary.get("overall", "")),
        "Max Overall:": player_details.get("Max Overall", summary.get("max_overall", "")),
        "Card Type:": card_type,
    }
    player.update(positions_payload(soup))
    for row in soup.select(".ability-row"):
        label, value = row.find("span"), row.find("strong")
        if label and value:
            player[f"{normalize_text(label.get_text(' ', strip=True))}:"] = normalize_text(value.get_text(" ", strip=True))
    for section_name in ("Characteristics", "Player Model"):
        for label, value in section_details(soup, section_name).items():
            player[f"{label}:"] = value

    styles = []
    for row in soup.select(".playing-style-row > div"):
        label, value = row.find("span"), row.find("strong")
        if label and value:
            section = "Att" if "Attacking" in label.get_text() else "Def"
            styles.append(f"{section}:{normalize_site_value(value.get_text(' ', strip=True))}")
    player["Playing Style"] = " | ".join(styles)
    skills = {normalize_text(section.find("h2").get_text(" ", strip=True)): section for section in soup.select(".skills-grid section") if section.find("h2")}
    player["Player Skills"] = pipe_values(skills.get("Player Skills"))
    player["AI Playing Styles"] = pipe_values(skills.get("AI Playing Styles"))
    state = {
        "url": summary["url"],
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
    return player, state


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def final_player_id(player: dict) -> str:
    for key in ("ID Giocatore", "pesdb_id", "player_id"):
        value = str(player.get(key, "")).strip()
        if value:
            return value
    return ""


def load_previous_index() -> dict[str, dict]:
    return {player_id: player for player in load_json(PREVIOUS_DATA_FILE, []) if (player_id := final_player_id(player))}


def prepare(chunk_size: int = CHUNK_SIZE, max_pages: int | None = None) -> dict:
    players, pages = discover_standard_players(max_pages=max_pages)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for index, chunk in enumerate(split_into_chunks(players, chunk_size)):
        file_name = f"standard_chunk_{index:03d}.json"
        save_json(CHUNKS_DIR / file_name, chunk)
        manifest.append({"chunk_index": index, "file": file_name, "count": len(chunk)})
    save_json(OUTPUT_DIR / "standard_2027_manifest.json", manifest)
    save_json(OUTPUT_DIR / "standard_2027_pages.json", pages)
    summary = {"players": len(players), "pages": len(pages), "chunks": len(manifest), "chunk_size": chunk_size}
    save_json(OUTPUT_DIR / "standard_2027_prepare_summary.json", summary)
    print(json.dumps(summary))
    return summary


def process_chunk(chunk_index: int) -> dict:
    manifest = load_json(OUTPUT_DIR / "standard_2027_manifest.json", [])
    chunk_info = next(item for item in manifest if int(item["chunk_index"]) == chunk_index)
    summaries = load_json(CHUNKS_DIR / chunk_info["file"], [])
    state = load_json(STATE_FILE, {})
    previous = load_previous_index()
    scraped, cached, errors, state_updates = [], [], [], {}
    session = build_session()
    for offset, summary in enumerate(summaries, start=1):
        player_id = summary["pesdb_id"]
        prior_state = state.get(player_id, {})
        try:
            unchanged = False
            if not FORCE_FULL and prior_state and player_id in previous and prior_state.get("url") == summary["url"]:
                head = request_with_retry(session, "HEAD", summary["url"])
                etag = head.headers.get("ETag", "")
                last_modified = head.headers.get("Last-Modified", "")
                unchanged = (
                    etag == prior_state.get("etag")
                    if etag and prior_state.get("etag")
                    else bool(last_modified and last_modified == prior_state.get("last_modified"))
                )
                if unchanged:
                    cached.append(previous[player_id])
                    state_updates[player_id] = {**prior_state, "checked_at": datetime.now(timezone.utc).isoformat()}
            if not unchanged:
                player, player_state = parse_standard_player_detail(summary)
                scraped.append(player)
                state_updates[player_id] = player_state
                time.sleep(DETAIL_DELAY_SECONDS)
        except Exception as exc:
            errors.append({"player_id": player_id, "url": summary["url"], "error": str(exc)})
            if player_id in previous:
                cached.append(previous[player_id])
                if prior_state:
                    state_updates[player_id] = prior_state
        print(f"[CHUNK {chunk_index}] {offset}/{len(summaries)} {player_id}")
    payload = {"chunk_index": chunk_index, "requested": summaries, "scraped": scraped, "cached": cached, "errors": errors, "state": state_updates}
    save_json(CHUNKS_DIR / f"result_chunk_{chunk_index:03d}.json", payload)
    return {"chunk_index": chunk_index, "scraped": len(scraped), "cached": len(cached), "errors": len(errors)}


def merge() -> dict:
    manifest = load_json(OUTPUT_DIR / "standard_2027_manifest.json", [])
    if not manifest:
        raise RuntimeError("2027 manifest missing")
    raw_players, cached_players, all_ids, errors, state = [], [], [], [], {}
    for item in manifest:
        chunk_index = int(item["chunk_index"])
        payload = load_json(CHUNKS_DIR / f"result_chunk_{chunk_index:03d}.json", None)
        if payload is None:
            raise RuntimeError(f"Missing result for chunk {chunk_index}")
        raw_players.extend(payload["scraped"])
        cached_players.extend(payload["cached"])
        errors.extend(payload["errors"])
        state.update(payload["state"])
        all_ids.extend(entry["pesdb_id"] for entry in payload["requested"])

    custom_columns, custom_values, excluded = load_custom_rules()
    transformed = []
    if raw_players:
        raw_df = pd.DataFrame(raw_players)
        final_df = transform_dataframe(raw_df, set(DEFAULT_EXCLUDED_COLUMNS) | excluded, custom_columns, custom_values)
        transformed = json.loads(final_df.to_json(orient="records", force_ascii=False))
    final_index = {final_player_id(player): player for player in [*transformed, *cached_players] if final_player_id(player)}
    ordered_ids = list(dict.fromkeys(all_ids))
    final_players = [normalize_final_player_values(final_index[player_id], custom_values) for player_id in ordered_ids if player_id in final_index]
    if len(final_players) != len(ordered_ids):
        missing = len(ordered_ids) - len(final_players)
        raise RuntimeError(f"Quality gate failed: {missing} Standard players are missing")

    previous = load_json(PREVIOUS_DATA_FILE, [])
    final_df = pd.DataFrame(final_players)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "pesdb.net eFootball 2027",
        "scope": "Standard players only",
        "players_count": len(final_players),
        "player_ids_count": len(ordered_ids),
        "missing_players_count": 0,
        "scraped_players_count": len(raw_players),
        "cached_players_count": len(cached_players),
        "errors": errors,
        "columns": list(final_df.columns),
        "has_errors": bool(errors),
        **build_diff(previous, final_players),
    }
    save_json(OUTPUT_DIR / "pesdb_players_it.json", final_players)
    final_df.to_csv(OUTPUT_DIR / "pesdb_players_it.csv", index=False, encoding="utf-8-sig")
    save_json(OUTPUT_DIR / "pesdb_players_meta.json", metadata)
    save_json(OUTPUT_DIR / "pesdb_players_diff.json", build_diff(previous, final_players))
    save_json(OUTPUT_DIR / "pesdb_2027_state.json", state)
    print(json.dumps({"players": len(final_players), "scraped": len(raw_players), "cached": len(cached_players), "errors": len(errors)}))
    return metadata
