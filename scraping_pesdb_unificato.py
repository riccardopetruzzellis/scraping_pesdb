import argparse
import base64
import json
import os
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup


BASE_URL = "https://pesdb.net/efootball/"
START_PAGE = 1
END_PAGE = None
LIST_SLEEP_MIN = 1.0
LIST_SLEEP_MAX = 2.5
DETAIL_SLEEP_SECONDS = 4
SAVE_EVERY = 50
REQUEST_TIMEOUT = 20
MAX_EMPTY_PAGES = 2
CHUNK_SIZE = 200
LIST_RETRY_ATTEMPTS = 6
LIST_RETRY_BASE_SECONDS = 30
DETAIL_RETRY_ATTEMPTS = 4
DETAIL_RETRY_BASE_SECONDS = 8
FINAL_RECOVERY_SLEEP_SECONDS = 12
CHUNK_COOLDOWN_EVERY = 150
CHUNK_COOLDOWN_SECONDS = 90

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
MODIFICATIONS_FILE = Path(__file__).resolve().parent / "file_modifiche.xlsx"
MODIFICATIONS_SHEET = "Regole"
RAW_IDS_FILE = OUTPUT_DIR / "player_ids.txt"
RAW_CSV_FILE = OUTPUT_DIR / "pesdb_players_raw.csv"
FINAL_JSON_FILE = OUTPUT_DIR / "pesdb_players_it.json"
FINAL_CSV_FILE = OUTPUT_DIR / "pesdb_players_it.csv"
FINAL_META_FILE = OUTPUT_DIR / "pesdb_players_meta.json"
FINAL_DIFF_FILE = OUTPUT_DIR / "pesdb_players_diff.json"
PAGE_LOG_FILE = OUTPUT_DIR / "log_pagine.xlsx"
RUN_LOG_FILE = OUTPUT_DIR / "log_errori.txt"

DEFAULT_EXCLUDED_COLUMNS = {
    "",
    "Squad Number:",
    "Permalink:",
    "Forum code:",
    "Facebook:",
    "Twitter:",
}

COLUMN_TRANSLATIONS = {
    "player_id": "ID Giocatore",
    "Player Name:": "Nome Giocatore",
    "Team Name:": "Squadra",
    "League:": "Campionato",
    "Nationality:": "Nazionalita",
    "Region:": "Regione",
    "Height:": "Altezza",
    "Weight:": "Peso",
    "Age:": "Eta",
    "Foot:": "Piede",
    "Maximum Level:": "Livello Massimo",
    "Rating:": "Valutazione",
    "Position:": "Posizione",
    "Overall Rating:": "Overall",
    "Offensive Awareness:": "Consapevolezza Offensiva",
    "Ball Control:": "Controllo Palla",
    "Dribbling:": "Dribbling",
    "Tight Possession:": "Possesso Stretto",
    "Low Pass:": "Passaggio Rasoterra",
    "Lofted Pass:": "Passaggio Alto",
    "Finishing:": "Finalizzazione",
    "Heading:": "Colpo di Testa",
    "Set Piece Taking:": "Calci Piazzati",
    "Curl:": "Effetto",
    "Defensive Awareness:": "Consapevolezza Difensiva",
    "Tackling:": "Contrasto",
    "Aggression:": "Aggressivita",
    "Defensive Engagement:": "Coinvolgimento Difensivo",
    "GK Awareness:": "Portiere - Posizionamento",
    "GK Catching:": "Portiere - Presa",
    "GK Parrying:": "Portiere - Respinta",
    "GK Reflexes:": "Portiere - Riflessi",
    "GK Reach:": "Portiere - Copertura",
    "Speed:": "Velocita",
    "Acceleration:": "Accelerazione",
    "Kicking Power:": "Potenza Tiro",
    "Jumping:": "Elevazione",
    "Physical Contact:": "Contatto Fisico",
    "Balance:": "Equilibrio",
    "Stamina:": "Resistenza",
    "Weak Foot Usage:": "Uso Piede Debole",
    "Weak Foot Accuracy:": "Precisione Piede Debole",
    "Form:": "Forma",
    "Injury Resistance:": "Resistenza Infortuni",
    "Playing Style": "Stile di Gioco",
    "Player Skills": "Abilita Giocatore",
    "AI Playing Styles": "Stili IA",
    "Strong Positions": "ruoli_naturali",
    "Secondary Positions": "ruoli_secondari",
    "Playable Positions": "ruoli_utilizzabili",
    "Pos_GK": "pos_pt",
    "Pos_CB": "pos_dc",
    "Pos_LB": "pos_ts",
    "Pos_RB": "pos_td",
    "Pos_DMF": "pos_med",
    "Pos_CMF": "pos_cc",
    "Pos_LMF": "pos_cls",
    "Pos_RMF": "pos_cld",
    "Pos_AMF": "pos_trq",
    "Pos_LWF": "pos_esa",
    "Pos_RWF": "pos_eda",
    "Pos_SS": "pos_sp",
    "Pos_CF": "pos_p",
}

