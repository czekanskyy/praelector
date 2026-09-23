# @praelector/schemas

Everything in `src/` is **generated**. Do not edit it by hand.

```sh
just codegen          # regenerate src/json/** and src/generated/**
just codegen-check    # fail if the committed output is stale
```

`scripts/gen_ts_types.py` imports the engine's Pydantic models, calls
`model_json_schema()` on each entry in its `EXPORTS` list, writes one JSON Schema
per model into `src/json/`, and emits TypeScript into `src/generated/`.

CI regenerates and fails on a diff (`ci-ui.yml`), so `apps/ui` can never drift
from the engine contract. The engine tree is required: this package produces
nothing until `engine/` exists.

## Layout

| Path | Content |
| --- | --- |
| `src/json/` | one JSON Schema per exported model, plus `index.json` |
| `src/generated/` | TypeScript types consumed by `apps/ui` |
