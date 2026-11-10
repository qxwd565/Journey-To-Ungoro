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
            "2020-04-21": {"cost": 4, "source": "https://example.test/2020", "confidence": "high"},
            "2021-03-26": {"spellSchool": "SHADOW", "source": "https://example.test/2021", "note": "school introduction"},
        }
        card = BUILD.normalize_date_keyed_source(data, {"id": "UNG_832", "releasedAt": "2017-04-07"})
        self.assertEqual(card["cost"], 2)
        self.assertEqual(card["patches"][0]["changes"]["cost"], 4)
        self.assertEqual(card["currentCache"]["cost"], 4)
        self.assertEqual(card["patches"][1]["changes"]["spellSchool"], "SHADOW")
        self.assertEqual(card["patchSources"], {
            "2020-04-21": "https://example.test/2020",
            "2021-03-26": "https://example.test/2021",
        })
        self.assertEqual(card["patchConfidence"]["2020-04-21"], "high")
        self.assertEqual(card["patchNotes"]["2021-03-26"], "school introduction")

    def test_bloodbloom_source_tag_and_scalar_boundaries(self):
        source = BUILD.load(ROOT / "data" / "UNG_832.json")
        keys = sorted(k for k in source if BUILD.DATE_RE.fullmatch(k))
        states = [source[keys[0]]]
        def tags(state):
            return {item["id"]: item["value"] for item in state["nativeTags"]}
        self.assertEqual(keys, ["2017-04-07", "2020-04-21", "2021-03-26"])
        self.assertEqual(states[0]["cost"], 2)
        self.assertEqual(tags(states[0])[48], states[0]["cost"])
        self.assertNotIn("spellSchool", states[0])
        self.assertNotIn(1635, tags(states[0]))
        for event in [source[key] for key in keys[1:]]:
            nxt = dict(states[-1])
            for field in event.get("remove", []):
                nxt.pop(field)
            nxt.update({k: v for k, v in event.items()
                        if k not in {"source", "confidence", "note", "remove", "status"}})
            states.append(nxt)
        self.assertEqual(states[1]["cost"], 4)
        self.assertEqual(tags(states[1])[48], states[1]["cost"])
        self.assertNotIn("spellSchool", states[1])
        self.assertNotIn(1635, tags(states[1]))
        self.assertEqual(states[2]["cost"], 4)
        self.assertEqual(tags(states[2])[48], states[2]["cost"])
        self.assertEqual(states[2]["spellSchool"], "SHADOW")
        self.assertEqual(tags(states[2])[1635], 6)
        self.assertNotIn("nativeTextBuilder", states[0])
        self.assertEqual(source["current"]["cost"], 4)
        self.assertEqual(source["current"]["nativeTextBuilder"], 0)

    def test_choose_one_forms_have_absent_spell_fields_before_2018_transition(self):
        for cid, expected in {
            "UNG_101a": {"attack": 5, "health": 3, "taunt": False},
            "UNG_101b": {"attack": 3, "health": 5, "taunt": True},
        }.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial = source["2017-04-04"]
            event = source["2018-11-30"]
            initial_tags = {x["id"]: x["value"] for x in initial["nativeTags"]}
            after_tags = {x["id"]: x["value"] for x in event["nativeTags"]}
            self.assertEqual(initial["type"], "SPELL")
            for field in ("cost", "attack", "health", "race", "races", "spellSchool", "nativeTextBuilder"):
                self.assertNotIn(field, initial)
            for tag_id in (45, 47, 48, 190, 200):
                self.assertNotIn(tag_id, initial_tags)
            self.assertEqual(initial_tags[202], 5)
            self.assertEqual(event["type"], "MINION")
            self.assertEqual(event["cost"], 4)
            self.assertEqual(event["attack"], expected["attack"])
            self.assertEqual(event["health"], expected["health"])
            self.assertEqual(event["races"], ["BEAST"])
            self.assertEqual(event["race"], "야수")
            self.assertEqual(after_tags[202], 4)
            self.assertEqual(after_tags[48], event["cost"])
            self.assertEqual(after_tags[47], event["attack"])
            self.assertEqual(after_tags[45], event["health"])
            self.assertEqual(after_tags[200], 20)
            self.assertEqual(after_tags.get(190) == 1, expected["taunt"])
            self.assertEqual(event["nativeRawText"], event["text"])
            self.assertNotIn("nativeTextBuilder", event)
            self.assertEqual(source["current"]["nativeTextBuilder"], 0)
            self.assertNotIn("releasedAt", source)

    def test_known_grammar_correction_has_no_patch_date(self):
        self.assertEqual(BUILD.normalize_display_text("UNG_063", "+1/+1를 얻습니다."), "+1/+1을 얻습니다.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
