import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_api", ROOT / "tools" / "build-api.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class HistoryOperationsTest(unittest.TestCase):
    def test_missing_key_inherits(self):
        card = {"releasedAt": "2017-04-07", "cost": 3, "attack": 1, "patches": [
            {"date": "2020-01-01", "changes": {"attack": 4}}
        ]}
        current = {}
        revisions, blocked, incomplete = BUILD.publish_forward_card(card, current, "TEST")
        self.assertEqual(current, {"cost": 3, "attack": 4})
        self.assertEqual(blocked, [])

    def test_falsy_and_empty_values_are_assignments(self):
        values = {"cost": 0, "collectible": False, "text": None, "race": "", "races": []}
        card = {"releasedAt": "2017-04-07", "patches": [
            {"date": "2020-01-01", "changes": values}
        ]}
        current = {}
        BUILD.publish_forward_card(card, current, "TEST")
        self.assertEqual(current, values)

    def test_patch_boundary_before_and_on_date(self):
        card = {"releasedAt": "2017-04-07", "cost": 2, "patches": [
            {"date": "2020-01-01", "changes": {"cost": 3}}
        ]}
        current = {}
        revisions, blocked, incomplete = BUILD.publish_forward_card(card, current, "TEST")
        self.assertEqual(current["cost"], 3)  # on 2020-01-01
        self.assertEqual(revisions[0]["from"], "2017-04-07")
        self.assertEqual(revisions[0]["before"], "2020-01-01")
        self.assertEqual(revisions[0]["changes"]["cost"], 2)  # immediately before

    def test_remove_is_distinct_and_reverse_compatible(self):
        card = {"releasedAt": "2017-04-07", "cost": 2, "patches": [
            {"date": "2020-01-01", "changes": {}, "remove": ["cost"]}
        ]}
        current = {}
        revisions, blocked, incomplete = BUILD.publish_forward_card(card, current, "TEST")
        self.assertNotIn("cost", current)
        self.assertEqual(blocked, [])
        self.assertEqual(revisions[0]["changes"]["cost"], 2)

    def test_new_field_does_not_drop_other_field_history(self):
        card = {"releasedAt": "2017-04-07", "cost": 2, "patches": [
            {"date": "2020-04-21", "changes": {"cost": 4}},
            {"date": "2021-03-26", "changes": {"spellSchool": "SHADOW"}}
        ]}
        current = {}
        revisions, blocked, incomplete = BUILD.publish_forward_card(card, current, "TEST")
        self.assertEqual(current, {"cost": 4, "spellSchool": "SHADOW"})
        self.assertEqual(revisions[0]["before"], "2020-04-21")
        self.assertEqual(revisions[0]["changes"]["cost"], 2)
        self.assertEqual(revisions[0]["incompleteFields"], ["spellSchool"])
        self.assertEqual(len(revisions), 1)
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0], {"date": "2021-03-26", "fields": ["spellSchool"]})

    def test_conflicting_operations_rejected(self):
        card = {"releasedAt": "2017-04-07", "patches": [
            {"date": "2020-01-01", "changes": {"cost": 0}, "remove": ["cost"]}
        ]}
        with self.assertRaises(ValueError):
            BUILD.read_patches(card, "TEST")

    def test_remove_absent_field_rejected(self):
        card = {"releasedAt": "2017-04-07", "patches": [
            {"date": "2020-01-01", "changes": {}, "remove": ["cost"]}
        ]}
        with self.assertRaises(ValueError):
            BUILD.publish_forward_card(card, {}, "TEST")

    def test_display_linebreaks_do_not_touch_raw_text(self):
        card = {"text": "first\\nsecond", "nativeRawText": "first\\nsecond", "patches": []}
        BUILD.normalize_card_display("TEST", card)
        self.assertEqual(card["text"], "first<br></br>second")
        self.assertEqual(card["nativeRawText"], "first\\nsecond")

    def test_type_inapplicable_zero_placeholders_are_ignored_in_history(self):
        cache = {"type": "SPELL", "cost": 2, "attack": 0, "health": 0,
                 "armor": 0, "durability": 0, "race": "", "races": [],
                 "spellSchool": ""}
        self.assertEqual(BUILD.normalize_history_cache(cache), {"type": "SPELL", "cost": 2})

    def test_date_keyed_source_normalizes_without_losing_current_cache(self):
        data = {
            "schemaVersion": 2, "id": "UNG_832", "dbfId": 41872,
            "current": {"cost": 4, "spellSchool": "SHADOW"},
            "2017-04-04": {"cost": 2, "nativeTags": [{"id": 48, "value": 2}]},
            "2020-04-21": {"cost": 4},
            "2021-03-26": {"spellSchool": "SHADOW"},
        }
        card = BUILD.normalize_date_keyed_source(data, {"id": "UNG_832", "releasedAt": "2017-04-07"})
        self.assertEqual(card["cost"], 2)
        self.assertEqual(card["patches"][0]["changes"]["cost"], 4)
        self.assertEqual(card["currentCache"]["cost"], 4)
        self.assertEqual(card["patches"][1]["changes"]["spellSchool"], "SHADOW")

    def test_known_grammar_correction_has_no_patch_date(self):
        self.assertEqual(BUILD.normalize_display_text("UNG_063", "+1/+1를 얻습니다."), "+1/+1을 얻습니다.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
