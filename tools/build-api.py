#!/usr/bin/env python3
"""Publish HScard API indexes from canonical per-card JSON.

Source of current card metadata: cards.json (generated current catalogue).
Source of gameplay specs: data/<cardId>.json (release baseline + card.patches).
Legacy reverse-only card.history is accepted temporarily during migration.
Historically introduced races/spell schools are dated in taxonomy-history.json,
materialized as sparse card.history overrides, and published for date lookup.
Never overwrite curated current data with raw client snapshots.
Card release dates are loaded from release-policy.json (Asia/Seoul).


Generated endpoints:
  cards.json   - current cards for WP JSON imports
  render.json  - current cards + sparse history for WebGL and WordPress
  history.json - temporary compatibility endpoint for installed 7.12.10 sites

Do not hand-edit the generated indexes. Do not change cardId/dbfId mappings.
The separate history endpoint is retained only until old WordPress plugins are upgraded.
"""
from __future__ import annotations
import copy
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_FIELDS = (
    "id", "dbfId", "name", "type", "cardClass", "rarity", "collectible",
    "cost", "text", "attack", "health", "durability", "armor", "art",
    "races", "race", "spellSchool", "set", "nativeTags", "mechanics",
    "watermark", "classes",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SPEC_FIELDS = (
    "name", "type", "cardClass", "classes", "rarity", "collectible",
    "cost", "attack", "health", "durability", "armor", "text",
    "races", "race", "spellSchool", "mechanics", "nativeTags",
)
HISTORY_ONLY_FIELDS = ("nativeRawText", "nativeTextBuilder")
PATCH_FIELDS = SPEC_FIELDS + HISTORY_ONLY_FIELDS
PATCH_FIELD_SET = set(PATCH_FIELDS)
TAXONOMY_RULE = "taxonomy-introduction"
RACE_KOREAN = {
    "BEAST": "야수", "DEMON": "악마", "DRAGON": "용족", "MURLOC": "멀록",
    "PIRATE": "해적", "TOTEM": "토템", "MECHANICAL": "기계", "MECH": "기계",
    "ELEMENTAL": "정령", "QUILBOAR": "가시멧돼지", "UNDEAD": "언데드",
    "DRAENEI": "드레나이", "NAGA": "나가",
}

# Hearthstone GameTag enum values, cross-checked against HearthSim/python-hearthstone.
# Preserve numeric tags in source; these maps only validate/derive display fields.
RARITY_BY_TAG = {1: "COMMON", 2: "FREE", 3: "RARE", 4: "EPIC", 5: "LEGENDARY"}
CLASS_BY_TAG = {
    2: "DRUID", 3: "HUNTER", 4: "MAGE", 5: "PALADIN", 6: "PRIEST",
    7: "ROGUE", 8: "SHAMAN", 9: "WARLOCK", 10: "WARRIOR",
    12: "NEUTRAL", 14: "DEMONHUNTER",
}
CARD_TYPE_BY_TAG = {
    3: "HERO", 4: "MINION", 5: "SPELL", 6: "ENCHANTMENT",
    7: "WEAPON", 10: "HERO_POWER",
}
RACE_BY_TAG = {
    1: "BLOODELF", 2: "DRAENEI", 3: "DWARF", 4: "GNOME", 5: "GOBLIN",
    6: "HUMAN", 7: "NIGHTELF", 8: "ORC", 9: "TAUREN", 10: "TROLL",
    11: "UNDEAD", 12: "WORGEN", 13: "GOBLIN", 14: "MURLOC",
    15: "DEMON", 16: "SCOURGE", 17: "MECHANICAL", 18: "ELEMENTAL",
    19: "OGRE", 20: "BEAST", 21: "TOTEM", 22: "NERUBIAN",
    23: "PIRATE", 24: "DRAGON", 25: "BLANK", 26: "ALL", 38: "EGG",
}
RACE_LABEL_BY_TAG = {
    1: "블러드엘프", 2: "드레나이", 3: "드워프", 4: "노움", 5: "고블린",
    6: "인간", 7: "나이트 엘프", 8: "오크", 9: "타우렌", 10: "트롤",
    11: "언데드", 12: "늑대인간", 13: "고블린", 14: "멀록",
    15: "악마", 16: "스컬지", 17: "기계", 18: "정령", 19: "오우거",
    20: "야수", 21: "토템", 22: "네루비안", 23: "해적", 24: "용족",
    25: "공백", 26: "모두", 38: "알",
}
SPELL_SCHOOL_BY_TAG = {
    1: "ARCANE", 2: "FIRE", 3: "FROST", 4: "NATURE",
    5: "HOLY", 6: "SHADOW", 7: "FEL",
}


def native_tag_values(card: dict) -> dict[int, int]:
    return {item["id"]: item["value"] for item in card.get("nativeTags", [])
            if isinstance(item, dict) and isinstance(item.get("id"), int)
            and isinstance(item.get("value"), int)}


def validate_baseline_enum_mappings(baseline: dict) -> dict:
    """Reject derived CardDefs labels that disagree with their preserved numeric tags."""
    counts = {"cards": 0, "rarity": 0, "race": 0, "cardClass": 0, "type": 0}
    for cid, entry in baseline.get("cards", {}).items():
        state = entry.get("state", {})
        tags = native_tag_values(state)
        counts["cards"] += 1
        for field, tag_id, mapping in (
            ("rarity", 203, RARITY_BY_TAG),
            ("cardClass", 199, CLASS_BY_TAG),
            ("type", 202, CARD_TYPE_BY_TAG),
        ):
            expected = mapping.get(tags.get(tag_id))
            if expected is not None and field in state:
                if state[field] != expected:
                    raise ValueError(
                        f"{cid}: CardDefs {field}={state[field]!r} disagrees with "
                        f"TAG {tag_id}={tags[tag_id]} (expected {expected!r})"
                    )
                counts[field] += 1
        expected_race = RACE_LABEL_BY_TAG.get(tags.get(200))
        if expected_race is not None and state.get("race") not in (None, "", expected_race):
            raise ValueError(
                f"{cid}: CardDefs race={state['race']!r} disagrees with "
                f"CARDRACE={tags[200]} (expected {expected_race!r})"
            )
        expected_races = [RACE_BY_TAG[tags[200]]] if tags.get(200) in RACE_BY_TAG else []
        if tags.get(200) in RACE_BY_TAG and "races" in state and state.get("races", []) != expected_races:
            raise ValueError(
                f"{cid}: CardDefs races={state.get('races')!r} disagrees with "
                f"CARDRACE={tags.get(200)!r} (expected {expected_races!r})"
            )
        if expected_race is not None and state.get("race"):
            counts["race"] += 1
    return counts


def validate_current_enum_mappings(records: list[dict]) -> dict:
    """Cross-check current derived fields against their retained raw enum tags."""
    counts = {"cards": 0, "rarity": 0, "race": 0, "cardClass": 0, "type": 0, "spellSchool": 0}
    for card in records:
        counts["cards"] += 1
        tags = native_tag_values(card)
        for field, tag_id, mapping in (
            ("rarity", 203, RARITY_BY_TAG),
            ("cardClass", 199, CLASS_BY_TAG),
            ("type", 202, CARD_TYPE_BY_TAG),
            ("spellSchool", 1635, SPELL_SCHOOL_BY_TAG),
        ):
            expected = mapping.get(tags.get(tag_id))
            if expected is not None and field in card:
                if card[field] != expected:
                    raise ValueError(
                        f"{card['id']}: current {field}={card[field]!r} disagrees "
                        f"with TAG {tag_id}={tags[tag_id]} (expected {expected!r})"
                    )
                counts[field] += 1
        race_code = RACE_BY_TAG.get(tags.get(200))
        if race_code is not None:
            races = card.get("races", [])
            if races and race_code not in races:
                raise ValueError(
                    f"{card['id']}: current races={races!r} omits "
                    f"CARDRACE={tags[200]} ({race_code})"
                )
            expected_label = RACE_LABEL_BY_TAG.get(tags.get(200))
            if expected_label and card.get("race"):
                labels = [part.strip() for part in card["race"].split(",")]
                if expected_label not in labels:
                    raise ValueError(
                        f"{card['id']}: current race={card['race']!r} disagrees "
                        f"with CARDRACE={tags[200]} (expected {expected_label!r})"
                    )
            counts["race"] += 1
    return counts


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_display_text(card_id: str, value):
    """Normalize display text only; never rewrite nativeRawText or JSON layout."""
    if not isinstance(value, str):
        return value
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\n", "<br></br>")
    value = value.replace("\\n", "<br></br>")
    if card_id == "UNG_063":
        value = value.replace("+1/+1를 얻습니다.", "+1/+1을 얻습니다.")
    return value


def normalize_card_display(card_id: str, card: dict, revisions: list[dict] | None = None):
    if "text" in card:
        card["text"] = normalize_display_text(card_id, card["text"])
    for event in card.get("patches", []):
        changes = event.get("changes", {})
        if "text" in changes:
            changes["text"] = normalize_display_text(card_id, changes["text"])
    for revision in revisions or []:
        changes = revision.get("changes", {})
        if "text" in changes:
            changes["text"] = normalize_display_text(card_id, changes["text"])


def publish(path: Path, value):
    # Runtime catalogues are compact; the editor-facing catalog stays readable.
    if path.name in ("render.json", "history.json"):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def read_history(card: dict, name: str):
    versions = card.get("history", [])
    if versions is None:
        return []
    if not isinstance(versions, list):
        raise ValueError(f"{name}: history must be an array")
    for rev in versions:
        if not isinstance(rev, dict) or not isinstance(rev.get("changes"), dict):
            raise ValueError(f"{name}: invalid history entry")
        if not rev["changes"] or not any(x in rev for x in ("from", "before")):
            raise ValueError(f"{name}: history has no changes or date boundary")
        if any(k in rev and (not isinstance(rev[k], str) or not DATE_RE.fullmatch(rev[k])) for k in ("from", "before")):
            raise ValueError(f"{name}: invalid history date")
        if all(k in rev for k in ("from", "before")) and rev["from"] >= rev["before"]:
            raise ValueError(f"{name}: invalid history interval")
    return versions


def normalize_date_keyed_source(data: dict, record: dict):
    """Adapt date-keyed source records to the common history replay model."""
    cid = record["id"]
    date_keys = sorted(key for key in data if DATE_RE.fullmatch(key))
    if not date_keys:
        raise ValueError(f"{cid}: date-keyed source has no initial snapshot")
    initial = data[date_keys[0]]
    if not isinstance(initial, dict):
        raise ValueError(f"{cid}: invalid initial date snapshot")
    patches = []
    patch_sources = {}
    patch_confidence = {}
    patch_notes = {}
    metadata_keys = {"source", "confidence", "note", "remove", "status"}
    for day in date_keys[1:]:
        event = data[day]
        if not isinstance(event, dict):
            raise ValueError(f"{cid}: invalid date event {day}")
        changes = {key: copy.deepcopy(value) for key, value in event.items()
                   if key not in metadata_keys}
        patch = {"date": day, "changes": changes}
        if "remove" in event:
            patch["remove"] = copy.deepcopy(event["remove"])
        if "source" in event:
            patch_sources[day] = copy.deepcopy(event["source"])
        if "confidence" in event:
            patch_confidence[day] = copy.deepcopy(event["confidence"])
        if "note" in event:
            patch_notes[day] = copy.deepcopy(event["note"])
        patches.append(patch)
    current_cache = data.get("current", {})
    if not isinstance(current_cache, dict):
        raise ValueError(f"{cid}: current cache must be an object")
    current_reference_tags = data.get("currentReferenceTags", [])
    if not isinstance(current_reference_tags, list) or any(not isinstance(x, dict) or not isinstance(x.get("id"), int) for x in current_reference_tags):
        raise ValueError(f"{cid}: currentReferenceTags must be an array of tag objects")
    card = copy.deepcopy(initial)
    card.update({
        "id": data.get("id"),
        "dbfId": data.get("dbfId"),
        "releasedAt": record.get("releasedAt"),
        "patches": patches,
        "patchSources": patch_sources,
        "patchConfidence": patch_confidence,
        "patchNotes": patch_notes,
        "currentCache": current_cache,
        "currentReferenceTags": current_reference_tags,
        "historyIncompleteFields": data.get("historyIncompleteFields", []),
        "historyKnownFields": data.get("historyKnownFields", []),
        "nativeTagsTimelineStatus": data.get("nativeTagsTimelineStatus", "partial"),
    })
    return card


def read_catalog_source(path: Path, record: dict):
    if not path.is_file():
        return None, None, False
    data = load(path)
    cid = record["id"]
    if not isinstance(data, dict):
        raise ValueError(f"{cid}: source document must be an object")
    if data.get("schemaVersion") == 2:
        if data.get("id") != cid or data.get("dbfId") != record.get("dbfId"):
            raise ValueError(f"{cid}: date-keyed source identity mismatch")
        return data, normalize_date_keyed_source(data, record), True
    card = data.get("card")
    if not isinstance(card, dict) or card.get("id") != cid:
        raise ValueError(f"{cid}: source card ID mismatch")
    # A separately archived native token is not an asserted DBF mapping. Keep
    # the approved current catalog, but never attach its archived history to a
    # numeric ID or manufacture a DBF ID in the source document.
    if card.get("dbfId") is None and data.get("apiAvailability", "").startswith("standalone historical source;"):
        return None, None, False
    if card.get("dbfId") != record.get("dbfId"):
        raise ValueError(f"{cid}: source card ID mismatch")
    return data, card, False


def release_for_card(record: dict, policy: dict):
    """Korean-local first playable date; unknown dates are never invented."""
    cid = record["id"]
    rule = policy.get("default", {"date": None, "status": "pending"})
    for prefix in sorted(policy.get("prefixes", {}), key=len, reverse=True):
        if cid.startswith(prefix):
            rule = policy["prefixes"][prefix]
            break
    rule = policy.get("cards", {}).get(cid, rule)
    if not isinstance(rule, dict):
        raise ValueError(f"Invalid release policy for {cid}")
    day = rule.get("date")
    status = rule.get("status", "pending" if day is None else "verified")
    if day is not None:
        if not isinstance(day, str) or not DATE_RE.fullmatch(day):
            raise ValueError(f"{cid}: invalid Korean release date")
        from datetime import date
        date.fromisoformat(day)
    if status not in ("verified", "estimated", "pending"):
        raise ValueError(f"{cid}: invalid release confidence")
    if status == "verified" and not day:
        raise ValueError(f"{cid}: verified date cannot be null")
    return day, status



def read_taxonomy_policy(path: Path):
    """Load calendar-day feature introduction dates, recorded in Asia/Seoul."""
    if not path.exists():
        return None
    policy = load(path)
    if policy.get("schema") != 1 or policy.get("timezone") != "Asia/Seoul":
        raise ValueError("taxonomy-history.json must use schema 1 and Asia/Seoul")
    from datetime import date
    for key in ("minionTypes", "spellSchools"):
        rules = policy.get(key)
        if not isinstance(rules, dict):
            raise ValueError(f"taxonomy-history.json: {key} must be a map")
        for kind, day in rules.items():
            if not isinstance(kind, str) or not isinstance(day, str) or not DATE_RE.fullmatch(day):
                raise ValueError(f"Invalid {key} introduction: {kind}")
            date.fromisoformat(day)
    overrides = policy.get("cardTypeIntroductions", {})
    if not isinstance(overrides, dict):
        raise ValueError("cardTypeIntroductions must be a map")
    for cid, rules in overrides.items():
        if not isinstance(rules, dict):
            raise ValueError(f"{cid}: cardTypeIntroductions must contain a map")
        for tribe, day in rules.items():
            if not isinstance(day, str) or not DATE_RE.fullmatch(day):
                raise ValueError(f"{cid}: invalid tribe date {tribe}")
            date.fromisoformat(day)
    older = policy.get("priorRaces", {})
    if not isinstance(older, dict) or any(not isinstance(k, str) or not isinstance(v, list)
                                           or any(not isinstance(r, str) for r in v)
                                           for k, v in older.items()):
        raise ValueError("priorRaces must be a map of card IDs to race lists")
    return policy


def historic_race_label(original: str, remaining: list[str]) -> str:
    """Keep the existing original/Korean label when it still identifies a surviving type."""
    if not remaining:
        return ""
    if original in remaining or original in (RACE_KOREAN.get(t) for t in remaining):
        return original
    return RACE_KOREAN.get(remaining[0], remaining[0]) if original in RACE_KOREAN.values() else remaining[0]


def taxonomy_revisions(record: dict, release_day: str | None, policy: dict) -> list[dict]:
    """Sparse past overrides. Latest boundary first so the oldest state wins when overlapping."""
    minion_types = policy["minionTypes"]
    spell_schools = policy["spellSchools"]
    races = record.get("races") if record.get("type") == "MINION" else []
    races = races if isinstance(races, list) else []
    # A card can acquire an existing tribe years after the tribe first debuted.
    per_card = policy.get("cardTypeIntroductions", {}).get(record["id"], {})
    race_dates = {race: per_card.get(race, minion_types.get(race)) for race in races}
    previous_races = policy.get("priorRaces", {}).get(record["id"], [])
    spell = record.get("spellSchool") if record.get("type") == "SPELL" else None
    boundaries = set()

    for race in races:
        day = race_dates.get(race)
        if day and (not release_day or release_day < day):
            boundaries.add(day)
    spell_day = spell_schools.get(spell) if isinstance(spell, str) else None
    if spell_day and (not release_day or release_day < spell_day):
        boundaries.add(spell_day)

    revisions = []
    for before in sorted(boundaries, reverse=True):
        changes = {}
        older_races = [race for race in races
                       if not (race_dates.get(race) and before <= race_dates[race])]
        # Older source records can retain the original Korean tribe label in
        # race while omitting it from the current races list. Preserve it.
        for race in reversed(previous_races):
            if race not in older_races:
                older_races.insert(0, race)
        if older_races != races:
            changes["races"] = older_races
            changes["race"] = historic_race_label(record.get("race") or "", older_races)
        if spell_day and before <= spell_day:
            changes["spellSchool"] = ""
        if changes:
            revisions.append({
                "before": before,
                "changes": changes,
                "generatedBy": TAXONOMY_RULE,
            })
    return revisions



def read_patches(card: dict, name: str) -> list[dict]:
    """Validate that each dated patch only stores changed gameplay fields."""
    patches = card.get("patches")
    if not isinstance(patches, list):
        raise ValueError(f"{name}: patches must be an array")
    prev = card.get("releasedAt")
    for event in patches:
        if not isinstance(event, dict) or set(event) - {"date", "changes", "remove"} or not {"date", "changes"} <= set(event):
            raise ValueError(f"{name}: invalid forward patch shape")
        day, changes = event["date"], event["changes"]
        remove = event.get("remove", [])
        if not isinstance(remove, list) or any(not isinstance(k, str) for k in remove) or len(remove) != len(set(remove)):
            raise ValueError(f"{name}: remove must be a unique list of field names")
        if not isinstance(changes, dict) or any(not isinstance(k, str) for k in changes):
            raise ValueError(f"{name}: changes must be an object")
        if set(changes) & set(remove):
            raise ValueError(f"{name}: a field cannot be assigned and removed together")
        if not isinstance(day, str) or not DATE_RE.fullmatch(day):
            raise ValueError(f"{name}: invalid patch date")
        from datetime import date
        date.fromisoformat(day)
        if prev is not None and day <= prev:
            raise ValueError(f"{name}: overlapping/unsorted patch dates {prev}, {day}")
        if not changes and not remove:
            raise ValueError(f"{name}: empty operation on {day}")
        if (set(changes) | set(remove)) - (PATCH_FIELD_SET | {"legacyArt"}):
            raise ValueError(f"{name}: unknown gameplay patch field")
        prev = day
    return patches


def normalize_history_cache(cache: dict):
    """Drop legacy zero/empty placeholders only from historical comparisons."""
    result = copy.deepcopy(cache)
    card_type = result.get("type")
    omit = set()
    if card_type == "MINION":
        omit.update(("armor", "durability"))
    elif card_type in {"SPELL", "HERO_POWER"}:
        omit.update(("attack", "health", "armor", "durability", "race", "races"))
    elif card_type == "WEAPON":
        omit.update(("health", "armor", "race", "races"))
    for field in omit:
        result.pop(field, None)
    for field, empty in (("race", ""), ("races", []), ("spellSchool", ""), ("classes", [])):
        if result.get(field) == empty:
            result.pop(field, None)
    return result


def publish_forward_card(card: dict, current: dict, name: str):
    """Replay dated source and publish only reversible, date-supported history."""
    patches = read_patches(card, name)
    base = {field: copy.deepcopy(card[field]) for field in PATCH_FIELDS if field in card}
    if "legacyArt" in card:
        base["legacyArt"] = card["legacyArt"]
    states = [base]
    for event in patches:
        next_state = copy.deepcopy(states[-1])
        for field in event.get("remove", []):
            if field not in next_state:
                raise ValueError(f"{name}: cannot remove absent field {field} on {event['date']}")
            del next_state[field]
        for field, value in event["changes"].items():
            if field in next_state and next_state[field] == value:
                raise ValueError(f"{name}: redundant patch for {field} on {event['date']}")
            next_state[field] = copy.deepcopy(value)
        states.append(next_state)
    latest = states[-1]
    current_cache = card.get("currentCache")
    unresolved = set(card.get("historyIncompleteFields", []))
    history_known_fields = set(card.get("historyKnownFields", []))
    if not history_known_fields.issubset(PATCH_FIELD_SET):
        raise ValueError(f"{name}: historyKnownFields contains an unsupported field")
    if current_cache is not None and not isinstance(current_cache, dict):
        raise ValueError(f"{name}: currentCache must be an object")
    effective_latest = normalize_history_cache(current_cache) if current_cache is not None else latest
    reference_ids = {x["id"] for x in card.get("currentReferenceTags", [])}
    if reference_ids and isinstance(effective_latest.get("nativeTags"), list):
        effective_latest["nativeTags"] = [
            tag for tag in effective_latest["nativeTags"] if tag.get("id") not in reference_ids
        ]
    for field in SPEC_FIELDS:
        if current_cache is not None:
            if field in current_cache:
                current[field] = copy.deepcopy(current_cache[field])
            else:
                current.pop(field, None)
        elif field in latest:
            current[field] = copy.deepcopy(latest[field])
        else:
            current.pop(field, None)
        if (field in latest) != (field in effective_latest):
            unresolved.add(field)
        elif field in latest and latest[field] != effective_latest[field]:
            unresolved.add(field)
    if current_cache is not None and card.get("nativeTagsTimelineStatus") != "complete":
        unresolved.add("nativeTags")
    backward = []
    compatibility_blocked = []
    for i, event in enumerate(patches):
        old = states[i]
        added_now = sorted((set(states[i + 1]) - set(old)) & set(SPEC_FIELDS))
        if added_now:
            compatibility_blocked.append({"date": event["date"], "fields": added_now})
        incomplete = sorted((set(effective_latest) - set(old)) & set(SPEC_FIELDS))
        differences = {
            field: copy.deepcopy(value) for field, value in old.items()
            if field in SPEC_FIELDS
            and (field not in unresolved or field in history_known_fields)
            and (field not in effective_latest or value != effective_latest[field])
        }
        if not differences:
            continue
        start = card.get("releasedAt") if i == 0 else patches[i - 1]["date"]
        revision = {"before": event["date"], "changes": differences}
        if incomplete:
            revision["incompleteFields"] = incomplete
        if start:
            revision["from"] = start
        backward.append(revision)
    incomplete_fields = sorted(unresolved | {
        field for item in compatibility_blocked for field in item["fields"]
    })
    return backward, compatibility_blocked, incomplete_fields

def main():
    source_path = ROOT / "cards.json"
    catalog = load(source_path)
    if catalog.get("schema") != 1 or not isinstance(catalog.get("cards"), list):
        raise ValueError("Unexpected cards.json schema")
    detailed = ROOT / "data"
    baseline_path = ROOT / "sources" / "carddefs-18336-baseline.json"
    if baseline_path.exists():
        validate_baseline_enum_mappings(load(baseline_path))
    validate_current_enum_mappings(catalog["cards"])
    release_policy_path = ROOT / "release-policy.json"
    release_policy = load(release_policy_path) if release_policy_path.exists() else None
    taxonomy_policy = read_taxonomy_policy(ROOT / "taxonomy-history.json")
    if release_policy is not None and release_policy.get("timezone") != "Asia/Seoul":
        raise ValueError("Release dates must use Korea (Asia/Seoul)")
    release_counts = {"verified": 0, "estimated": 0, "pending": 0}
    changed_individual = 0
    compatibility_blocked = []
    history = {}
    renderer = []
    seen = set()
    for record in catalog["cards"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError("Invalid card in cards.json")
        cid = record["id"]
        if cid in seen:
            raise ValueError(f"Duplicate card ID {cid}")
        seen.add(cid)
        release_date = release_for_card(record, release_policy)[0] if release_policy is not None else record.get("releasedAt")
        path = detailed / (cid + ".json")
        data, card, date_keyed = read_catalog_source(path, record)
        revisions = []
        incomplete_fields = []
        if data is None:
            if record.get("history"):
                raise ValueError(f"{cid}: historical data requires {path.name}")
            # Preserve cards that have no detailed source yet.
            record.pop("history", None)
        else:
            if not date_keyed:
                card = data["card"]
            # The date-keyed source owns history; cards.json remains the current cache.
            if "patches" in card:
                if "history" in card:
                    raise ValueError(f"{cid}: forward patches cannot coexist with legacy reverse history")
                revisions, blocked, incomplete_fields = publish_forward_card(card, record, cid)
                if blocked:
                    compatibility_blocked.append({"id": cid, "events": blocked})
            else:
                # Transitional support for un-migrated cards only.
                revisions = read_history(card, cid)
                if taxonomy_policy is not None:
                    curated = [rev for rev in revisions if rev.get("generatedBy") != TAXONOMY_RULE]
                    revisions = curated + taxonomy_revisions(record, release_date, taxonomy_policy)
                    if revisions != card.get("history", []):
                        card["history"] = revisions
                    revisions = read_history(card, cid)
            if revisions:
                incomplete = sorted(set(incomplete_fields) | {
                    field for item in compatibility_blocked if item["id"] == cid
                    for event in item["events"] for field in event["fields"]
                })
                history_entry = {"id": cid, "history": revisions}
                if incomplete:
                    history_entry["incompleteFields"] = incomplete
                history[str(record["dbfId"])] = history_entry
            elif record.get("history"):
                # Avoid silently discarding previously migrated patches.
                raise ValueError(f"{cid}: history exists in cards.json but not data/{cid}.json")
            record.pop("history", None)
        if data is not None:
            normalize_card_display(cid, card, revisions)
        if "text" in record:
            record["text"] = normalize_display_text(cid, record["text"])
        render_card = {field: record[field] for field in RENDER_FIELDS if field in record}
        # A single runtime endpoint: the current card and its sparse dated
        # differences are delivered together. Absence of history means current.
        if data is not None and revisions:
            render_card["history"] = revisions
        if incomplete_fields:
            render_card["historyIncompleteFields"] = incomplete_fields
        incomplete = sorted(set(incomplete_fields) | {
            field for item in compatibility_blocked if item["id"] == cid
            for event in item["events"] for field in event["fields"]
        })
        if incomplete:
            render_card["historyIncompleteFields"] = incomplete
        if release_policy is not None:
            release_date, release_status = release_for_card(record, release_policy)
            record["releasedAt"] = release_date
            record["releaseStatus"] = release_status
            render_card["releasedAt"] = release_date
            # Consumers must not hide cards based on an estimated release date.
            render_card["releaseStatus"] = release_status
            release_counts[release_status] += 1
            if data is not None:
                if date_keyed:
                    data["current"]["releasedAt"] = release_date
                    data["current"]["releaseStatus"] = release_status
                else:
                    card["releasedAt"] = release_date
                    card["releaseStatus"] = release_status
                if publish(path, data):
                    changed_individual += 1
        renderer.append(render_card)

    files = {
        "cards.json": catalog,
        "render.json": {"schema": 1, "set": catalog["set"], "cards": renderer},
        "history.json": {"schema": 1, "set": catalog["set"], "cards": history},
    }
    changed = [name for name, value in files.items() if publish(ROOT / name, value)]
    print(json.dumps({
        "set": catalog["set"], "cards": len(renderer),
        "datedCards": len(history),
        "published": changed, "releaseDates": release_counts,
        "individualCardsUpdated": changed_individual,
        "compatibilityBlocked": compatibility_blocked,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
