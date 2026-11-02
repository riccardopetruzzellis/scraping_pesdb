"""Tests for the PESDB catalogue switch (standard vs Serie A authentic).

Run with: python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scraping_pesdb_2027 as scraper  # noqa: E402


def built_list_url(page: int) -> str:
    request = requests.Request("GET", scraper.PLAYERS_URL, params=scraper.CATALOG.list_query(page))
    return request.prepare().url


class CatalogSwitchTest(unittest.TestCase):
    def tearDown(self) -> None:
        scraper.configure_catalog("standard")

    def test_standard_keeps_historical_paths(self) -> None:
        config = scraper.configure_catalog("standard")
        self.assertEqual(scraper.PLAYERS_URL, "https://pesdb.net/efootball/players/")
        self.assertEqual(built_list_url(3), "https://pesdb.net/efootball/players/?availability=standard&page=3")
        self.assertEqual(scraper.STATE_FILE, ROOT / "data" / "pesdb_2027_state.json")
        self.assertEqual(scraper.PREVIOUS_DATA_FILE, ROOT / "data" / "pesdb_players_it.json")
        self.assertEqual(scraper.CHUNKS_DIR, ROOT / "output" / "chunks_2027")
        self.assertEqual(scraper.POSITION_REPAIR_DIR, ROOT / "output" / "position_repair_2027")
        self.assertEqual(config.output_file("it.json"), ROOT / "output" / "pesdb_players_it.json")
        self.assertEqual(config.output_file("meta.json"), ROOT / "output" / "pesdb_players_meta.json")
        self.assertEqual(config.work_file("manifest.json"), ROOT / "output" / "standard_2027_manifest.json")
        self.assertEqual(config.scope, "Standard players only")

    def test_authentic_urls_and_files(self) -> None:
        config = scraper.configure_catalog("authentic")
        self.assertEqual(scraper.PLAYERS_URL, "https://pesdb.net/efootball/authentic/players/")
        self.assertEqual(
            built_list_url(1),
            "https://pesdb.net/efootball/authentic/players/?availability=standard&league%5B%5D=10&page=1",
        )
        self.assertEqual(scraper.STATE_FILE, ROOT / "data" / "pesdb_authentic_state.json")
        self.assertEqual(scraper.PREVIOUS_DATA_FILE, ROOT / "data" / "pesdb_authentic_it.json")
        self.assertEqual(scraper.CHUNKS_DIR, ROOT / "output" / "chunks_authentic_2027")
        self.assertEqual(config.output_file("it.csv"), ROOT / "output" / "pesdb_authentic_it.csv")
        self.assertEqual(config.output_file("diff.json"), ROOT / "output" / "pesdb_authentic_diff.json")
        self.assertEqual(config.work_file("manifest.json"), ROOT / "output" / "authentic_2027_manifest.json")

    def test_catalog_name_is_validated(self) -> None:
        self.assertIs(scraper.get_catalog_config(None), scraper.CATALOGS["standard"])
        self.assertIs(scraper.get_catalog_config(" Authentic "), scraper.CATALOGS["authentic"])
        with self.assertRaises(ValueError):
            scraper.get_catalog_config("featured")

    def test_authentic_detail_url_keeps_player_id(self) -> None:
        url = "https://pesdb.net/efootball/authentic/players/franck-kessie-107935"
        self.assertEqual(scraper.player_id_from_url(url), "107935")

    def test_catalog_fields_only_for_authentic(self) -> None:
        player = {"pesdb_id": "107935", "name": "Franck Kessié"}
        scraper.configure_catalog("standard")
        self.assertEqual(scraper.add_catalog_fields(player), player)
        scraper.configure_catalog("authentic")
        enriched = scraper.add_catalog_fields(player)
        self.assertEqual(enriched["catalog"], "authentic")
        self.assertEqual(enriched["card_image_url"], "https://pesdb.net/assets/img/card/f107935authentic.png")
        self.assertEqual(list(enriched)[:2], ["pesdb_id", "name"])

    def test_position_repair_url(self) -> None:
        scraper.configure_catalog("standard")
        self.assertEqual(scraper.position_repair_url("123"), "https://pesdb.net/efootball/?id=123")
        scraper.configure_catalog("authentic")
        state = {"123": {"url": "https://pesdb.net/efootball/authentic/players/x-123"}}
        self.assertEqual(scraper.position_repair_url("123", state), state["123"]["url"])
        with self.assertRaises(RuntimeError):
            scraper.position_repair_url("456", state)


if __name__ == "__main__":
    unittest.main()
