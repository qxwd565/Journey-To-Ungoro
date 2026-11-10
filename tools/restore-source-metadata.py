#!/usr/bin/env python3
"""Restore stable top-level card metadata from the pre-v2 source snapshot.

The baseline manifest is generated once from the immutable source commit and
then committed. Existing metadata is never overwritten: a conflicting value
fails loudly so that historical data is not silently replaced.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
MANIFEST_PATH = ROOT / "sources" / "card-metadata-baseline.json"
BASELINE_COMMIT = "9f603273aa2a03a57fe9066927090818ada4af31"
FIELDS = (
    "root",
    "relatedIds",
    "englishName",
    "expansion",
    "setOrder",
    "formats",
    "provenance",
    "mode",
)


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_baseline(card_id):
    url = (
        "https://raw.githubusercontent.com/qxwd565/Journey-To-Ungoro/"
        f"{BASELINE_COMMIT}/data/{card_id}.json"
    )
    request = Request(url, headers={"User-Agent": "HSdeck-Ungoro-metadata-restore"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    paths = sorted(DATA_DIR.glob("UNG_*.json"))
    if len(paths) != 185:
        raise RuntimeError(f"Expected exactly 185 Ungoro source files, found {len(paths)}")

    if MANIFEST_PATH.exists():
        manifest = load_json(MANIFEST_PATH)
        if manifest.get("sourceCommit") != BASELINE_COMMIT:
            raise RuntimeError("Metadata manifest references an unexpected baseline commit")
        baseline_cards = manifest.get("cards", {})
    else:
        def capture(path):
            card_id = path.stem
            baseline = read_baseline(card_id)
            if baseline.get("id") not in (None, card_id):
                raise RuntimeError(f"Baseline ID mismatch for {card_id}")
            return card_id, {
                field: baseline[field] for field in FIELDS if field in baseline
            }

        with ThreadPoolExecutor(max_workers=12) as pool:
            baseline_cards = dict(pool.map(capture, paths))
        manifest = {
            "schemaVersion": 1,
            "sourceCommit": BASELINE_COMMIT,
            "description": "Original stable top-level metadata captured before schemaVersion 2 migration.",
            "fields": list(FIELDS),
            "cards": baseline_cards,
        }
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if set(baseline_cards) != {path.stem for path in paths}:
        raise RuntimeError("Metadata manifest card IDs do not match the 185 current source files")

    restored = 0
    for path in paths:
        card_id = path.stem
        source = load_json(path)
        expected = baseline_cards[card_id]
        changed = False
        for field, value in expected.items():
            if field in source:
                if source[field] != value:
                    raise RuntimeError(
                        f"{card_id}.{field} conflicts with the original baseline; refusing to overwrite"
                    )
            else:
                source[field] = value
                changed = True
                restored += 1
        if changed:
            path.write_text(
                json.dumps(source, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    print(
        f"Metadata baseline verified for {len(paths)} cards; "
        f"restored {restored} missing fields."
    )


if __name__ == "__main__":
    main()
