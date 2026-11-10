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
        self.assertEqual(BUILD.normalize_history_cache({"type": "MINION", "classes": []}),
                         {"type": "MINION"})
        self.assertEqual(BUILD.normalize_history_cache({"type": "MINION", "classes": ["DEMONHUNTER"]}),
                         {"type": "MINION", "classes": ["DEMONHUNTER"]})

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
            self.assertEqual(source["current"]["nativeRawText"], event["nativeRawText"])
            self.assertNotIn("nativeTextBuilder", event)
            self.assertEqual(source["current"]["nativeTextBuilder"], 0)
            self.assertNotIn("releasedAt", source)

    def test_focused_cards_report_filtered_native_tag_history_as_incomplete(self):
        catalogue = BUILD.load(ROOT / "cards.json")
        records = {x["id"]: x for x in catalogue["cards"]}
        for cid in ("UNG_832", "UNG_101a", "UNG_101b"):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            card = BUILD.normalize_date_keyed_source(source, records[cid])
            current = {}
            revisions, blocked, incomplete = BUILD.publish_forward_card(card, current, cid)
            self.assertIn("nativeTags", incomplete)
            self.assertEqual(card["currentCache"]["nativeTags"],
                             records[cid]["nativeTags"])
            first_day = sorted(k for k in source if BUILD.DATE_RE.fullmatch(k))[0]
            self.assertNotIn("currentCache", source[first_day])
            if cid == "UNG_832":
                self.assertIn("spellSchool", incomplete)
                self.assertEqual(current["cost"], 4)
                self.assertEqual(revisions[0]["changes"]["cost"], 2)
            else:
                self.assertIn("collectible", incomplete)
                self.assertTrue(any("attack" in x["fields"] for x in blocked))

    def test_eight_card_carddefs_baselines_and_tag_boundaries(self):
        catalogue = BUILD.load(ROOT / "cards.json")
        records = {x["id"]: x for x in catalogue["cards"]}
        school = {
            "UNG_018": ("FIRE", 2), "UNG_024": ("ARCANE", 1),
            "UNG_025": ("FIRE", 2), "UNG_028t": ("ARCANE", 1),
            "UNG_029": ("SHADOW", 6), "UNG_030": ("HOLY", 5),
            "UNG_057": ("NATURE", 4), "UNG_057t1": ("NATURE", 4),
        }
        for cid, (school_name, school_value) in school.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            days = sorted(k for k in source if BUILD.DATE_RE.fullmatch(k))
            playable_day = "2017-04-04" if cid in ("UNG_028t", "UNG_057t1") else "2017-04-07"
            self.assertEqual(days[0], playable_day)
            initial = source[days[0]]
            initial_tags = {x["id"]: x["value"] for x in initial["nativeTags"]}
            self.assertNotIn("spellSchool", initial)
            self.assertNotIn(1635, initial_tags)
            school_event = source["2021-03-26"]
            school_tags = {x["id"]: x["value"] for x in school_event["nativeTags"]}
            self.assertEqual(school_event["spellSchool"], school_name)
            self.assertEqual(school_tags[1635], school_value)
            self.assertEqual(source["current"]["nativeTags"], records[cid]["nativeTags"])
            self.assertEqual(source["sourceBaseline"]["commitDate"], "2017-04-04")
            self.assertNotIn("nativeReferences", initial)
            self.assertIn("nativeReferences", source["references"])
            self.assertEqual([x["id"] for x in source["referenceTags"]], [183])
            self.assertNotIn(183, {x["id"] for x in initial["nativeTags"]})
            self.assertEqual(source["nativeTagsTimelineStatus"],
                             "partial" if cid in ("UNG_025", "UNG_028t", "UNG_029") else "complete")

        for cid, ref_ids in {"UNG_018": [1452], "UNG_057": [1078, 1452]}.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            card = BUILD.normalize_date_keyed_source(source, records[cid])
            self.assertEqual([x["id"] for x in card["currentReferenceTags"]], ref_ids)
            current = {}
            BUILD.publish_forward_card(card, current, cid)
            self.assertEqual(current["nativeTags"], records[cid]["nativeTags"])

        geyser = BUILD.load(ROOT / "data" / "UNG_018.json")
        self.assertEqual(geyser["2017-04-07"]["cost"], 2)
        self.assertEqual(next(x for x in geyser["2017-04-07"]["nativeTags"] if x["id"] == 48)["value"], 2)
        self.assertEqual(geyser["2023-04-05"]["cost"], 1)
        self.assertEqual(next(x for x in geyser["2023-04-05"]["nativeTags"] if x["id"] == 48)["value"], 1)

        volcano = BUILD.load(ROOT / "data" / "UNG_025.json")
        self.assertEqual(next(x for x in volcano["2017-04-07"]["nativeTags"] if x["id"] == 215)["value"], 2)
        self.assertEqual(next(x for x in volcano["2023-10-18"]["nativeTags"] if x["id"] == 215)["value"], 1)
        self.assertIn(296, {x["id"] for x in volcano["2023-10-18"]["nativeTags"]})
        self.assertTrue(any(x["field"] == "nativeTags[296]" for x in volcano["unresolvedSourceFields"]))

        warp = BUILD.load(ROOT / "data" / "UNG_028t.json")
        self.assertIsNone(warp["current"].get("releasedAt"))
        self.assertIsNone(warp.get("releasedAt"))
        self.assertTrue(any(x["field"] == "nativeTags[203]/rarity" for x in warp["unresolvedSourceFields"]))
        self.assertTrue(any(x["field"] == "collectible" for x in warp["unresolvedSourceFields"]))
        self.assertIn("2024-04-26", warp)
        self.assertIn("nativeRawText", warp["2024-04-26"])

        for cid in ("UNG_057", "UNG_057t1"):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertIn("2023-10-18", source)
            self.assertIn("nativeRawText", source["2023-10-18"])
        token = BUILD.load(ROOT / "data" / "UNG_057t1.json")
        self.assertIsNone(token.get("releasedAt"))
        self.assertTrue(any(x["field"] == "collectible" for x in token["unresolvedSourceFields"]))

    def test_carddefs_enum_mappings_match_raw_tags_across_all_185_cards(self):
        baseline = BUILD.load(ROOT / "sources" / "carddefs-18336-baseline.json")
        catalogue = BUILD.load(ROOT / "cards.json")
        baseline_counts = BUILD.validate_baseline_enum_mappings(baseline)
        current_counts = BUILD.validate_current_enum_mappings(catalogue["cards"])
        self.assertEqual(baseline_counts["cards"], 185)
        self.assertEqual(current_counts["cards"], 185)
        self.assertEqual(BUILD.RARITY_BY_TAG[3], "RARE")
        self.assertEqual(BUILD.RARITY_BY_TAG[4], "EPIC")
        rare_tag_three = [
            entry["state"] for entry in baseline["cards"].values()
            if BUILD.native_tag_values(entry["state"]).get(203) == 3
        ]
        self.assertEqual(len(rare_tag_three), 39)
        self.assertTrue(all(state["rarity"] == "RARE" for state in rare_tag_three))
        epic_tag_four = [
            entry["state"] for entry in baseline["cards"].values()
            if BUILD.native_tag_values(entry["state"]).get(203) == 4
        ]
        self.assertTrue(all(state["rarity"] == "EPIC" for state in epic_tag_four))
        self.assertEqual(BUILD.RACE_LABEL_BY_TAG[20], "야수")
        self.assertEqual(BUILD.RACE_LABEL_BY_TAG[14], "멀록")
        self.assertEqual(BUILD.RACE_LABEL_BY_TAG[24], "용족")

        for cid in ("UNG_024", "UNG_025"):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial = source["2017-04-07"]
            self.assertEqual(initial["rarity"], "RARE")
            self.assertEqual(BUILD.native_tag_values(initial)[203], 3)
            self.assertEqual(source["current"]["rarity"], "RARE")
            self.assertFalse(any(x["field"] == "rarity"
                                 for x in source["unresolvedSourceFields"]))
        current_by_id = {x["id"]: x for x in catalogue["cards"]}
        self.assertEqual(current_by_id["UNG_024"]["rarity"], "RARE")
        self.assertEqual(current_by_id["UNG_025"]["rarity"], "RARE")

    def test_known_grammar_correction_has_no_patch_date(self):
        self.assertEqual(BUILD.normalize_display_text("UNG_063", "+1/+1를 얻습니다."), "+1/+1을 얻습니다.")


    def test_eight_spell_batch_date_boundaries_and_cache_separation(self):
        expected = {
            "UNG_060": ["2021-03-26", "2023-10-18"],
            "UNG_103": ["2021-03-26", "2023-10-18"],
            "UNG_108": ["2021-03-26"],
            "UNG_111": ["2021-03-26"],
            "UNG_817": ["2021-03-26", "2021-05-13", "2023-10-18"],
            "UNG_823": ["2021-03-26", "2023-10-18"],
            "UNG_829t1": ["2021-03-26"],
            "UNG_831": ["2021-03-26"],
        }
        for cid, patch_dates in expected.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertEqual(source["schemaVersion"], 2)
            date_keys = sorted(k for k in source if BUILD.DATE_RE.fullmatch(k))
            self.assertEqual(date_keys[1:], patch_dates)
            first = source[date_keys[0]]
            self.assertEqual(first["type"], "SPELL")
            self.assertNotIn("nativeTextBuilder", first)
            self.assertNotIn(183, {x["id"] for x in first["nativeTags"]})
            self.assertEqual(source["sourceBaseline"]["commitDate"], "2017-04-04")
            self.assertEqual(source["referenceTags"][0]["id"], 183)
            self.assertEqual(source["current"]["spellSchool"],
                             "SHADOW" if cid in ("UNG_829t1", "UNG_831") else "NATURE")
            school = source["2021-03-26"]
            self.assertEqual(school["spellSchool"], source["current"]["spellSchool"])
            self.assertIn(1635, {x["id"] for x in school["nativeTags"]})
            self.assertIn("nativeTextBuilder", {x["field"] for x in source["unresolvedSourceFields"]})
        token = BUILD.load(ROOT / "data" / "UNG_829t1.json")
        self.assertEqual(token["current"]["releaseStatus"], "pending")
        self.assertIsNone(token["current"]["releasedAt"])
        self.assertEqual(token["nativeTagsTimelineStatus"], "partial")
        tide = BUILD.load(ROOT / "data" / "UNG_817.json")
        self.assertIn(685, {x["id"] for x in tide["2021-03-26"]["nativeTags"]})
        self.assertEqual(tide["2021-05-13"]["cost"], 3)
        self.assertEqual(tide["2023-10-18"]["text"],
                         "<b>생명력 흡수</b><br></br>하수인에게 피해를<br></br>$5 줍니다.")
        self.assertNotIn("text", tide["historyIncompleteFields"])
        mana = BUILD.load(ROOT / "data" / "UNG_111.json")
        self.assertIn(1452, {x["id"] for x in mana["current"]["nativeTags"]})
        self.assertIn(1452, {x["id"] for x in mana["currentReferenceTags"]})
        adaptive = BUILD.load(ROOT / "data" / "UNG_103.json")
        self.assertEqual(adaptive["nativeTagsTimelineStatus"], "partial")
        self.assertIn("nativeTags", adaptive["historyIncompleteFields"])
        scales = BUILD.load(ROOT / "data" / "UNG_108.json")
        self.assertIn("cost", scales["historyIncompleteFields"])
        self.assertIn("nativeTags", scales["historyIncompleteFields"])
        self.assertTrue(any(x["field"] == "cost" for x in scales["unresolvedSourceFields"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