POSITION_CODES = [
    "GK",
    "CB",
    "LB",
    "RB",
    "DMF",
    "CMF",
    "LMF",
    "RMF",
    "AMF",
    "LWF",
    "RWF",
    "SS",
    "CF",
]

POSITION_TRANSLATIONS = {
    "GK": "PT",
    "CB": "DC",
    "LB": "TS",
    "RB": "TD",
    "DMF": "MED",
    "CMF": "CC",
    "LMF": "CLS",
    "RMF": "CLD",
    "AMF": "TRQ",
    "LWF": "ESA",
    "RWF": "EDA",
    "SS": "SP",
    "CF": "P",
}

VALUE_TRANSLATIONS = {
    "Right foot": "Destro",
    "Left foot": "Sinistro",
    "Almost Never": "Quasi Mai",
    "Rarely": "Raramente",
    "Occasionally": "Occasionalmente",
    "Standard": "Standard",
    "High": "Alta",
    "Low": "Bassa",
    "Medium": "Media",
    "C": "C",
    "B": "B",
    "A": "A",
    "D": "D",
    "E": "E",
    "CF": "Punta Centrale",
    "SS": "Seconda Punta",
    "LWF": "Ala Sinistra",
    "RWF": "Ala Destra",
    "AMF": "Trequartista",
    "CMF": "Centrocampista Centrale",
    "DMF": "Mediano",
    "LMF": "Esterno Sinistro",
    "RMF": "Esterno Destro",
    "LB": "Terzino Sinistro",
    "RB": "Terzino Destro",
    "CB": "Difensore Centrale",
    "GK": "Portiere",
    "Goal Poacher": "Rapace d'Area",
    "Fox in the Box": "Volpe d'Area",
    "Target Man": "Boa",
    "Deep-Lying Forward": "Falso Nove",
    "Hole Player": "Incursore",
    "Creative Playmaker": "Regista Creativo",
    "Orchestrator": "Regista",
    "Box-to-Box": "Box-to-Box",
    "Anchor Man": "Ancora",
    "The Destroyer": "Distruttore",
    "Build Up": "Impostatore",
    "Offensive Goalkeeper": "Portiere Offensivo",
    "Defensive Goalkeeper": "Portiere Difensivo",
    "Prolific Winger": "Ala Prolifica",
    "Roaming Flank": "Ala Mobile",
    "-": "",
}

