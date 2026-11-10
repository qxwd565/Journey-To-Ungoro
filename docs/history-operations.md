# History operation contract (schema 1)

Canonical dated card histories use forward events. An event has `date`, `changes`, and optional `remove`.

- A key omitted from both `changes` and `remove` is unchanged (inherit the previous value).
- A key in `changes` is assigned exactly as supplied. The values `0`, `false`, `null`, `""`, and `[]` are ordinary values and MUST NOT mean deletion.
- A key in `remove` is deleted from the state. It MUST NOT also occur in `changes`.
- A key may be removed only if it exists immediately before the event. Re-adding it later is an ordinary assignment.
- Empty `changes` is allowed only when `remove` is non-empty.
- Events are strictly increasing by Korean-local calendar date (Asia/Seoul).

The operation is canonical/editor-facing only. It is never copied verbatim to `cards.json`, `render.json`, or `history.json`. Existing consumers continue to receive the established sparse reverse-override history shape. If an old consumer cannot represent a removed field without changing semantics, that card/date is held out of compatibility publication and reported as blocked; no empty-value sentinel is synthesized.

Release policy distinguishes verified, estimated, and pending. Pending entries have `date: null`; candidate dates remain explanatory metadata and are never treated as playable dates.
