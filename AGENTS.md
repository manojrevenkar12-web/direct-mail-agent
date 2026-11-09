# AGENTS.md

How to work in this repository, for people and coding agents.

## Fast feedback

```bash
make lint        # ruff
make test        # all Python tests, dbt on DuckDB included (about 15 seconds)
make web-test    # the approval console: tsc, vitest, vite build
make demo        # three rounds on a small market, printed
make dev         # the development split (about 5 minutes); tune here
make lock-check  # the held-out lock still verifies
make report      # RESULTS.md and the console's data from reports/*.json
```

## Invariants (tests enforce them)

1. **The agent never sees the truth.** `mailworld` simulates the market, the people and the model's mistakes and
   keeps the truth; `mail_eval` scores against it. Nothing under `src/agentrt` or `src/mailagent` imports either
   (`test_isolation.py`).
2. **The model reads; code decides; a person approves.** The model reads the team mailbox, triages anomalies and
   writes the brief. Suppressions, selection, budget and file checks are code. A direction applies only if its
   sender is authenticated and has authority for it, and its figure is in the sentence it quotes
   (`test_directives.py`). The printer gets a file only with a valid approval of that file's sha256, from the right
   role, and never twice (`test_agent_round.py`).
3. **The model never sees a company.** Its context is aggregates and settings (`test_isolation.py`).
4. **One suppression definition.** `config/suppressions.yaml` compiles to numpy for the agent and to SQL for the
   warehouse (`warehouse/models/mail_universe.sql`, generated); a test proves they agree on every company, and
   another runs `dbt build` on DuckDB.
5. **Objections always reach operations.** A rule finds them as well as the model.
6. **Every decision has a reason.** The decision record is hash-chained; editing an entry breaks `verify()`.
7. **Settings in config.** Limits and learning in `config/agent.toml`, roles and authority in
   `config/permissions.toml`, prices and person-minutes in `config/costs.toml`, the market in `config/world.toml`,
   console sizes and colours in `web/src/shared/theme/tokens.ts`.
8. **Generated files.** `RESULTS.md`, `web/public/data/console.json` and `warehouse/models/mail_universe.sql` come
   from scripts; CI fails if they are stale.

## The held-out rule

Everything is tuned on `dev`. Before a held-out split runs, every file that decides its result is pinned with
`scripts/lock.py write <split>`, and `scripts/evaluate.py <split>` refuses to run unless the lock verifies. A split
is spent once it has run. `heldout` ran the first version (`config/heldout.lock`) and exposed two design flaws; the
fix was developed on `dev` and run once on `heldout2`, which was written before the fixed agent ran on anything else.
An amendment line in a lock may replace a pinned hash only for a change that cannot move a result, and only after a
re-run of the split reproduces its report byte for byte.