LIST_VALUE_TRANSLATIONS = {
    "Heading": "Colpo di Testa",
    "First-time Shot": "Tiro di Prima",
    "Track Back": "Ripiegamento",
    "Aerial Superiority": "Superiorita Aerea",
    "Super-sub": "Super Riserva",
    "One-touch Pass": "Passaggio di Prima",
    "Through Passing": "Passaggio Filtrante",
    "Long-Range Shooting": "Tiro dalla Distanza",
    "Long-Range Curler": "Tiro a Giro da Lontano",
    "Acrobatic Finishing": "Finalizzazione Acrobatiche",
    "Gamesmanship": "Furbizia",
    "Captaincy": "Leadership",
    "Fighting Spirit": "Spirito Combattivo",
    "Flip Flap": "Flip Flap",
    "Marseille Turn": "Roulette",
    "Cut Behind & Turn": "Doppio Passo e Giro",
    "Sombrero": "Sombrero",
    "Pinpoint Crossing": "Cross Preciso",
    "Man Marking": "Marcatura Stretta",
    "Interception": "Intercettazione",
    "Blocker": "Muro Difensivo",
    "Sliding Tackle": "Scivolata",
    "Captaincy": "Leadership",
}

UNICODE_REPLACEMENTS = {
    "\u00a0": " ",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2013": "-",
    "\u2014": "-",
    "\u2026": "...",
}
def build_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session


def extract_ids_from_page(session, page_number):
    url = f"{BASE_URL}?page={page_number}"
    print(f"[LISTA] Pagina {page_number}")
    last_error = None
    response = None
    for attempt in range(1, LIST_RETRY_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            last_error = None
            break
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in {429, 500, 502, 503, 504}:
                raise
            retry_after = exc.response.headers.get("Retry-After") if exc.response is not None else None
        except requests.RequestException as exc:
            last_error = exc
            retry_after = None

        if attempt == LIST_RETRY_ATTEMPTS:
            break

        if retry_after and retry_after.isdigit():
            sleep_seconds = int(retry_after)
        else:
            sleep_seconds = LIST_RETRY_BASE_SECONDS * attempt + random.uniform(0, LIST_SLEEP_MAX)
        print(
            f"[RETRY] pagina {page_number} tentativo {attempt}/{LIST_RETRY_ATTEMPTS} fallito, "
            f"attendo {sleep_seconds:.1f}s"
        )
        time.sleep(sleep_seconds)

    if last_error is not None or response is None:
        raise last_error

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_="players")
    if not table:
        return [], False, 0

    player_ids = []
    rows = table.find_all("tr")[1:]
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 2:
            continue
        player_link = cols[1].find("a")
        if not player_link or "href" not in player_link.attrs:
            continue
        match = re.search(r"id=(\d+)", player_link["href"])
        if match:
            player_ids.append(match.group(1))

    return player_ids, True, len(player_ids)


def extract_position_map(soup):
    pitch = soup.find("div", class_="pitch")
    if not pitch:
        return {f"Pos_{position}": 0 for position in POSITION_CODES}

    strong_positions = []
    secondary_positions = []
    position_scores = {position: 0 for position in POSITION_CODES}
    for marker in pitch.find_all("div", recursive=False):
        classes = marker.get("class", [])
        position = next((item.upper() for item in classes if item not in {"pos1", "pos2"}), None)
        if not position or position not in position_scores:
            continue
        if "pos2" in classes:
            strong_positions.append(position)
            position_scores[position] = 2
        elif "pos1" in classes:
            secondary_positions.append(position)
            position_scores[position] = max(position_scores[position], 1)

    playable_positions = strong_positions + [
        position for position in secondary_positions if position not in strong_positions
    ]
    payload = {
        "Strong Positions": " | ".join(POSITION_TRANSLATIONS[position] for position in strong_positions),
        "Secondary Positions": " | ".join(POSITION_TRANSLATIONS[position] for position in secondary_positions),
        "Playable Positions": " | ".join(POSITION_TRANSLATIONS[position] for position in playable_positions),
    }
    payload.update({f"Pos_{position}": position_scores[position] for position in POSITION_CODES})
    return payload


