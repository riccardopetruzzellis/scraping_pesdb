"""Commands used by the staged GitHub Action for the PESDB 2027 scraper."""

import argparse
from pathlib import Path

from scraping_pesdb_2027 import (
    CHUNK_SIZE,
    assemble_discovery,
    discover_range,
    merge,
    prepare,
    prepare_discovery_plan,
    prepare_position_repair,
    process_position_repair_chunk,
    process_chunk,
    merge_position_repair,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    prepare_parser.add_argument("--max-pages", type=int)
    plan_parser = commands.add_parser("prepare-discovery-plan")
    plan_parser.add_argument("--pages-per-shard", type=int, required=True)
    plan_parser.add_argument("--max-pages", type=int)
    range_parser = commands.add_parser("discover-range")
    range_parser.add_argument("--start-page", type=int, required=True)
    range_parser.add_argument("--end-page", type=int, required=True)
    assemble_parser = commands.add_parser("assemble-discovery")
    assemble_parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    chunk_parser = commands.add_parser("process-chunk")
    chunk_parser.add_argument("--chunk-index", type=int, required=True)
    commands.add_parser("merge")
    repair_prepare_parser = commands.add_parser("prepare-position-repair")
    repair_prepare_parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    repair_prepare_parser.add_argument("--input", type=Path)
    repair_prepare_parser.add_argument("--player-limit", type=int)
    repair_chunk_parser = commands.add_parser("process-position-repair-chunk")
    repair_chunk_parser.add_argument("--chunk-index", type=int, required=True)
    repair_merge_parser = commands.add_parser("merge-position-repair")
    repair_merge_parser.add_argument("--input", type=Path)
    repair_merge_parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(chunk_size=args.chunk_size, max_pages=args.max_pages)
    elif args.command == "prepare-discovery-plan":
        prepare_discovery_plan(pages_per_shard=args.pages_per_shard, max_pages=args.max_pages)
    elif args.command == "discover-range":
        discover_range(start_page=args.start_page, end_page=args.end_page)
    elif args.command == "assemble-discovery":
        assemble_discovery(chunk_size=args.chunk_size)
    elif args.command == "process-chunk":
        process_chunk(args.chunk_index)
    elif args.command == "prepare-position-repair":
        kwargs = {"chunk_size": args.chunk_size, "player_limit": args.player_limit}
        if args.input:
            kwargs["input_file"] = args.input
        prepare_position_repair(**kwargs)
    elif args.command == "process-position-repair-chunk":
        process_position_repair_chunk(args.chunk_index)
    elif args.command == "merge-position-repair":
        kwargs = {}
        if args.input:
            kwargs["input_file"] = args.input
        if args.output:
            kwargs["output_file"] = args.output
        merge_position_repair(**kwargs)
    else:
        merge()


if __name__ == "__main__":
    main()
