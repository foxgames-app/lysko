#!/usr/bin/env python3
"""Tests for tools/apps_catalog.py: python3 tools/test_apps_catalog.py"""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apps_catalog as ac  # noqa: E402

with open(os.path.join(ac.ROOT, "apps.json"), encoding="utf-8") as f:
    DOC = json.load(f)


class CatalogTest(unittest.TestCase):
    def bad(self, mutate):
        d = copy.deepcopy(DOC)
        mutate(d)
        self.assertTrue(ac.validate(d), "expected a validation error")

    def test_live_file_valid(self):
        self.assertEqual(ac.validate(DOC), [])

    def test_html_up_to_date(self):
        with open(os.path.join(ac.ROOT, "apps.html"), encoding="utf-8") as f:
            self.assertEqual(f.read(), ac.render(DOC))

    def test_schema(self):
        self.bad(lambda d: d.update(schema=2))

    def test_icon_host(self):
        self.bad(lambda d: d["apps"][0].update(icon="https://evil.example/x.png"))

    def test_store_url_must_match_package(self):
        self.bad(lambda d: d["apps"][0]["android"].update(url="https://play.google.com/store/apps/details?id=other.app"))

    def test_ios_url(self):
        self.bad(lambda d: d["apps"][0].update(ios={"id": "123456", "url": "http://apps.apple.com/app/id123456"}))

    def test_missing_language(self):
        self.bad(lambda d: d["apps"][0]["name"].pop("pt"))

    def test_html_in_text(self):
        self.bad(lambda d: d["apps"][0]["text"].update(en="<script>"))

    def test_published_needs_link(self):
        self.bad(lambda d: d["apps"][0].update(android=None, ios=None))

    def test_duplicate_id(self):
        self.bad(lambda d: d["apps"].append(copy.deepcopy(d["apps"][0])))

    def test_unknown_key(self):
        self.bad(lambda d: d["apps"][0].update(tracking="x"))


if __name__ == "__main__":
    unittest.main()
