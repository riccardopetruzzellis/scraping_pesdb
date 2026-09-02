"""Commands used by the staged GitHub Action for the PESDB 2027 scraper."""

import argparse

from scraping_pesdb_2027 import (
    CHUNK_SIZE,
    assemble_discovery,
    discover_range,
    merge,
    prepare,
    prepare_discovery_plan,
    process_chunk,
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
    else:
        merge()


if __name__ == "__main__":
    main()
