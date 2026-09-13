# Praelector — project pack

| File                                               | What it is                                              |
| -------------------------------------------------- | ------------------------------------------------------- |
| [00_ZAMYSL_Praelector.md](00_ZAMYSL_Praelector.md) | Product concept (Polish)                                |
| [PRD.md](PRD.md)                                   | Product requirements — source of truth for v1 (English) |
| [CODING_AGENT_PROMPT.md](CODING_AGENT_PROMPT.md)   | Prompt to paste into a planning/coding agent            |
| [docs/plan/](docs/plan/)                           | Implementation plan (English)                           |

Implementation plan:

| File                                                     | What it is                                                  |
| -------------------------------------------------------- | ----------------------------------------------------------- |
| [docs/plan/PLAN.md](docs/plan/PLAN.md)                   | Architecture, decisions, milestones M0–M6, risks, PR sequence |
| [docs/plan/REPO_LAYOUT.md](docs/plan/REPO_LAYOUT.md)     | Monorepo tree with responsibilities per folder               |
| [docs/plan/DATA_MODEL.md](docs/plan/DATA_MODEL.md)       | SQLite + JSON entities and invariants                        |
| [docs/plan/OPENAPI_SKETCH.md](docs/plan/OPENAPI_SKETCH.md) | Sidecar HTTP/WS endpoints for v1                           |
| [docs/plan/CI_AND_RELEASE.md](docs/plan/CI_AND_RELEASE.md) | Workflows, branch rules, release artifacts                 |
| [docs/plan/SEQUENCES.md](docs/plan/SEQUENCES.md)         | Mermaid flows: ingest → suggestions → TTS → mux              |

Next step: review `docs/plan/PLAN.md`, then implement milestone M0 starting with PR 1 of `PLAN.md` §14.