def extract_all_player_ids(start_page, end_page=None, max_empty_pages=MAX_EMPTY_PAGES):
    all_ids = []
    page_logs = []
    current_page = start_page
    empty_pages_in_a_row = 0
    session = build_session()

    while end_page is None or current_page <= end_page:
        ids, table_found, rows = extract_ids_from_page(session, current_page)
        page_logs.append(
            {
                "Pagina": current_page,
                "Tabella trovata": table_found,
                "ID estratti": rows,
            }
        )

        if not table_found or rows == 0:
            empty_pages_in_a_row += 1
            print(f"[LISTA] Pagina senza giocatori ({empty_pages_in_a_row}/{max_empty_pages})")
            current_page += 1
            if empty_pages_in_a_row >= max_empty_pages:
                print("[LISTA] Raggiunta la fine delle pagine con giocatori")
                return list(dict.fromkeys(all_ids)), page_logs
            time.sleep(random.uniform(LIST_SLEEP_MIN, LIST_SLEEP_MAX))
            continue

        empty_pages_in_a_row = 0
        all_ids.extend(ids)
        current_page += 1
        time.sleep(random.uniform(LIST_SLEEP_MIN, LIST_SLEEP_MAX))

    unique_ids = list(dict.fromkeys(all_ids))
    return unique_ids, page_logs


def extract_player_details(session, player_id):
    url = f"{BASE_URL}?id={player_id}"
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    player_data = {"player_id": player_id}
    player_data.update(extract_position_map(soup))

    for table in soup.find_all("table"):
        if "playing_styles" in table.get("class", []):
            continue
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) != 2:
                continue
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            player_data[key] = value

    styles_table = soup.find("table", class_="playing_styles")
    if styles_table:
        current_section = None
        values_by_section = {}
        for row in styles_table.find_all("tr"):
            header = row.find("th")
            value_cell = row.find("td")
            if header:
                current_section = header.get_text(strip=True)
                values_by_section[current_section] = []
                continue
            if value_cell and current_section:
                values_by_section[current_section].append(value_cell.get_text(strip=True))

        for section, values in values_by_section.items():
            player_data[section] = " | ".join(values)

    return player_data


def extract_player_details_with_retry(session, player_id, max_attempts=DETAIL_RETRY_ATTEMPTS):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return extract_player_details(session, player_id)
        except requests.HTTPError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in {429, 500, 502, 503, 504}:
                raise
        except requests.RequestException as exc:
            last_error = exc

        if attempt == max_attempts:
            break

        sleep_seconds = DETAIL_RETRY_BASE_SECONDS * attempt
        print(f"[RETRY] player {player_id} tentativo {attempt}/{max_attempts} fallito, attendo {sleep_seconds}s")
        time.sleep(sleep_seconds)

    raise last_error


def translate_scalar(value):
    if pd.isna(value):
        return value
    clean_value = normalize_text(str(value))
    return VALUE_TRANSLATIONS.get(clean_value, clean_value)


def translate_pipe_list(value):
    if pd.isna(value):
        return value
    items = [normalize_text(item) for item in str(value).split("|")]
    translated = [LIST_VALUE_TRANSLATIONS.get(item, VALUE_TRANSLATIONS.get(item, item)) for item in items if item]
    return " | ".join(translated)


def normalize_text(value):
    text = str(value)
    for source, target in UNICODE_REPLACEMENTS.items():
        text = text.replace(source, target)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip()


def normalize_lookup_key(value):
    return re.sub(r"[\s_]+", "", normalize_text(value).lower())


def load_custom_rules():
    if not MODIFICATIONS_FILE.exists():
        return {}, {}, set()

    rules_df = pd.read_excel(MODIFICATIONS_FILE, sheet_name=MODIFICATIONS_SHEET, header=None)
    column_map = {}
    value_map = {}
    excluded_columns = set(DEFAULT_EXCLUDED_COLUMNS)

    for _, row in rules_df.iterrows():
        source_column = normalize_text(row.iloc[0]) if len(row) > 0 and pd.notna(row.iloc[0]) else ""
        target_column = normalize_text(row.iloc[1]) if len(row) > 1 and pd.notna(row.iloc[1]) else ""
        source_value = normalize_text(row.iloc[2]) if len(row) > 2 and pd.notna(row.iloc[2]) else ""
        target_value = normalize_text(row.iloc[3]) if len(row) > 3 and pd.notna(row.iloc[3]) else ""
        excluded = normalize_text(row.iloc[4]) if len(row) > 4 and pd.notna(row.iloc[4]) else ""

        if source_column and target_column:
            column_map[source_column] = target_column
        if source_value and target_value:
            value_map[normalize_lookup_key(source_value)] = target_value
        if excluded:
            excluded_columns.add(excluded)

    return column_map, value_map, excluded_columns


