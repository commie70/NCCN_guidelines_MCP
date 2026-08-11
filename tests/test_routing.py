from __future__ import annotations

import tempfile
import unittest

from nccn_guidelines.routing import RoutingError, Settings, select_source


class RoutingTests(unittest.TestCase):
    def settings(self, global_complete: bool) -> Settings:
        env = {"NCCN_DATA_DIR": tempfile.mkdtemp()}
        if global_complete:
            env.update({"NCCN_GLOBAL_USERNAME": "u", "NCCN_GLOBAL_PASSWORD": "p"})
        return Settings.from_env(env)

    def test_auto_table(self) -> None:
        self.assertEqual(select_source("en", "auto", self.settings(True)).source, "global")
        self.assertEqual(select_source("en", "auto", self.settings(False)).source, "china")
        for configured in (True, False):
            for language in ("zh", "paired"):
                self.assertEqual(select_source(language, "auto", self.settings(configured)).source, "china")

    def test_explicit_source_and_invalid_global_language(self) -> None:
        settings = self.settings(False)
        self.assertEqual(select_source("en", "china", settings).source, "china")
        self.assertEqual(select_source("en", "global", settings).source, "global")
        for language in ("zh", "paired"):
            with self.assertRaises(RoutingError):
                select_source(language, "global", settings)

    def test_new_global_names_do_not_mix_with_legacy_aliases(self) -> None:
        settings = Settings.from_env(
            {
                "NCCN_DATA_DIR": tempfile.mkdtemp(),
                "NCCN_GLOBAL_USERNAME": "new-only",
                "NCCN_PASSWORD": "legacy-password",
            }
        )
        self.assertFalse(settings.global_credentials.complete)
        self.assertEqual(settings.global_credentials.missing, ["NCCN_GLOBAL_PASSWORD"])

    def test_explicit_session_cookie_counts_as_configured_authentication(self) -> None:
        settings = Settings.from_env({"NCCN_DATA_DIR": tempfile.mkdtemp(), "NCCN_CHINA_SESSION_COOKIE": "fixture-cookie"})
        self.assertTrue(settings.authentication_configured("china"))
        self.assertFalse(settings.china_credentials.complete)

    def test_global_session_cookie_selects_global_for_auto_english(self) -> None:
        settings = Settings.from_env({"NCCN_DATA_DIR": tempfile.mkdtemp(), "NCCN_GLOBAL_SESSION_COOKIE": "fixture-cookie"})
        self.assertEqual(select_source("en", "auto", settings).source, "global")
