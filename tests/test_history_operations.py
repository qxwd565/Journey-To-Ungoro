import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_api", ROOT / "tools" / "build-api.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class HistoryOperationsTest(unittest.TestCase):
    def test_missing_key_inherits(self):
        card = {"releasedAt": "2017-04-07", "cost": 3, "patches": [
            {"date": "2020-01-01", "changes": {"attack": 4}}
        ]}
        current = {}
        revisions, blocked = BUILD.publish_forward_card(card, current, "TEST")
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

    def test_remove_is_distinct_and_reverse_compatible(self):
        card = {"releasedAt": "2017-04-07", "cost": 2, "patches": [
            {"date": "2020-01-01", "changes": {}, "remove": ["cost"]}
        ]}
        current = {}
        revisions, blocked = BUILD.publish_forward_card(card, current, "TEST")
        self.assertNotIn("cost", current)
        self.assertEqual(blocked, [])
        self.assertEqual(revisions[0]["changes"]["cost"], 2)

    def test_new_field_blocks_legacy_reverse_projection(self):
        card = {"releasedAt": "2017-04-07", "patches": [
            {"date": "2020-01-01", "changes": {"spellSchool": "FIRE"}}
        ]}
        current = {}
        revisions, blocked = BUILD.publish_forward_card(card, current, "TEST")
        self.assertEqual(current["spellSchool"], "FIRE")
        self.assertEqual(revisions, [])
        self.assertEqual(blocked, [{"date": "2020-01-01", "fields": ["spellSchool"]}])

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

    def test_known_grammar_correction_has_no_patch_date(self):
        self.assertEqual(BUILD.normalize_display_text("UNG_063", "+1/+1를 얻습니다."), "+1/+1을 얻습니다.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