def translate_value(value, custom_translations):
    if pd.isna(value):
        return value
    normalized = normalize_text(value)
    return custom_translations.get(normalize_lookup_key(normalized), VALUE_TRANSLATIONS.get(normalized, normalized))


def split_player_skills(df):
    skill_column = next((col for col in df.columns if normalize_lookup_key(col) == "playerskills"), None)
    if not skill_column:
        return df

    skills_series = df[skill_column].fillna("").map(
        lambda value: [normalize_text(item) for item in str(value).split("|") if normalize_text(item)]
    )
    max_skills = skills_series.map(len).max()
    if not max_skills:
        return df

    insert_at = df.columns.get_loc(skill_column)
    for index in range(max_skills):
        df.insert(
            insert_at + index + 1,
            f"Player_Skills_{index + 1}",
            skills_series.map(lambda items: items[index] if index < len(items) else ""),
        )

    return df.drop(columns=[skill_column])


def transform_dataframe(df, excluded_columns, custom_column_names, custom_translations):
    df = df.copy()
    df.columns = [normalize_text(col) for col in df.columns]
    normalized_excluded_columns = {normalize_text(col) for col in excluded_columns}
    df = df.loc[:, [col for col in df.columns if col not in normalized_excluded_columns]]

    for column in df.columns:
        if column in {"Playing Style", "Position:", "Foot:", "Weak Foot Usage:", "Weak Foot Accuracy:", "Form:", "Rating:"}:
            df[column] = df[column].map(lambda value: translate_value(value, custom_translations) if pd.notna(value) else value)
        elif column in {"Player Skills", "AI Playing Styles"}:
            df[column] = df[column].map(
                lambda value: " | ".join(
                    translate_value(item, custom_translations) for item in translate_pipe_list(value).split(" | ")
                ).strip(" |")
                if pd.notna(value)
                else value
            )
        else:
            df[column] = df[column].map(
                lambda value: translate_value(value, custom_translations)
                if isinstance(value, str)
                else value
            )

    df = split_player_skills(df)
    df = df.rename(columns=lambda col: custom_column_names.get(normalize_text(col), COLUMN_TRANSLATIONS.get(col, col)))
    ordered_columns = []
    for source_column, translated_column in COLUMN_TRANSLATIONS.items():
        normalized_source = normalize_text(source_column)
        final_name = custom_column_names.get(normalized_source, translated_column)
        if final_name in df.columns and final_name not in ordered_columns:
            ordered_columns.append(final_name)
    for source_column, target_column in custom_column_names.items():
        if target_column in df.columns and target_column not in ordered_columns:
            ordered_columns.append(target_column)
    skill_columns = [col for col in df.columns if re.fullmatch(r"Player_Skills_\d+", col)]
    for skill_column in skill_columns:
        if skill_column not in ordered_columns:
            ordered_columns.append(skill_column)
    remaining_columns = [col for col in df.columns if col not in ordered_columns]
    df = df[ordered_columns + remaining_columns]
    return df


def write_text_file(path, lines):
    path.write_text("\n".join(lines), encoding="utf-8")


def append_run_log(message):
    RUN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def build_metadata(final_df, page_logs, player_ids):
    empty_by_column = {}
    for column in final_df.columns:
        series = final_df[column]
        empty_count = int(series.isna().sum())
        empty_count += int(series.map(lambda value: isinstance(value, str) and not value.strip()).sum())
        empty_by_column[column] = empty_count

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "players_count": int(len(final_df)),
        "player_ids_count": int(len(player_ids)),
        "missing_players_count": int(max(len(player_ids) - len(final_df), 0)),
        "pages_processed": int(len(page_logs)),
        "columns": list(final_df.columns),
        "empty_by_column": empty_by_column,
        "has_errors": RUN_LOG_FILE.exists() and RUN_LOG_FILE.stat().st_size > 0,
    }


