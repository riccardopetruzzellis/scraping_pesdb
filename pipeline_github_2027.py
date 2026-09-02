"""Commands used by the staged GitHub Action for the PESDB 2027 scraper."""

import argparse

from scraping_pesdb_2027 import CHUNK_SIZE, merge, prepare, process_chunk


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    prepare_parser.add_argument("--max-pages", type=int)
    chunk_parser = commands.add_parser("process-chunk")
    chunk_parser.add_argument("--chunk-index", type=int, required=True)
    commands.add_parser("merge")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(chunk_size=args.chunk_size, max_pages=args.max_pages)
    elif args.command == "process-chunk":
        process_chunk(args.chunk_index)
    else:
        merge()


if __name__ == "__main__":
    main()
