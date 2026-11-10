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
        expected_races = {14: "MURLOC", 20: "BEAST", 24: "DRAGON"}
        race_count = 0
        for cid, entry in baseline["cards"].items():
            state = entry["state"]
            race_tag = BUILD.native_tag_values(state).get(200)
            if race_tag in expected_races:
                self.assertEqual(state.get("races"), [expected_races[race_tag]], cid)
                race_count += 1
        self.assertEqual(race_count, 53)

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
            "UNG_108": ["2021-03-26", "2022-06-17"],
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
        venom = BUILD.load(ROOT / "data" / "UNG_823.json")
        self.assertEqual(venom["nativeTagsTimelineStatus"], "partial")
        self.assertIn("nativeTags", venom["historyIncompleteFields"])
        self.assertTrue(any(x["field"] == "nativeTags[363]" for x in venom["unresolvedSourceFields"]))
        scales = BUILD.load(ROOT / "data" / "UNG_108.json")
        self.assertEqual(scales["2017-04-07"]["cost"], 1)
        self.assertEqual(scales["2022-06-17"]["cost"], 2)
        self.assertEqual({x["id"]: x["value"] for x in scales["2022-06-17"]["nativeTags"]}[48], 2)
        self.assertEqual(scales["nativeTagsTimelineStatus"], "complete")
        self.assertNotIn("cost", scales["historyIncompleteFields"])
        self.assertNotIn("nativeTags", scales["historyIncompleteFields"])
        self.assertFalse(any(x["field"] in ("cost", "nativeTags[48]") for x in scales["unresolvedSourceFields"]))


    def test_october_2023_eight_card_source_and_published_boundaries(self):
        expected_schools = {
            "UNG_856": ("NATURE", 4), "UNG_927": ("NATURE", 4),
            "UNG_941": ("ARCANE", 1), "UNG_948": ("FIRE", 2),
            "UNG_955": ("FIRE", 2), "UNG_956": ("NATURE", 4),
        }
        for cid, (school, tag_value) in expected_schools.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial = source["2017-04-07"]
            self.assertNotIn("spellSchool", initial, cid)
            self.assertNotIn(1635, {x["id"] for x in initial["nativeTags"]}, cid)
            event = source["2021-03-26"]
            self.assertEqual(event["spellSchool"], school, cid)
            self.assertEqual(BUILD.native_tag_values(event)[1635], tag_value, cid)
            self.assertEqual(source["current"]["spellSchool"], school, cid)

        tyrant = BUILD.load(ROOT / "data" / "UNG_852.json")
        self.assertEqual((tyrant["2017-04-07"]["attack"], tyrant["2017-04-07"]["health"]), (12, 12))
        self.assertEqual((tyrant["2023-10-18"]["attack"], tyrant["2023-10-18"]["health"]), (14, 14))
        self.assertNotIn(190, BUILD.native_tag_values(tyrant["2017-04-07"]))
        self.assertEqual(BUILD.native_tag_values(tyrant["2023-10-18"])[190], 1)
        self.assertIn("[x]", tyrant["2023-10-18"]["nativeRawText"])
        self.assertNotIn(1211, BUILD.native_tag_values(tyrant["2023-10-18"]))

        cleaver = BUILD.load(ROOT / "data" / "UNG_950.json")
        self.assertEqual(cleaver["2017-04-07"]["cost"], 7)
        self.assertEqual(BUILD.native_tag_values(cleaver["2017-04-07"])[48], 7)
        self.assertEqual(cleaver["2023-10-18"]["cost"], 6)
        self.assertEqual(BUILD.native_tag_values(cleaver["2023-10-18"])[48], 6)

        genesis = BUILD.load(ROOT / "data" / "UNG_927.json")
        self.assertEqual((genesis["2017-04-07"]["cost"], genesis["2023-10-18"]["cost"]), (5, 4))
        meteor = BUILD.load(ROOT / "data" / "UNG_955.json")
        self.assertIn("$3", meteor["2017-04-07"]["nativeRawText"])
        self.assertIn("$4", meteor["2023-10-18"]["nativeRawText"])
        self.assertIn(chr(10), meteor["2023-10-18"]["nativeRawText"])
        echo = BUILD.load(ROOT / "data" / "UNG_956.json")
        self.assertEqual((echo["2017-04-07"]["cost"], echo["2023-10-18"]["cost"]), (3, 2))

        render = BUILD.load(ROOT / "render.json")
        history = BUILD.load(ROOT / "history.json")
        cards = BUILD.load(ROOT / "cards.json")
        by_id = {x["id"]: x for x in render["cards"]}
        self.assertEqual((by_id["UNG_852"]["attack"], by_id["UNG_852"]["health"]), (14, 14))
        self.assertEqual(by_id["UNG_955"]["text"], meteor["current"]["text"])
        card_index = next(i for i, x in enumerate(cards["cards"]) if x["id"] == "UNG_955")
        self.assertEqual(cards["cards"][card_index]["text"], meteor["current"]["text"])
        self.assertIn("41954", history["cards"])
        h852 = history["cards"]["41954"]["history"][0]
        self.assertEqual(h852["before"], "2023-10-18")
        self.assertEqual((h852["changes"]["attack"], h852["changes"]["health"]), (12, 12))
        self.assertIn("대상으로 지정되지 않습니다", h852["changes"]["text"])
        self.assertTrue({311, 332}.issubset({x["id"] for x in h852["changes"]["nativeTags"]}))
        self.assertEqual(by_id["UNG_852"]["history"], history["cards"]["41954"]["history"])

        h950 = history["cards"]["41859"]["history"][0]
        self.assertEqual((h950["before"], h950["changes"]["cost"]), ("2023-10-18", 7))
        self.assertEqual({x["id"]: x["value"] for x in h950["changes"]["nativeTags"]}[48], 7)
        h927 = history["cards"]["41407"]["history"]
        self.assertEqual(next(x for x in h927 if x["before"] == "2023-10-18")["changes"]["cost"], 5)
        h956 = history["cards"]["41879"]["history"]
        rev956 = next(x for x in h956 if x["before"] == "2023-10-18")
        self.assertEqual(rev956["changes"]["cost"], 3)
        self.assertEqual({x["id"]: x["value"] for x in rev956["changes"]["nativeTags"]}[1635], 4)
        h955 = history["cards"]["41878"]["history"]
        rev955 = next(x for x in h955 if x["before"] == "2023-10-18")
        self.assertIn("$3", rev955["changes"]["text"])
        self.assertIn("$4", meteor["2023-10-18"]["nativeRawText"])
        for cid, dbf in (("UNG_856", "42011"), ("UNG_927", "41407"),
                         ("UNG_941", "41496"), ("UNG_948", "41690"),
                         ("UNG_955", "41878"), ("UNG_956", "41879")):
            old_state = history["cards"][dbf]["history"][0]["changes"]
            self.assertNotIn(1635, {x["id"] for x in old_state["nativeTags"]}, cid)
        self.assertEqual(by_id["UNG_955"]["text"], cards["cards"][card_index]["text"])


    def test_next_sixteen_ungoro_cards_have_exact_dated_states_and_native_tags(self):
        catalogue = BUILD.load(ROOT / "cards.json")
        records = {card["id"]: card for card in catalogue["cards"]}
        expected_dates = {
            "UNG_002": ["2017-04-05", "2022-11-30", "2023-10-18"],
            "UNG_010": ["2017-04-07", "2023-10-18"],
            "UNG_019": ["2017-04-07", "2024-03-29"],
            "UNG_027": ["2017-04-07", "2022-11-30", "2023-10-18"],
            "UNG_027t2": ["2017-04-04", "2022-11-30", "2023-10-18"],
            "UNG_027t4": ["2017-04-04", "2022-11-30", "2023-10-18"],
            "UNG_032": ["2017-04-07", "2023-10-18"],
            "UNG_035": ["2017-04-07", "2023-10-18"],
            "UNG_037": ["2017-04-07", "2023-10-18"],
            "UNG_047": ["2017-04-07", "2023-10-18"],
            "UNG_063": ["2017-04-07", "2023-10-18"],
            "UNG_065": ["2017-04-07", "2023-10-18"],
            "UNG_070": ["2017-04-07", "2023-10-18"],
            "UNG_071": ["2017-04-07", "2023-10-18"],
            "UNG_072": ["2017-04-07", "2023-10-18"],
            "UNG_079": ["2017-04-07", "2023-10-18"],
        }
        self.assertEqual(len(expected_dates), 16)
        for cid, dates in expected_dates.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertEqual(source["schemaVersion"], 2, cid)
            self.assertEqual(source["dbfId"], records[cid]["dbfId"], cid)
            self.assertEqual(sorted(k for k in source if BUILD.DATE_RE.fullmatch(k)), dates, cid)
            self.assertEqual(source["sourceBaseline"]["commitDate"], "2017-04-04", cid)
            self.assertEqual(source["sourceBaseline"]["build"], 18336, cid)
            self.assertEqual(source["current"]["nativeTags"], records[cid]["nativeTags"], cid)

        volcano = BUILD.load(ROOT / "data" / "UNG_002.json")
        self.assertEqual(volcano["2017-04-05"]["race"], "야수")
        self.assertEqual(BUILD.native_tag_values(volcano["2017-04-05"])[200], 20)
        self.assertEqual(volcano["2022-11-30"]["races"], ["ELEMENTAL", "BEAST"])
        self.assertEqual(BUILD.native_tag_values(volcano["2022-11-30"])[2540], 1)
        self.assertEqual((volcano["2017-04-05"]["cost"], volcano["2023-10-18"]["cost"]), (7, 6))
        self.assertEqual(BUILD.native_tag_values(volcano["2023-10-18"])[48], 6)

        for cid in ("UNG_027", "UNG_027t2", "UNG_027t4"):
            pyros = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial_day = "2017-04-04" if cid.endswith(("t2", "t4")) else "2017-04-07"
            self.assertEqual(BUILD.native_tag_values(pyros[initial_day])[200], 18)
            self.assertNotIn(2542, BUILD.native_tag_values(pyros[initial_day]))
            self.assertEqual(pyros["2022-11-30"]["races"], ["ELEMENTAL", "BEAST"])
            self.assertEqual(BUILD.native_tag_values(pyros["2022-11-30"])[2542], 1)
        p2 = BUILD.load(ROOT / "data" / "UNG_027t2.json")
        p4 = BUILD.load(ROOT / "data" / "UNG_027t4.json")
        self.assertIsNone(p2["current"]["releasedAt"])
        self.assertEqual(p2["current"]["releaseStatus"], "pending")
        self.assertIsNone(p4["current"]["releasedAt"])
        self.assertEqual(p4["current"]["releaseStatus"], "pending")
        self.assertEqual((p2["2017-04-04"]["cost"], p2["2023-10-18"]["cost"]), (6, 4))
        self.assertEqual(BUILD.native_tag_values(p2["2023-10-18"])[48], 4)
        self.assertEqual((p4["2017-04-04"]["cost"], p4["2023-10-18"]["cost"]), (10, 8))
        self.assertEqual(BUILD.native_tag_values(p4["2023-10-18"])[48], 8)
        p1 = BUILD.load(ROOT / "data" / "UNG_027.json")
        self.assertIn("[x]", p1["2017-04-07"]["nativeRawText"])
        self.assertIn("(6)", p1["2017-04-07"]["nativeRawText"])
        self.assertIn("(4)", p1["2023-10-18"]["nativeRawText"])

        trex = BUILD.load(ROOT / "data" / "UNG_010.json")
        self.assertEqual(trex["2017-04-07"]["health"], 7)
        self.assertNotIn(190, BUILD.native_tag_values(trex["2017-04-07"]))
        self.assertEqual(trex["2023-10-18"]["health"], 8)
        self.assertEqual(BUILD.native_tag_values(trex["2023-10-18"])[190], 1)
        self.assertIn("\n", trex["2023-10-18"]["nativeRawText"])
        self.assertEqual(trex["current"]["text"], records["UNG_010"]["text"])

        wind = BUILD.load(ROOT / "data" / "UNG_019.json")
        old_wind_tags = BUILD.native_tag_values(wind["2017-04-07"])
        self.assertEqual((old_wind_tags[311], old_wind_tags[332]), (1, 1))
        self.assertNotIn(1211, old_wind_tags)
        self.assertEqual(wind["2024-03-29"]["attack"], 3)
        self.assertNotIn("nativeTags", wind["2024-03-29"])
        self.assertEqual(BUILD.native_tag_values(wind["current"])[1211], 1)
        self.assertEqual(wind["nativeTagsTimelineStatus"], "partial")
        self.assertIn("nativeTags", wind["historyIncompleteFields"])

        stat_changes = {
            "UNG_032": (("health", 1), ("health", 2), 45, 2),
            "UNG_035": (("health", 3), ("health", 4), 45, 4),
            "UNG_037": (("cost", 4), ("cost", 3), 48, 3),
            "UNG_047": (("cost", 4), ("cost", 3), 48, 3),
            "UNG_063": (("health", 1), ("health", 2), 45, 2),
            "UNG_065": (("attack", 5), ("attack", 6), 47, 6),
            "UNG_070": (("health", 5), ("health", 6), 45, 6),
            "UNG_071": (("health", 10), ("health", 12), 45, 12),
            "UNG_072": (("health", 4), ("health", 5), 45, 5),
            "UNG_079": (("cost", 6), ("cost", 5), 48, 5),
        }
        for cid, (old_pair, new_pair, tag_id, tag_value) in stat_changes.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial_day = "2017-04-07"
            self.assertEqual(source[initial_day][old_pair[0]], old_pair[1], cid)
            self.assertEqual(source["2023-10-18"][new_pair[0]], new_pair[1], cid)
            self.assertEqual(BUILD.native_tag_values(source["2023-10-18"])[tag_id], tag_value, cid)

        grammar = BUILD.load(ROOT / "data" / "UNG_063.json")
        self.assertIn("+1/+1를", grammar["2017-04-07"]["nativeRawText"])
        self.assertIn("+1/+1을", grammar["current"]["text"])
        self.assertIn("+1/+1를", grammar["current"]["nativeRawText"])


    def test_ungoro_conditional_taunt_and_partial_tags_do_not_invent_events(self):
        stone = BUILD.load(ROOT / "data" / "UNG_070.json")
        self.assertNotIn(190, BUILD.native_tag_values(stone["2017-04-07"]))
        self.assertNotIn(190, BUILD.native_tag_values(stone["2023-10-18"]))
        self.assertEqual(BUILD.native_tag_values(stone["current"])[190], 1)
        self.assertIn("nativeTags", stone["historyIncompleteFields"])
        trex = BUILD.load(ROOT / "data" / "UNG_010.json")
        self.assertEqual(BUILD.native_tag_values(trex["2023-10-18"])[190], 1)
        wind = BUILD.load(ROOT / "data" / "UNG_019.json")
        self.assertIn("text", wind["historyIncompleteFields"])
        self.assertEqual(wind["2017-04-07"]["text"],
                         "이 하수인은 주문이나 영웅 능력의 대상으로 지정되지 않습니다.")


    def test_ung_019_2024_attack_boundary_does_not_date_target_protection_tag_conversion(self):
        source = BUILD.load(ROOT / "data" / "UNG_019.json")
        initial = source["2017-04-07"]
        event = source["2024-03-29"]
        current = source["current"]
        initial_tags = BUILD.native_tag_values(initial)
        current_tags = BUILD.native_tag_values(current)
        self.assertEqual((initial_tags[311], initial_tags[332]), (1, 1))
        self.assertNotIn(1211, initial_tags)
        self.assertEqual(event["attack"], 3)
        self.assertNotIn("nativeTags", event)
        self.assertEqual(event["source"], "https://hearthstone.blizzard.com/ko-kr/news/24064739")
        self.assertEqual(event["sourceEvidence"] if "sourceEvidence" in event else source["sourceEvidence"]["2024-03-29"]["cardDefsCommit"],
                         "e73eeb8d2c284af5fcddc2db5fce692c77434cd8")
        self.assertEqual(current["attack"], 3)
        self.assertEqual(current_tags[47], 3)
        self.assertEqual(current_tags[1211], 1)
        self.assertEqual(source["nativeTagsTimelineStatus"], "partial")
        self.assertEqual(source["historyKnownFields"], [])
        self.assertIn("nativeTags", source["historyIncompleteFields"])
        self.assertIn("nativeTags[311,332,1211]",
                      [x["field"] for x in source["unresolvedSourceFields"]])


    def test_next_sixteen_ungoro_sources_replay_confirmed_boundaries_and_scoped_tags(self):
        ids = (
            "UNG_084", "UNG_085", "UNG_086", "UNG_088", "UNG_099", "UNG_100",
            "UNG_101", "UNG_111t1", "UNG_113", "UNG_208", "UNG_211", "UNG_800",
            "UNG_801", "UNG_808", "UNG_816", "UNG_818",
        )
        catalog = BUILD.load(ROOT / "cards.json")
        records = {card["id"]: card for card in catalog["cards"]}
        self.assertEqual(len(ids), 16)
        for cid in ids:
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertEqual(source["schemaVersion"], 2, cid)
            self.assertEqual(source["dbfId"], records[cid]["dbfId"], cid)
            initial_day = "2017-04-04" if cid == "UNG_111t1" else "2017-04-07"
            self.assertEqual(source[initial_day]["nativeTags"],
                             [x for x in BUILD.load(ROOT / "sources" / "carddefs-18336-baseline.json")["cards"][cid]["state"]["nativeTags"] if x["id"] != 183], cid)
            card = BUILD.normalize_date_keyed_source(
                source, {"id": cid, "releasedAt": records[cid]["releasedAt"]}
            )
            patches, states = BUILD.replay_forward_states(card, cid)
            latest = states[-1]
            current = source["current"]
            self.assertEqual(latest["id"] if "id" in latest else cid, cid)
            self.assertEqual(current["nativeTags"], records[cid]["nativeTags"], cid)
            self.assertEqual(current.get("releasedAt"), records[cid].get("releasedAt"), cid)

        volcano = BUILD.load(ROOT / "data" / "UNG_084.json")
        card = BUILD.normalize_date_keyed_source(volcano, {"id": "UNG_084", "releasedAt": "2017-04-07"})
        _, states = BUILD.replay_forward_states(card, "UNG_084")
        self.assertEqual((states[0]["health"], BUILD.native_tag_values(states[0])[45]), (3, 3))
        self.assertEqual((states[1]["race"], states[1]["races"]), ("정령, 야수", ["ELEMENTAL", "BEAST"]))
        self.assertEqual(BUILD.native_tag_values(states[1])[2542], 1)
        self.assertEqual((states[2]["text"], states[2]["nativeRawText"]),
                         (volcano["2023-10-18"]["text"], volcano["2023-10-18"]["nativeRawText"]))
        self.assertEqual((states[3]["health"], BUILD.native_tag_values(states[3])[45]), (4, 4))

        devil = BUILD.load(ROOT / "data" / "UNG_099.json")
        card = BUILD.normalize_date_keyed_source(devil, {"id": "UNG_099", "releasedAt": "2017-04-07"})
        _, states = BUILD.replay_forward_states(card, "UNG_099")
        self.assertEqual(BUILD.native_tag_values(states[0])[200], 20)
        self.assertEqual(BUILD.native_tag_values(states[1])[2540], 1)
        self.assertEqual(states[1]["races"], ["ELEMENTAL", "BEAST"])
        self.assertEqual((states[2]["cost"], BUILD.native_tag_values(states[2])[48]), (7, 7))

        expected = {
            "UNG_085": ("attack", 2, 3, 47, 3),
            "UNG_088": ("health", 4, 5, 45, 5),
            "UNG_100": ("health", 4, 5, 45, 5),
            "UNG_113": ("cost", 4, 3, 48, 3),
            "UNG_208": ("cost", 7, 5, 48, 5),
            "UNG_211": ("cost", 8, 7, 48, 7),
            "UNG_800": ("cost", 3, 2, 48, 2),
            "UNG_808": ("health", 2, 3, 45, 3),
            "UNG_816": ("attack", 4, 5, 47, 5),
            "UNG_818": ("attack", 1, 3, 47, 3),
        }
        for cid, (field, before, after, tag_id, tag_value) in expected.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            card = BUILD.normalize_date_keyed_source(source, {"id": cid, "releasedAt": "2017-04-07"})
            _, states = BUILD.replay_forward_states(card, cid)
            self.assertEqual(states[0][field], before, cid)
            self.assertEqual(states[-1][field], after, cid)
            self.assertEqual(BUILD.native_tag_values(states[-1])[tag_id], tag_value, cid)

        anaconda = BUILD.load(ROOT / "data" / "UNG_086.json")
        self.assertNotIn(190, BUILD.native_tag_values(anaconda["2017-04-07"]))
        self.assertEqual(anaconda["2023-10-18"]["nativeTagUpdates"], [{"id": 190, "value": 1, "name": "도발"}])
        rock = BUILD.load(ROOT / "data" / "UNG_801.json")
        self.assertNotIn(190, BUILD.native_tag_values(rock["2017-04-07"]))
        self.assertNotIn("nativeTagUpdates", rock)
        stalker = BUILD.load(ROOT / "data" / "UNG_800.json")
        self.assertNotIn(217, BUILD.native_tag_values(stalker["2017-04-07"]))
        self.assertNotIn(217, BUILD.native_tag_values(stalker["2023-10-18"]))
        shell = BUILD.load(ROOT / "data" / "UNG_101.json")
        self.assertNotIn(190, BUILD.native_tag_values(shell["2017-04-07"]))
        self.assertNotIn("nativeTagUpdates", shell)

        treant = BUILD.load(ROOT / "data" / "UNG_111t1.json")
        self.assertIsNone(treant["current"]["releasedAt"])
        self.assertEqual(treant["current"]["releaseStatus"], "pending")
        self.assertEqual(treant["current"]["races"], [])
        self.assertNotIn("races", treant["2017-04-04"])
        self.assertNotIn(2831, BUILD.native_tag_values(treant["2017-04-04"]))
        self.assertEqual(treant["2023-04-05"]["confidence"], "medium-high")
        card = BUILD.normalize_date_keyed_source(treant, {"id": "UNG_111t1", "releasedAt": None})
        _, states = BUILD.replay_forward_states(card, "UNG_111t1")
        self.assertEqual((states[-1]["cost"], BUILD.native_tag_values(states[-1])[48]), (1, 1))


    def test_next_sixteen_ungoro_cards_replay_stats_abilities_races_and_native_tags(self):
        ids = (
            "UNG_830", "UNG_835", "UNG_838", "UNG_843", "UNG_845", "UNG_846",
            "UNG_847", "UNG_900", "UNG_907", "UNG_912", "UNG_913", "UNG_914t1",
            "UNG_919", "UNG_920t1", "UNG_925", "UNG_926",
        )
        baseline = BUILD.load(ROOT / "sources" / "carddefs-18336-baseline.json")
        catalog = BUILD.load(ROOT / "cards.json")
        records = {x["id"]: x for x in catalog["cards"]}
        self.assertEqual(len(ids), 16)
        for cid in ids:
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertEqual(source["schemaVersion"], 2, cid)
            self.assertEqual(source["dbfId"], records[cid]["dbfId"], cid)
            initial_day = "2017-04-04" if records[cid].get("releasedAt") is None else "2017-04-07"
            self.assertEqual(source[initial_day]["nativeTags"],
                             [x for x in baseline["cards"][cid]["state"]["nativeTags"] if x["id"] != 183], cid)
            card = BUILD.normalize_date_keyed_source(
                source, {"id": cid, "releasedAt": records[cid].get("releasedAt")}
            )
            patches, states = BUILD.replay_forward_states(card, cid)
            self.assertTrue(states, cid)

        expected = {
            "UNG_830": ("cost", 6, 5, 48, 5),
            "UNG_835": ("cost", 3, 2, 48, 2),
            "UNG_838": ("cost", 7, 6, 48, 6),
            "UNG_843": ("cost", 4, 3, 48, 3),
            "UNG_845": ("attack", 2, 3, 47, 3),
            "UNG_847": ("cost", 7, 6, 48, 6),
            "UNG_907": ("cost", 9, 8, 48, 8),
            "UNG_912": ("health", 1, 2, 45, 2),
            "UNG_913": ("cost", 5, 4, 48, 4),
            "UNG_914t1": ("health", 3, 5, 45, 5),
            "UNG_919": ("cost", 7, 6, 48, 6),
            "UNG_925": ("attack", 5, 6, 47, 6),
        }
        for cid, (field, before, after, tag_id, tag_value) in expected.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            released = records[cid].get("releasedAt")
            card = BUILD.normalize_date_keyed_source(source, {"id": cid, "releasedAt": released})
            _, states = BUILD.replay_forward_states(card, cid)
            self.assertEqual(states[0][field], before, cid)
            self.assertEqual(states[-1][field], after, cid)
            self.assertEqual(BUILD.native_tag_values(states[-1])[tag_id], tag_value, cid)

        anaconda = BUILD.load(ROOT / "data" / "UNG_086.json")
        card = BUILD.normalize_date_keyed_source(anaconda, {"id": "UNG_086", "releasedAt": "2017-04-07"})
        _, states = BUILD.replay_forward_states(card, "UNG_086")
        self.assertNotIn(190, BUILD.native_tag_values(states[0]))
        self.assertEqual(BUILD.native_tag_values(states[-1])[190], 1)
        self.assertEqual(states[-1]["text"], anaconda["2023-10-18"]["text"])
        self.assertNotIn("nativeTags", anaconda["historyIncompleteFields"])

        storm = BUILD.load(ROOT / "data" / "UNG_846.json")
        card = BUILD.normalize_date_keyed_source(storm, {"id": "UNG_846", "releasedAt": "2017-04-07"})
        _, states = BUILD.replay_forward_states(card, "UNG_846")
        self.assertEqual(BUILD.native_tag_values(states[0])[217], 1)
        self.assertNotIn(218, BUILD.native_tag_values(states[0]))
        self.assertNotIn(217, BUILD.native_tag_values(states[-1]))
        self.assertEqual(BUILD.native_tag_values(states[-1])[218], 1)
        self.assertEqual(states[-1]["health"], 2)

        umbra = BUILD.load(ROOT / "data" / "UNG_900.json")
        self.assertNotIn(217, BUILD.native_tag_values(umbra["2017-04-07"]))
        self.assertEqual(umbra["2026-02-25"]["nativeTagUpdates"], [{"id": 48, "value": 5}])
        self.assertIn("nativeTags[217]", [x["field"] for x in umbra["unresolvedSourceFields"]])
        self.assertEqual(umbra["2026-02-25"]["cost"], 5)

        parrot = BUILD.load(ROOT / "data" / "UNG_912.json")
        self.assertIn("2023-04-05", parrot)
        self.assertNotIn("2023-10-18", parrot)

        queen = BUILD.load(ROOT / "data" / "UNG_920t1.json")
        self.assertIsNone(queen["current"]["releasedAt"])
        self.assertEqual(queen["current"]["releaseStatus"], "pending")
        self.assertEqual(queen["2023-10-18"]["nativeTagUpdates"], [{"id": 791, "value": 1, "name": "속공"}])
        self.assertEqual(queen["2023-10-18"]["nativeRawText"], queen["current"]["nativeRawText"])

        sentinel = BUILD.load(ROOT / "data" / "UNG_926.json")
        initial = sentinel["2017-04-07"]
        self.assertNotIn("race", initial)
        self.assertNotIn("races", initial)
        self.assertNotIn(200, BUILD.native_tag_values(initial))
        card = BUILD.normalize_date_keyed_source(sentinel, {"id": "UNG_926", "releasedAt": "2017-04-07"})
        _, states = BUILD.replay_forward_states(card, "UNG_926")
        self.assertEqual(states[0].get("race"), None)
        self.assertEqual(states[-1]["race"], "드레나이")
        self.assertEqual(states[-1]["races"], ["DRAENEI"])
        self.assertEqual(BUILD.native_tag_values(states[-1])[200], 2)



    def test_remaining_twenty_four_ungoro_initial_states_and_dated_tag_boundaries(self):
        ids = (
            "UNG_004", "UNG_028", "UNG_116", "UNG_834", "UNG_854", "UNG_916",
            "UNG_922t1", "UNG_933", "UNG_934", "UNG_937", "UNG_940", "UNG_942",
            "UNG_952", "UNG_953", "UNG_954", "UNG_954t1", "UNG_957", "UNG_957t1",
            "UNG_961", "UNG_962", "UNG_963", "UNG_999t2", "UNG_999t5", "UNG_999t6",
        )
        baseline = BUILD.load(ROOT / "sources" / "carddefs-18336-baseline.json")
        catalog = BUILD.load(ROOT / "cards.json")
        records = {x["id"]: x for x in catalog["cards"]}
        self.assertEqual(len(ids), 24)
        for cid in ids:
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertEqual(source["schemaVersion"], 2, cid)
            self.assertEqual(source["dbfId"], records[cid]["dbfId"], cid)
            initial_day = "2017-04-04" if records[cid].get("releasedAt") is None else "2017-04-07"
            self.assertEqual(
                source[initial_day]["nativeTags"],
                [x for x in baseline["cards"][cid]["state"]["nativeTags"] if x["id"] != 183],
                cid,
            )
            self.assertEqual(source["current"]["releasedAt"], records[cid].get("releasedAt"), cid)
            self.assertEqual(source["current"]["releaseStatus"], records[cid]["releaseStatus"], cid)

        expected = {
            "UNG_004": ("cost", 8, 7, 48, 7),
            "UNG_834": ("cost", 5, 4, 48, 4),
            "UNG_854": ("cost", 8, 7, 48, 7),
            "UNG_933": ("cost", 9, 7, 48, 7),
            "UNG_937": ("cost", 3, 2, 48, 2),
            "UNG_953": ("health", 2, 3, 45, 3),
            "UNG_954t1": ("attack", 5, 8, 47, 8),
            "UNG_957": ("attack", 3, 4, 47, 4),
            "UNG_957t1": ("attack", 6, 8, 47, 8),
            "UNG_962": ("cost", 4, 3, 48, 3),
            "UNG_963": ("cost", 5, 4, 48, 4),
        }
        for cid, (field, before, after, tag_id, tag_value) in expected.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            released = records[cid].get("releasedAt")
            card = BUILD.normalize_date_keyed_source(source, {"id": cid, "releasedAt": released})
            patches, states = BUILD.replay_forward_states(card, cid)
            self.assertEqual(states[0][field], before, cid)
            self.assertEqual(states[-1][field], after, cid)
            self.assertEqual(BUILD.native_tag_values(states[-1])[tag_id], tag_value, cid)

        for cid, old_count, new_count, day in (
            ("UNG_028", 6, 8, "2020-04-21"),
            ("UNG_116", 5, 4, "2023-10-18"),
            ("UNG_940", 7, 6, "2023-10-18"),
            ("UNG_942", 10, 8, "2023-10-18"),
            ("UNG_954", 6, 5, "2023-10-18"),
        ):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            initial_day = "2017-04-07"
            self.assertEqual(BUILD.native_tag_values(source[initial_day])[535], old_count, cid)
            event = source[day]
            self.assertEqual(next(x for x in event["nativeTagUpdates"] if x["id"] == 535)["value"], new_count, cid)
            card = BUILD.normalize_date_keyed_source(source, {"id": cid, "releasedAt": "2017-04-07"})
            _, states = BUILD.replay_forward_states(card, cid)
            self.assertEqual(BUILD.native_tag_values(states[0])[535], old_count, cid)
            self.assertEqual(BUILD.native_tag_values(states[-1])[535], new_count, cid)
        self.assertNotIn("2023-10-18", BUILD.load(ROOT / "data" / "UNG_934.json"))

        exact_texts = {
            "UNG_004": "하수인의 능력치를 7/14로 만듭니다.",
            "UNG_834": "하수인에게 피해를 $3 줍니다. 1/1 테러닥스를 셋 소환하고 <b>적응</b>시킵니다.",
            "UNG_940": "<b>퀘스트:</b><br></br><b>죽음의 메아리</b> 하수인을 6회 소환해야 합니다.<br></br><b>보상:</b> 희망의 감시자 아마라",
            "UNG_942": "<b>퀘스트:</b> 멀록을 8마리 소환해야 합니다.<br></br><b>보상:</b> 대왕아가미",
            "UNG_954": "<b>퀘스트:</b><br></br>내 하수인에게 주문을 5회 시전해야 합니다.<br></br><b>보상:</b> 갈바돈",
            "UNG_957": "<b>도발</b>, <b>죽음의 메아리:</b><br></br><b>도발</b> 능력이 있는<br></br>8/12 공포뿔을 내 덱에 섞어 넣습니다.",
        }
        for cid, expected_text in exact_texts.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            day = "2020-04-21" if cid == "UNG_028" else "2023-10-18"
            if cid == "UNG_028":
                expected_text = "<b>퀘스트:</b> 게임이 시작됐을 때 내 덱에 없던 주문을 8회 시전해야 합니다.<br></br><b>보상:</b> 시간 왜곡"
            self.assertEqual(source[day]["text"], expected_text, cid)
            self.assertEqual(source[day]["nativeRawText"].count("\n"),
                             source[day]["text"].count("<br></br>"), cid)
        self.assertEqual(BUILD.load(ROOT / "data" / "UNG_004.json")["2023-10-18"]["nativeRawText"],
                         "하수인의 능력치를 7/14로 만듭니다.")
        self.assertEqual(BUILD.load(ROOT / "data" / "UNG_028.json")["sourceEvidence"]["2020-04-21"]["crossCheck"],
                         "https://www.inven.co.kr/board/hs/3508/16197?p=89")

        for cid in ("UNG_916", "UNG_922t1", "UNG_961"):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            day = "2017-04-04" if cid == "UNG_922t1" else "2017-04-07"
            self.assertEqual(source[day]["cost"], 1, cid)
            self.assertEqual(BUILD.native_tag_values(source[day])[48], 1, cid)
            self.assertEqual(source["2023-10-18"]["cost"], 0, cid)
            self.assertEqual(source["2023-10-18"]["nativeTagRemovals"], [48], cid)
            card = BUILD.normalize_date_keyed_source(source, {"id": cid, "releasedAt": records[cid].get("releasedAt")})
            _, states = BUILD.replay_forward_states(card, cid)
            self.assertEqual(states[-1]["cost"], 0, cid)
            self.assertNotIn(48, BUILD.native_tag_values(states[-1]), cid)

        quest_sources = {
            "UNG_028": "https://kr.forums.blizzard.com/ko/hearthstone/t/1737.json",
            "UNG_116": "https://hearthstone.blizzard.com/ko-kr/news/23989479",
            "UNG_940": "https://hearthstone.blizzard.com/ko-kr/news/23989479",
            "UNG_942": "https://hearthstone.blizzard.com/ko-kr/news/23989479",
            "UNG_954": "https://hearthstone.blizzard.com/ko-kr/news/23989479",
        }
        for cid, source_url in quest_sources.items():
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            day = "2020-04-21" if cid == "UNG_028" else "2023-10-18"
            self.assertEqual(source[day]["source"], source_url, cid)
        self.assertEqual(BUILD.load(ROOT / "data" / "UNG_952.json")["2025-03-19"]["cost"], 5)
        self.assertEqual(BUILD.load(ROOT / "data" / "UNG_952.json")["2025-03-19"]["source"],
                         "https://hearthstone.blizzard.com/ko-kr/news/24187196")

        storm = BUILD.load(ROOT / "data" / "UNG_940.json")
        self.assertNotIn(217, BUILD.native_tag_values(storm["2017-04-07"]))
        self.assertEqual(storm["2023-10-18"]["nativeTagUpdates"], [{"id": 535, "value": 6}])
        thorns = BUILD.load(ROOT / "data" / "UNG_952.json")
        self.assertNotIn(190, BUILD.native_tag_values(thorns["2017-04-07"]))
        self.assertNotIn(217, BUILD.native_tag_values(thorns["2017-04-07"]))
        self.assertEqual(thorns["2025-03-19"]["nativeTagUpdates"], [{"id": 48, "value": 5}])
        for cid, tag_id in (("UNG_934", 190), ("UNG_940", 217),
                            ("UNG_952", 190), ("UNG_952", 217),
                            ("UNG_999t2", 217), ("UNG_999t6", 190)):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertIn("nativeTags", source["historyIncompleteFields"], cid)
            self.assertTrue(any(x["field"] == "nativeTags" for x in source["unresolvedSourceFields"]), cid)

        liquid = BUILD.load(ROOT / "data" / "UNG_999t5.json")
        self.assertIn(311, BUILD.native_tag_values(liquid["2017-04-04"]))
        self.assertIn(332, BUILD.native_tag_values(liquid["2017-04-04"]))
        self.assertNotIn(1211, BUILD.native_tag_values(liquid["2017-04-04"]))
        self.assertIn("nativeTags[311,332,1211]",
                      [x["field"] for x in liquid["unresolvedSourceFields"]])
        self.assertEqual(liquid["nativeTagsTimelineStatus"], "partial")

        for cid in ("UNG_922t1", "UNG_954t1", "UNG_957t1", "UNG_999t2", "UNG_999t5", "UNG_999t6"):
            source = BUILD.load(ROOT / "data" / (cid + ".json"))
            self.assertIsNone(source["current"]["releasedAt"], cid)
            self.assertEqual(source["current"]["releaseStatus"], "pending", cid)


if __name__ == "__main__":
    unittest.main(verbosity=2)