def split_into_chunks(items, chunk_size=CHUNK_SIZE):
    return [items[index:index + chunk_size] for index in range(0, len(items), chunk_size)]


def save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def index_players_by_id(players):
    indexed = {}
    for player in players:
        player_id = str(player.get("pesdb_id") or player.get("player_id") or "").strip()
        if player_id:
            indexed[player_id] = player
    return indexed


def build_diff(previous_players, current_players):
    previous_index = index_players_by_id(previous_players)
    current_index = index_players_by_id(current_players)

    previous_ids = set(previous_index)
    current_ids = set(current_index)

    added_ids = sorted(current_ids - previous_ids)
    removed_ids = sorted(previous_ids - current_ids)
    common_ids = sorted(previous_ids & current_ids)

    changed_players = []
    for player_id in common_ids:
        old_player = previous_index[player_id]
        new_player = current_index[player_id]
        changed_fields = {}
        all_keys = sorted(set(old_player) | set(new_player))
        for key in all_keys:
            old_value = old_player.get(key)
            new_value = new_player.get(key)
            if old_value != new_value:
                changed_fields[key] = {"old": old_value, "new": new_value}
        if changed_fields:
            changed_players.append({"player_id": player_id, "changes": changed_fields})

    return {
        "added_players_count": len(added_ids),
        "removed_players_count": len(removed_ids),
        "changed_players_count": len(changed_players),
        "added_player_ids": added_ids,
        "removed_player_ids": removed_ids,
        "changed_players": changed_players,
    }


