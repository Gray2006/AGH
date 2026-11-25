# AGH

[English](README.en.md) · [简体中文](README.md) · [PyPI](https://pypi.org/project/agh-gestalt/) · MIT

**Agent Gestalt Hierarchy** — an M0 vertical slice of a multi-agent "gestalt reconstruction" framework. A parent issues a skeleton and a contract; children reconstruct the whole rather than reassembling parts; every submission is signed and provenance-checked. Gate, arena, arbitration, governance, budget ledger and a hash-chained log form one runnable, testable, replayable pipeline.

> Status: M0 (v2.29.2). The default child is a **rule-based reconstructor**; LLM children and the LLM mutator are pluggable and already measured. Both the M0 pipeline and the LLM mutation path support bit-exact L1 replay.

```
Parent M0
  │  skeleton + contract + budget reservation
  ▼
Parent P1 ──┬── child C1 faithful
            ├── child C2 shallow / flat
            └── child C3 dissent (flat features)
  │
  ▼
Write gate ── signature · risk score · taint propagation (self-reported trust ignored)
  │
  ▼
Arena ── hard filter → calibrated confidence → vertical consistency → coverage → diversity → dissent
  │
  ▼
Pure-function arbitration (fixed seed) ── winner + contested flag
  │
  ▼
Governance T0/T1/T2 ── auto-release / safe halt / human approval
  │
  ▼
Budget settlement + hash-chained log + bit-exact L1 replay
```

---

## 30-second tour

```bash
pip install agh-gestalt          # PyPI has 2.1.0
pip install git+https://github.com/Gray2006/AGH   # latest from source
agh quickstart
```

No API key, no code, no tokens. It runs three mock calls, flags one of them as wrong, verifies the hash chain,
replays it, exports failure samples, and then shows how to wire in your own code.

Output lands in `./agh-quickstart/`: `run.jsonl` (the audit log) and `failures.json`.

## Three lines to audit your own multi-agent pipeline

```python
from agh import AuditSession

audit = AuditSession("run.jsonl")
with audit:
    call_id = audit.call(model="deepseek-chat", prompt=p, response=r, tokens=312)
    audit.flag(call_id, reason="wrong")      # mark a result that went wrong

audit.verify()                                # later: has this chain been modified?
audit.replay()                                # later: replay it, confirm reproducibility
audit.export("bundle.json", redact=True)      # audit bundle, safe to hand over
```

Command line:

```bash
agh audit summary --log run.jsonl              # calls, tokens, flags
agh audit verify --log run.jsonl               # check the hash chain
agh audit export-failures --log run.jsonl      # export flagged calls as failure samples
```

With `store_payload=False` only hashes of inputs and outputs are kept — suitable for sensitive data, at the
cost of verifying "not modified" without being able to reproduce content.

The exported failure samples are the **product feeding the lab** entry point: real flagged mistakes are more
trustworthy than a self-made task family.

## What it solves

Two common failures in multi-agent deliberation: children decompose a whole into parts and reassemble something that looks right but loses relations; or children self-report confidence and provenance that the parent cannot verify.

AGH's answers:

- **Give a skeleton, not an answer**: the contract pins required nodes/edges and vertical moves, children reconstruct
- **Provenance is gateway-issued**: the submission schema has no provenance field, forgery fails signature verification
- **Budget before call**: lease reservation, idempotent settlement, over-reservation recorded as a violation
- **Reproducible conclusions**: arbitration is a pure function, the log is hash-chained, L1 replay is bit-exact

## Where it sits in the AGI-governance spectrum

Multi-agent governance splits into three layers; AGH claims only the middle one:

| Layer | Question | Representative approach |
|---|---|---|
| Individual safety | Is every decision of one strong model traceable? | Cryptographic audit shell: hash-chained log plus external anchoring |
| Team charter | Between hierarchical agents, who told whom what, and can the conclusion be reproduced? | **AGH** |
| Social simulation | When many individually-safe agents interact, do harmful behaviours emerge? | Simulation frameworks such as [SWARM](https://www.swarm-ai.org/) |

AGH's bet: part of AGI-level risk is not in a single model but in **information transfer and
accountability** — a child can self-report confidence and provenance, and the parent cannot verify it.
So AGH makes contracts, signatures, budget ledger and hash-chained log a mandatory channel, and treats
replay as a first-class citizen rather than afterthought logging.

**What it does not promise** (which is exactly why it is not production-grade governance):

- Not an external timestamp or third-party audit: the hash chain is local. It detects a quietly edited
  line, not a wholesale replacement of the chain
- Not an identity system: the dev key is deterministically derived, so anyone with the source can forge
  signatures
- Not independent verification: `StructuralVerifier` is a local deterministic pure function
- L1 replay covers the M0 pipeline and LLM mutation records; the LLM-child reconstruction path is only
  L2 statistically equivalent for now

## Quick start

Python 3.12+.

```bash
git clone https://github.com/Gray2006/AGH.git
cd AGH
pip install -e ".[dev]"   # 或 pip install agh-gestalt

python -m pytest -q          # 356 tests + 1 skipped
python -m agh                # run M0, writes runs/m0/ (same as python scripts/run_m0.py)
```

`run_m0.py` first generates or verifies the frozen-layer anchor `config/anchor.json`, then runs the full pipeline and writes the report plus the event log.

Expected output (excerpt):

```json
{
  "winner": "child-faithful",
  "contested": true,
  "scores": {"child-faithful": 0.55313, "child-dissent": 0.45975},
  "rejected": [
    "child-forged:rejected:payload_hash_mismatch",
    "child-shallow:hard_filter:missing required parts: ['C2']"
  ],
  "l1_bit_exact": true,
  "governance_state": "VERIFIED",
  "ledger_violations": 0
}
```

## Modules

| File | Role |
|---|---|
| `agh/contracts.py` | Single source of truth: skeleton/contract/submission/reconstruction, Pydantic v2, `extra=forbid`, hardened JSON Schema |
| `agh/crypto.py` | HMAC gateway signing, verification order, taint propagation, settlement signing |
| `agh/bus.py` | Bus abstraction: publish dedup + consumer idempotency + expected sequence (no exactly-once claim) |
| `agh/ledger.py` | Budget reservation, idempotent settlement, over-reservation violations, expiry reclaim |
| `agh/frozen.py` | Frozen layer: signed anchor outside the directory, self-reference rejected |
| `agh/arena.py` | Calibrated confidence, vertical consistency, coverage, hard filter, diversity, dissent, pure arbitration |
| `agh/gate.py` | Write / retrieval (selection integrity) / promotion / reuse gates |
| `agh/governance.py` | Eight-state machine, T0/T1/T2 tiers, degradation halt |
| `agh/eventlog.py` | Hash-chained log, bit-exact L1 replay, L2 statistical equivalence |
| `agh/evalstats.py` | Paired bootstrap CI, bootstrap p-value, Holm correction, Cohen's d |
| `agh/llm.py` | LLM child adapter: prompt, JSON extraction, contract schema validation (no network code) |
| `agh/experiment.py` | G1 experiments: arms × seeds with single / majority / best-of-N baselines and paired statistics |
| `agh/ablation.py` | 9-cell ablation suite: full pipeline plus 8 single-point removals |
| `agh/timestamp.py` | External trusted timestamps: local HMAC TSA / HTTP TSA, anchor write and verify |
| `agh/billing.py` | External billing: idempotent charge per ref after settlement |
| `agh/forgetting.py` | Verifiable forgetting: signed tombstones plus residual scan |
| `agh/claims.py` | Cross-org statements: signed statements, Merkle transparency log, inclusion proofs |
| `agh/sdk.py` | Python SDK: run / verify / replay / experiment / ablation |
| `agh/evolution.py` | Archive-based self-iteration: bounded genome, lineage, governance gate, budget |
| `agh/evolution_llm.py` | LLM mutator plus evolution-vs-random-search comparison |
| `agh/benchmarks.py` | Configurable benchmark generator (fixed nodes, random edges/required) |
| `agh/evolution_sharded.py` | Sharded elites plus global parameter evolution (combined mode) |
| `agh/meta.py` | Meta-evolution: operator bandit plus curriculum (meta mode) |
| `agh/selfmod.py` | Self-modification base: immutable artifacts, gates, atomic switch, rollback |
| `agh/supervisor.py` | Independent supervisor process: the only role allowed to switch versions |
| `agh/verifier.py` | Independent verifiers: structural evidence, coverage, LLM judge |
| `agh/calibration.py` | Rater calibration: agreement, Cohen's kappa, ECE |
| `agh/costs.py` | Real token usage converted into budget (configurable prices) |
| `agh/bus_nats.py` | NATS JetStream adapter (dedup header, expected sequence, at-least-once) |
| `agh/sqlite_log.py` | SQLite event log (same semantics as JSONL, built for long runs) |
| `agh/providers.py` | OpenAI-compatible model adapter (env key, JSON mode, retries) |
| `agh/pipeline.py` | M0 orchestration, reducer, demo frozen layer |

Thresholds live in `config/frozen/` and are covered by the anchor. Docs in [`docs/`](docs/): implementation report, original plan, and two verification reports.

## Wiring a real LLM

M0 children are rule functions, but the interface is ready: `LlmChild` needs only a completion function; the framework builds the prompt, extracts JSON and validates against the contract schema.

```python
from agh.llm import LlmChild
from agh.pipeline import m0_skeleton

child = LlmChild(
    name="llm-child",
    complete=lambda prompt: my_model(prompt),   # any string-returning transport
    skeleton=m0_skeleton(),
)
recon = child.reconstruct("ct-1")               # raises ChildOutputError on invalid output
```

`ChildOutputError` carries the raw text and per-field schema errors, so callers can retry or switch models. No network code ships in the framework.

The repo includes an OpenAI-compatible adapter (`agh/providers.py`); keys come from the environment only:

```bash
export DEEPSEEK_API_KEY=sk-...
python scripts/run_llm_child.py --provider deepseek
agh evolve --llm-mutator --provider deepseek --generations 5
```

Signing backend: `agh run --sign ed25519` uses Ed25519 (deterministically derived from the dev secret, reproducible); HMAC stays the default.

Any OpenAI-compatible endpoint works: `--base-url https://... --model xxx --api-key-env MY_KEY`. The client enables JSON mode and retries; invalid output raises instead of silently returning a half-baked object.

Contract-pass-rate experiment (repeated reconstructions from a real model):

```bash
python scripts/run_llm_experiment.py --provider command-code --samples 8
```

Experiment reports now include real token usage (3 samples totalled 2956 tokens, 1861 completion including reasoning tokens).

Measured with deepseek-v4.1-flash (12 samples, `StructuralVerifier` checking structural evidence): 12/12 passed the contract, mean score 0.79396 vs the rule child under the same verifier at 0.80795, delta -0.014 — consistently valid, still slightly below the handcrafted rule child.

Prompt ablation (12 samples each, same verifier): without structural hints 0.79396; with the naming-convention hint 0.76546 (delta -0.043) — the hint pushes `vertical_moves:*` into features, increasing structural distance and hurting the score.

> Real-model scores before 1.4.0 (0.49–0.51) included self-reported vertical-move credit and are void. From 1.5.0 an independent verifier checks the evidence and both the rule child and the model are scored the same way.

Across 10 generated skeletons (`scripts/run_llm_bench.py`): the real model averages 0.62229 vs the rule child at 0.69081, paired delta -0.06851 (CI -0.11277 to -0.02372) — the single-skeleton -0.014 grows to -0.07 across skeletons.

Harder set (7–8 nodes, more edges, required ratio 0.6, 12 skeletons): 0.6744 vs 0.76478, delta -0.09038 (CI -0.11809 to -0.05952); one of twelve scored 0.5 on the structural verifier — a real partial failure, but only 8% of samples.

Verifier calibration (`scripts/run_verifier_calibration.py`, 10 real candidates):
- Judge with the rule: agreement 1.0, kappa 1.0, ECE 0.0 — but the judge merely restates the rule, so this is not independent evidence
- Blind judge (`--blind`, no rule): agreement 0.8, **kappa 0.0**, ECE 0.2; it gives 1.0 to every candidate and does not discriminate
- Human labels, first batch (all positives): 8 scorable items, agreement 0.875, kappa 0.0 — no negatives, so kappa is meaningless
- Human labels, balanced set (5 positive / 5 negative, 10 items): agreement **1.0**, kappa **1.0**, ECE **0.0**

Conclusion: on a balanced set the structural verifier matches human judgement completely.

Real-failure calibration (4 partial failures + 5 positives drawn from 50 hard runs, 9 items): binary agreement 1.0, kappa 1.0; ECE 0.241 — the verifier returns graded scores (0.5/0.667) while the human labels are binary, so the probability calibration was not established from binary labels alone.

Graded labels (19 items pooled, human 0/0.5/1): ECE **0.009**, MAE **0.009**; the newest 7 items scored ECE 0.0. Four rounds: 0.024 → 0.019 → 0.014 → 0.009.

These 19 items are frozen into a regression test (`tests/fixtures/calibration.json`): CI fails if ECE exceeds 0.05 or binary kappa drops below 0.9, so verifier changes cannot silently regress. Caveat: negatives were built by the same rule (removing an edge or node), so this validates that the rule is implemented as stated and understood the same way — not that the rule is semantically right. That needs negatives from real model failures.

Multi-model comparison is not possible yet: the command-code endpoint only serves `deepseek/deepseek-v4.1-flash`; `deepseek-v4.1`, `deepseek-v3.2`, `glm-4.7-flash` and `qwen3-max` all return 400.

## Signing backends

HMAC-SHA256 by default; Ed25519 for production, with rotation:

```python
from agh.crypto import KeyRing

ring = KeyRing.with_ed25519("gw-1", private_bytes)
ring.rotate("gw-1", "gw-2", private_bytes=new_private, overlap_ms=3_600_000)
```

The old key keeps verifying inside the overlap window, then returns `expired_kid`. The key type is dispatched by `kid`, so HMAC and Ed25519 can coexist.

## CLI and SDK

```bash
agh run                 # M0 (default)
agh verify              # verify the hash-chained event log
agh replay              # bit-exact L1 replay
agh experiment --seeds 100
agh ablation --seeds 50
```

```python
from agh.sdk import AghClient

client = AghClient()
report = client.run()
assert client.verify_log()
assert client.replay().bit_exact
```

## External anchoring of the event log

The hash chain catches an edited line, but a self-consistent replacement chain passes its own
verification. Anchoring writes the head and size outside the log:

```bash
python -m agh run --anchor-store runs/anchors.jsonl   # write an Ed25519-signed anchor after M0
python -m agh anchor --events runs/m0/events.jsonl --store runs/anchors.jsonl --verify
```

- The anchor is Ed25519-signed: without the private key nobody can rewrite the anchor, so the whole
  chain cannot be swapped
- Unsigned anchors (`--sign none`) catch edits to the log but not an edit to both the log and the anchor
- `AnchorStore` is replaceable: point it at a timestamp service or another machine without changing the API
- Verification re-reads the log from disk; in-memory entries never take part in the comparison


## Timestamps, billing, forgetting, statements

- **External timestamps**: `anchor_log(log_head, tsa, path)`; `HmacTimestampAuthority` for local use, `HttpTimestampAuthority` for a remote service (transport injectable; swap in an RFC 3161 client without changing the interface)
- **External billing**: `BillingLedger(ledger, provider).settle(...)` settles the budget then charges once per ref; `JsonFileBilling` and `HttpBilling` included
- **Verifiable forgetting**: signed tombstones plus a residual scan over records and edges
- **Cross-org statements**: `sign_statement()` + `TransparencyLog` (Merkle tree, inclusion proofs, signed tree head)

## Billing and storage

- `costs.usage_to_budget(usage, model)`: converts prompt/completion tokens into USD and compute units via `Price`, ready for `Ledger.reserve/settle`
- `bus_nats.NatsBus`: maps the `Bus` protocol onto JetStream — `Nats-Msg-Id` dedup, `Nats-Expected-Last-Subject-Sequence` optimistic concurrency, at-least-once delivery, native ack/nak
- `sqlite_log.SqliteEventLog`: SQLite implementation with the same chain semantics; `verify_against` still needs an external head

## Governance effectiveness

Every other experiment asks whether the score can go up. This one asks: **remove the governance layer, and does the bad behaviour get in?**

`python scripts/run_governance_bench.py` runs the same inputs through two arms; the control arm swaps governance for the naive implementation:

| Scenario | With governance | Without |
|---|---|---|
| Forged provenance (tampered payload / signature / unknown signer / replay) | 80/80 blocked | 0/80 |
| Over-budget calls | 10/10 refused | 0/10 |
| One tampered log line | 20/20 detected | 0/20 |

100% vs 0% in all three, zero false rejects on legitimate input. Reproducible in seconds and wired into CI.

The point is not that AGH is secure. It is that the governance layer is not decoration: remove it and every "auditable, replayable" claim above stops holding.

## Releasing and anchoring

`python scripts/release.py` makes a release one command:

1. Check that `pyproject.toml` and the package version agree, and the tree is clean
2. Optionally upload to PyPI with `--upload --token-file .pypi_token`
3. Run M0 once and require bit-exact L1 replay
4. Sign the event-log head and anchor it: local `runs/anchors/vX.Y.Z.jsonl` plus a git tag `agh-anchor/<digest>`
5. `--push` pushes the anchor tag to origin

The anchor tag is an **external location**: a local `events.jsonl` can be deleted and rewritten as a
self-consistent new chain, but the head already lives in the remote repository, so replacing it means
touching the remote too — a different permission boundary. `python scripts/release.py --verify` looks the
anchor up by version and checks the log against it.

This is not a third-party timestamp. It prevents a quiet log edit, not someone with push access editing
both the log and the tag.

## Import an existing log

Already logging model calls elsewhere? Bring them in without touching code:

```bash
agh import --from-jsonl my_log.jsonl
# different field names? map them:
agh import --from-jsonl other.jsonl --map model=model_name --map prompt=input_text --map response=output_text
```

One JSON object per line, at least `model` / `prompt` / `response` (`tokens` optional). Lines with missing fields or
bad JSON are skipped and counted.

### Supported source formats

`agh import` reads three export shapes; `--format auto` (default) sniffs the first line:

| Format | Fields | Notes |
|---|---|---|
| generic | `model` / `prompt` / `response` / `tokens` | your own jsonl; `--map` renames fields |
| langfuse | `type` / `input` / `output` / `model` / `usage` | Langfuse JSONL export |
| langsmith | `run_type` / `inputs.messages` / `outputs.messages` | LangSmith run export; only `run_type=llm` |

```bash
agh import --from-jsonl langfuse-export.jsonl            # auto-detect
agh import --from-jsonl runs.jsonl --format langsmith    # force
```

**Boundary**: an import is a retroactive record. It proves the log has not changed since import, not that the
original record was truthful. To chain calls at source, use `AuditSession.call()` when the call happens.

## Visual report

```bash
agh ui --log run.jsonl
```

Produces a **self-contained HTML** file (data embedded, no network, no server) and opens it in the browser. You can also
send the file to someone else — they just double-click it.

The page shows call statistics, every call's model/hashes/tokens, flagged problems, and the event timeline. It refuses
to render a log that fails verification.

To put it in the DSH sidebar, just open the generated HTML there — no extra plugin needed.

## Feedback

```bash
agh feedback --log run.jsonl              # redacted by default, hashes only
agh feedback --log run.jsonl --with-payload   # includes raw text; review before posting
```

It prints markdown you can paste straight into an issue: version, environment, call and flag counts, a table of
flagged calls (only `prompt_sha256` prefixes by default), and a reproduction template.

The command refuses a log that fails verification — reporting on tampered data is pointless.

Three ways to connect, with code samples and boundaries: [docs/import-guide.en.md](docs/import-guide.en.md).

## Research notes

M0 pipeline, evolution experiments, red team and code-arena details live in [docs/research.en.md](docs/research.en.md). Research records; not needed for daily auditing.

## Design decisions

1. **L1 / L2 are separate.** The original plan asked replay to match the run, but LLM outputs are non-deterministic. L1 replays recorded child outputs bit-exactly; L2 only requires statistical equivalence.
2. **No exactly-once in the bus.** It follows real NATS JetStream semantics: at-least-once + publish-window dedup + consumer idempotency. See [NATS verification](docs/verification-nats.md).
3. **Governance is risk-tiered.** All eight states are kept, but T0 is automatic, T1 auto-verified, T2 requires a human.
4. **Confidence needs a verifier signal.** With only self-reported confidence, calibrated confidence returns 0.
6. **Coverage = recall x precision.** Counting only required hits lets a candidate stuff every
   node into `covered` for free; with precision in the score, over-coverage costs something.
5. **Vertical consistency counts only `vertical=True` moves**; flat horizontal spread earns nothing.

## References

All 13 cited IDs exist, but 4 items must be corrected:

- DGM's SWE-bench figure is **20.0% → 50.0%**, not 23.0%
- `2504.02049` is **Distributed Multi-agent Coordination over Cellular Sheaves**
- `2603.20640` is missing its subtitle: **Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention**
- four 2026 preprints must not be presented as peer-reviewed results

See [`docs/verification-references.md`](docs/verification-references.md) and [`docs/verification-nats.md`](docs/verification-nats.md).

## Boundaries

- Research prototype, not production
- The default child is a rule-based reconstructor; `LlmChild` and `LlmStrategyMutator` are drop-in and
  already measured (real model mean 0.62229 vs rule 0.69081, see G1 above), but the sample is small and
  is not a capability claim
- The `gw-dev` key is derived from a fixed value: anyone with the source can forge signatures. Production
  needs Ed25519 plus managed keys
- The hash chain detects a quietly edited line, not a wholesale replacement. Preventing replacement needs
  an external anchor: `verify_against` is the interface, no external timestamp is wired yet
- `StructuralVerifier` is a local pure function, not an independent third party
- The frozen layer prevents silent edits, not edits by whoever holds the signing key
- L1 replay covers the M0 pipeline and LLM mutation records (`--replay-mutations`); the LLM-child
  reconstruction path is L2 statistically equivalent
- Anchoring detects whole-chain replacement (given the Ed25519 key), but the anchor file itself can be
  deleted; a real third-party timestamp or off-host store is an interface, not a wired service

## Contributing

`ash
pip install -e ".[dev]"   # 或 pip install agh-gestalt
python -m ruff check .
python -m pytest
`

Run lint and the full suite before committing. After changing frozen config, rebuild the anchor with `python -m agh --refresh-anchor` and state the reason. See [CONTRIBUTING.md](CONTRIBUTING.md).
## Versioning and compatibility

- **2.x**: field and signature compatibility goes to a minor bump; score-semantics changes also go to a
  minor bump but must be tagged `Semantics` in the CHANGELOG and carry a calibration note in STATUS.
  Removing fields or changing signatures requires a major bump
- During 1.x fields were frozen, but score semantics changed three times (information degradation,
  coverage formula, strategy vs parameter reporting). 2.0 writes that into the rules instead of
  pretending otherwise
- Historical numbers keep their calibration label; old reports are not recomputed and numbers from
  different calibrations are never compared side by side

## License

MIT, see [LICENSE](LICENSE).
