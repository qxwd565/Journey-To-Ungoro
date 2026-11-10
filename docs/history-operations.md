# History operation contract (schema 1)

Canonical dated card histories use forward events with `date`, `changes`, and optional `remove`.

- Omitted keys inherit the previous state.
- Keys in `changes` are assigned exactly, including `0`, `false`, `null`, `""`, and `[]`.
- Keys in `remove` are deleted. A key cannot appear in both operations; removing an absent key is invalid.
- An event must contain at least one assignment or removal. Dates are strictly increasing Korea-local calendar dates (Asia/Seoul).
- The allow-list includes gameplay fields and the native tag/raw-text fields required for historical taxonomy reconstruction.

This is a canonical internal format only. The builder does not expose `remove` to existing consumers. Reverse-override compatibility can represent value changes, but not a field that existed in the latest object and was absent in an earlier state. Such card/date histories are reported under `compatibilityBlocked` and omitted from legacy history publication rather than encoded as null, empty string, zero, or an empty array. Current card metadata remains published.

Release-policy entries with `status: pending` and `date: null` are not playable dates. Candidate dates are explanatory only.