def get_github_file_sha(session, owner, repo, branch, path):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    response = session.get(url, params={"ref": branch}, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()["sha"]


def push_file_to_github(session, owner, repo, branch, local_path, repo_path, commit_message):
    sha = get_github_file_sha(session, owner, repo, branch, repo_path)
    content = base64.b64encode(local_path.read_bytes()).decode("ascii")
    payload = {
        "message": commit_message,
        "content": content,
        "branch": branch,
    }
    if sha:
        payload["sha"] = sha

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{repo_path}"
    response = session.put(url, json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()


def push_outputs_to_github():
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_BRANCH", "main")
    json_path = os.getenv("GITHUB_JSON_PATH", "data/pesdb_players_it.json")
    meta_path = os.getenv("GITHUB_META_PATH", "data/pesdb_players_meta.json")
    diff_path = os.getenv("GITHUB_DIFF_PATH", "data/pesdb_players_diff.json")
    csv_path = os.getenv("GITHUB_CSV_PATH", "data/pesdb_players_it.csv")

    if not token or not repo:
        print("[GITHUB] Push saltato: variabili GITHUB_TOKEN o GITHUB_REPOSITORY mancanti")
        return

    owner, repo_name = repo.split("/", 1)
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pesdb-render-scraper",
        }
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    extraction_stamp = datetime.now(timezone.utc).strftime("%d_%m_%Y")
    dated_json_path = f"data/estrazione_{extraction_stamp}.json"
    push_file_to_github(
        session,
        owner,
        repo_name,
        branch,
        FINAL_JSON_FILE,
        json_path,
        f"Update PESDB JSON - {timestamp}",
    )
    push_file_to_github(
        session,
        owner,
        repo_name,
        branch,
        FINAL_JSON_FILE,
        dated_json_path,
        f"Archive PESDB dated JSON - {timestamp}",
    )
    push_file_to_github(
        session,
        owner,
        repo_name,
        branch,
        FINAL_META_FILE,
        meta_path,
        f"Update PESDB metadata - {timestamp}",
    )
    push_file_to_github(
        session,
        owner,
        repo_name,
        branch,
        FINAL_DIFF_FILE,
        diff_path,
        f"Update PESDB diff - {timestamp}",
    )
    push_file_to_github(
        session,
        owner,
        repo_name,
        branch,
        FINAL_CSV_FILE,
        csv_path,
        f"Update PESDB CSV - {timestamp}",
    )
    print(f"[GITHUB] File aggiornati su {repo}@{branch}")


def recover_missing_players(player_ids):
    if not player_ids:
        return [], []

    session = build_session()
    recovered_players = []
    recovery_errors = []

    for index, player_id in enumerate(player_ids, start=1):
        print(f"[RECOVERY] {index}/{len(player_ids)} player {player_id}")
        try:
            recovered_players.append(extract_player_details_with_retry(session, player_id))
        except Exception as exc:
            recovery_errors.append({"player_id": player_id, "error": str(exc)})
        time.sleep(FINAL_RECOVERY_SLEEP_SECONDS)

    return recovered_players, recovery_errors


def run(start_page, end_page, excluded_columns):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_run_log(f"=== Avvio run {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    custom_column_names, custom_translations, file_excluded_columns = load_custom_rules()
    effective_excluded_columns = set(excluded_columns) | file_excluded_columns

    player_ids, page_logs = extract_all_player_ids(start_page, end_page)
    write_text_file(RAW_IDS_FILE, player_ids)
    pd.DataFrame(page_logs).to_excel(PAGE_LOG_FILE, index=False)
    print(f"[LISTA] ID unici trovati: {len(player_ids)}")

    session = build_session()

    all_players = []
    total = len(player_ids)
    for index, player_id in enumerate(player_ids, start=1):
        print(f"[DETTAGLIO] {index}/{total} player {player_id}")
        try:
            all_players.append(extract_player_details_with_retry(session, player_id))
        except Exception as exc:
            error_message = f"Player {player_id}: {exc}"
            print(f"[ERRORE] {error_message}")
            append_run_log(error_message)
            continue

        if index % SAVE_EVERY == 0:
            pd.DataFrame(all_players).to_csv(RAW_CSV_FILE, index=False, encoding="utf-8-sig")
            print(f"[DETTAGLIO] Checkpoint salvato a {index} giocatori")

        time.sleep(DETAIL_SLEEP_SECONDS)

    raw_df = pd.DataFrame(all_players)
    raw_df.to_csv(RAW_CSV_FILE, index=False, encoding="utf-8-sig")

    final_df = transform_dataframe(raw_df, effective_excluded_columns, custom_column_names, custom_translations)
    final_df.to_json(FINAL_JSON_FILE, orient="records", force_ascii=False)
    final_df.to_csv(FINAL_CSV_FILE, index=False, encoding="utf-8-sig")
    metadata = build_metadata(final_df, page_logs, player_ids)
    FINAL_META_FILE.write_text(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    push_outputs_to_github()

    append_run_log(f"=== Fine run {time.strftime('%Y-%m-%d %H:%M:%S')} - giocatori: {len(final_df)} ===")
    print(f"[FINE] Giocatori salvati: {len(final_df)}")
    print(f"[FINE] JSON finale: {FINAL_JSON_FILE}")
    print(f"[FINE] Metadata finale: {FINAL_META_FILE}")


def parse_args():
    parser = argparse.ArgumentParser(description="Scraping completo PESDB con output tradotto in italiano.")
    parser.add_argument("--start-page", type=int, default=START_PAGE, help="Prima pagina elenco da leggere.")
    parser.add_argument(
        "--end-page",
        type=int,
        default=END_PAGE,
        help="Ultima pagina elenco da leggere. Se omessa, continua fino all'ultima pagina con giocatori.",
    )
    parser.add_argument(
        "--include-column",
        action="append",
        default=[],
        help="Colonna inglese da mantenere anche se esclusa di default. Ripetibile.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    excluded_columns = set(DEFAULT_EXCLUDED_COLUMNS) - set(args.include_column)
    run(args.start_page, args.end_page, excluded_columns)
