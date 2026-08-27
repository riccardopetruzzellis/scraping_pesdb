import argparse
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from scraping_pesdb_unificato import (
    CHUNK_SIZE,
    CHUNK_COOLDOWN_EVERY,
    CHUNK_COOLDOWN_SECONDS,
    DEFAULT_EXCLUDED_COLUMNS,
    FINAL_DIFF_FILE,
    FINAL_CSV_FILE,
    FINAL_JSON_FILE,
    FINAL_META_FILE,
    REQUEST_TIMEOUT,
    FAST_FAIL_RATE_LIMIT_IN_CHUNKS,
    OUTPUT_DIR,
    PAGE_LOG_FILE,
    RAW_IDS_FILE,
    build_diff,
    build_metadata,
    build_session,
    extract_all_player_ids,
    extract_player_details_with_retry_mode,
    load_custom_rules,
    load_json,
    recover_missing_players,
    save_json,
    split_into_chunks,
    transform_dataframe,
)
import time


CHUNKS_DIR = OUTPUT_DIR / "chunks"
MERGED_DIR = OUTPUT_DIR / "merged"
MAX_PLAYER_COUNT_DROP_RATIO = float(os.getenv("MAX_PLAYER_COUNT_DROP_RATIO", "0.005"))


def github_request_session():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pesdb-github-actions",
        }
    )
    return session


def fetch_previous_repo_json(repo_path):
    local_path = Path(repo_path)
    if local_path.exists():
        content = local_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            print(f"[DIFF] Snapshot locale precedente non valido in {repo_path}, confronto remoto tentato")
        else:
            return parsed if isinstance(parsed, list) else []

    repo = os.getenv("GITHUB_REPOSITORY")
    branch = os.getenv("GITHUB_BRANCH", "main")
    session = github_request_session()
    if not repo or not session:
        return []
    owner, repo_name = repo.split("/", 1)
    url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{repo_path}"
    response = session.get(url, params={"ref": branch}, timeout=REQUEST_TIMEOUT)
    if response.status_code == 404:
        return []
    response.raise_for_status()
    payload = response.json()
    content = base64.b64decode(payload["content"]).decode("utf-8")
    content = content.strip()
    if not content:
        return []
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        print(f"[DIFF] Snapshot precedente non valido in {repo_path}, confronto saltato")
        return []
    return parsed if isinstance(parsed, list) else []


def prepare(end_page, chunk_size):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    player_ids, page_logs = extract_all_player_ids(1, end_page)
    RAW_IDS_FILE.write_text("\n".join(player_ids), encoding="utf-8")
    pd.DataFrame(page_logs).to_excel(PAGE_LOG_FILE, index=False)

    chunk_map = []
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    for index, chunk_ids in enumerate(split_into_chunks(player_ids, chunk_size)):
        chunk_file = CHUNKS_DIR / f"ids_chunk_{index:03d}.json"
        save_json(chunk_file, chunk_ids)
        chunk_map.append({"chunk_index": index, "ids_file": chunk_file.name, "count": len(chunk_ids)})

    save_json(OUTPUT_DIR / "chunks_manifest.json", chunk_map)
    print(json.dumps({"chunks": chunk_map, "count": len(chunk_map)}))


def process_chunk(chunk_index):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = load_json(OUTPUT_DIR / "chunks_manifest.json", [])
    chunk_info = next(item for item in manifest if item["chunk_index"] == chunk_index)
    chunk_ids = load_json(CHUNKS_DIR / chunk_info["ids_file"], [])

    session = build_session()
    players = []
    errors = []
    for idx, player_id in enumerate(chunk_ids, start=1):
        if idx > 1 and (idx - 1) % CHUNK_COOLDOWN_EVERY == 0:
            print(f"[CHUNK {chunk_index}] cooldown dopo {idx - 1} player, attendo {CHUNK_COOLDOWN_SECONDS}s e resetto la sessione")
            time.sleep(CHUNK_COOLDOWN_SECONDS)
            session = build_session()
        print(f"[CHUNK {chunk_index}] {idx}/{len(chunk_ids)} player {player_id}")
        try:
            players.append(
                extract_player_details_with_retry_mode(
                    session,
                    player_id,
                    fast_fail_rate_limit=FAST_FAIL_RATE_LIMIT_IN_CHUNKS,
                )
            )
        except Exception as exc:
            errors.append({"player_id": player_id, "error": str(exc)})

    chunk_payload = {
        "chunk_index": chunk_index,
        "players": players,
        "errors": errors,
        "requested_ids": chunk_ids,
    }
    save_json(CHUNKS_DIR / f"players_chunk_{chunk_index:03d}.json", chunk_payload)


