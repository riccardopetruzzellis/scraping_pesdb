import json
import unittest
from unittest.mock import patch

import pandas as pd
from bs4 import BeautifulSoup

import scraping_pesdb_2027 as scraper


class PlayerSkillsTests(unittest.TestCase):
    def extract(self, html):
        return scraper.extract_skill_lists(BeautifulSoup(html, "html.parser"))

    def test_structured_data(self):
        data = {"compare": {"playerSkills": ["Double Touch", "Through Passing"], "aiPlayingStyles": ["Mazing Run"]}}
        result = self.extract('<script id="player-progression-data" type="application/json">' + json.dumps(data) + '</script>')
        self.assertEqual(result["Player Skills"], "Double Touch | Through Passing")
        self.assertEqual(result["AI Playing Styles"], "Mazing Run")

    def test_current_links_and_legacy_spans(self):
        for tag in ("a", "span"):
            html = ''.join(f'<section><h2>{title}</h2><div class="skill-chips"><{tag}>{value}</{tag}></div></section>'
                           for title, value in (("Player Skills", "Double Touch"), ("AI Playing Styles", "Mazing Run")))
            self.assertEqual(self.extract(html)["Player Skills"], "Double Touch")

    def test_explicit_empty_arrays(self):
        data = {"compare": {"playerSkills": [], "aiPlayingStyles": []}}
        result = self.extract('<script id="player-progression-data">' + json.dumps(data) + '</script>')
        self.assertEqual(result, {"Player Skills": "", "AI Playing Styles": ""})

    def test_missing_markup_fails(self):
        with self.assertRaises(RuntimeError):
            self.extract('<h2>Player Skills</h2>')

    def test_invalid_structured_values_fail(self):
        for value in (None, "Double Touch", [None], [""]):
            with self.assertRaises(RuntimeError):
                self.extract('<script id="player-progression-data">' + json.dumps({"compare": {"playerSkills": value}}) + '</script>')

    def test_export_retains_all_skills(self):
        columns, values, excluded = scraper.load_custom_rules()
        frame = scraper.transform_dataframe(pd.DataFrame([{"player_id": "16895490", "Player Skills": "Double Touch | Through Passing"}]),
                                            set(scraper.DEFAULT_EXCLUDED_COLUMNS) | excluded, columns, values)
        row = frame.to_dict("records")[0]
        skills = [value for key, value in row.items() if "skills" in key.lower()]
        self.assertEqual(len(skills), 2)
        self.assertTrue(all(skills))

    def test_obsolete_cache_not_used_after_error(self):
        summary = {"pesdb_id": "16895490", "url": "https://example.test/player"}
        def fake_load(path, default):
            if path == scraper.STATE_FILE:
                return {"16895490": {"url": summary["url"]}}
            if path.name == "standard_2027_manifest.json":
                return [{"chunk_index": 0, "file": "chunk.json"}]
            return [summary]
        with patch.object(scraper, "load_json", side_effect=fake_load), \
             patch.object(scraper, "load_previous_index", return_value={"16895490": {"player_skills_1": ""}}), \
             patch.object(scraper, "parse_standard_player_detail", side_effect=RuntimeError("missing skills")), \
             patch.object(scraper, "save_json") as save:
            result = scraper.process_chunk(0)
        self.assertEqual(result["cached"], 0)
        self.assertEqual(result["errors"], 1)
        self.assertEqual(save.call_args.args[1]["cached"], [])


if __name__ == "__main__":
    unittest.main()