def validate_quality_gate(final_df, all_ids, previous_players):
    current_count = len(final_df)
    expected_count = len(set(str(player_id) for player_id in all_ids))
    previous_count = len(previous_players)
    if expected_count and current_count < expected_count:
        raise RuntimeError(
            f"Giocatori mancanti nel merge: estratti {current_count} su {expected_count} ID attesi"
        )
    if previous_count:
        max_drop = max(1, int(previous_count * MAX_PLAYER_COUNT_DROP_RATIO))
        dropped = previous_count - current_count
        if dropped > max_drop:
            raise RuntimeError(
                "Estrazione sotto soglia qualità: "
                f"{current_count} giocatori contro {previous_count} precedenti "
                f"(drop {dropped}, massimo consentito {max_drop})."
            )
    return {
        "previous_players_count": previous_count,
        "quality_expected_player_ids": expected_count,
        "quality_max_drop_ratio": MAX_PLAYER_COUNT_DROP_RATIO,
    }


def merge(push_to_github):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    custom_column_names, custom_translations, file_excluded_columns = load_custom_rules()
    effective_excluded_columns = set(DEFAULT_EXCLUDED_COLUMNS) | file_excluded_columns
    manifest = load_json(OUTPUT_DIR / "chunks_manifest.json", [])
    if not manifest:
        raise RuntimeError("chunks_manifest.json non trovato o vuoto")

    merged_players = []
    merged_errors = []
    all_ids = []
    failed_player_ids = []
    missing_chunks = []
    for item in manifest:
        chunk_file = CHUNKS_DIR / f"players_chunk_{item['chunk_index']:03d}.json"
        if not chunk_file.exists():
            missing_chunks.append(chunk_file.name)
            continue
        chunk_payload = load_json(chunk_file, {})
        merged_players.extend(chunk_payload.get("players", []))
        merged_errors.extend(chunk_payload.get("errors", []))
        all_ids.extend(chunk_payload.get("requested_ids", []))
        failed_player_ids.extend(error["player_id"] for error in chunk_payload.get("errors", []))

    if missing_chunks:
        raise RuntimeError(f"Chunk mancanti nel merge: {len(missing_chunks)}. Esempi: {missing_chunks[:5]}")
    if not merged_players:
        raise RuntimeError("Nessun giocatore trovato nei chunk elaborati")

    if failed_player_ids:
        print(f"[RECOVERY] Avvio recupero finale per {len(failed_player_ids)} player falliti nei chunk")
        recovered_players, recovery_errors = recover_missing_players(failed_player_ids)
        merged_players.extend(recovered_players)
        merged_errors.extend(recovery_errors)

    unique_players = {}
    for player in merged_players:
        unique_players[str(player.get("player_id"))] = player
    merged_players = list(unique_players.values())

    raw_df = pd.DataFrame(merged_players)
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    raw_df.to_csv(MERGED_DIR / "pesdb_players_raw.csv", index=False, encoding="utf-8-sig")

    final_df = transform_dataframe(raw_df, effective_excluded_columns, custom_column_names, custom_translations)
    final_df.to_json(FINAL_JSON_FILE, orient="records", force_ascii=False)
    final_df.to_csv(FINAL_CSV_FILE, index=False, encoding="utf-8-sig")
    current_players = json.loads(FINAL_JSON_FILE.read_text(encoding="utf-8"))
    previous_players = fetch_previous_repo_json(os.getenv("GITHUB_JSON_PATH", "data/pesdb_players_it.json"))
    quality_payload = validate_quality_gate(final_df, all_ids, previous_players)
    diff_payload = build_diff(previous_players, current_players)
    FINAL_DIFF_FILE.write_text(json.dumps(diff_payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    metadata = build_metadata(final_df, [], all_ids)
    metadata["chunk_count"] = len(manifest)
    metadata["errors"] = merged_errors
    metadata["expected_player_ids"] = len(all_ids)
    metadata["extracted_players"] = len(final_df)
    metadata["missing_players_count"] = max(len(all_ids) - len(final_df), 0)
    metadata.update(
        {
            "added_players_count": diff_payload["added_players_count"],
            "removed_players_count": diff_payload["removed_players_count"],
            "changed_players_count": diff_payload["changed_players_count"],
            **quality_payload,
        }
    )
    FINAL_META_FILE.write_text(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    if push_to_github:
        from scraping_pesdb_unificato import push_outputs_to_github

        push_outputs_to_github()


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--end-page", type=int, default=None)
    prepare_parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)

    chunk_parser = subparsers.add_parser("process-chunk")
    chunk_parser.add_argument("--chunk-index", type=int, required=True)

    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--push-to-github", action="store_true")

    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.end_page, args.chunk_size)
    elif args.command == "process-chunk":
        process_chunk(args.chunk_index)
    elif args.command == "merge":
        merge(args.push_to_github)


if __name__ == "__main__":
    main()
