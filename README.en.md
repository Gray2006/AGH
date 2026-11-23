# AGH

[English](README.en.md) · [简体中文](README.md) · MIT

**Agent Gestalt Hierarchy** — an M0 vertical slice of a multi-agent "gestalt reconstruction" framework. A parent issues a skeleton and a contract; children reconstruct the whole rather than reassembling parts; every submission is signed and provenance-checked. Gate, arena, arbitration, governance, budget ledger and a hash-chained log form one runnable, testable, replayable pipeline.

> Status: M0 (v0.10.0). Children are **rule-based reconstructors**, not LLMs. Every number below is reproducible locally.

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

## What it solves

Two common failures in multi-agent deliberation: children decompose a whole into parts and reassemble something that looks right but loses relations; or children self-report confidence and provenance that the parent cannot verify.

AGH's answers:

- **Give a skeleton, not an answer**: the contract pins required nodes/edges and vertical moves, children reconstruct
- **Provenance is gateway-issued**: the submission schema has no provenance field, forgery fails signature verification
- **Budget before call**: lease reservation, idempotent settlement, over-reservation recorded as a violation
- **Reproducible conclusions**: arbitration is a pure function, the log is hash-chained, L1 replay is bit-exact

## Quick start

Python 3.12+.

```bash
git clone https://github.com/Gray2006/AGH.git
cd AGH
pip install -e ".[dev]"

python -m pytest -q          # 166 tests
python -m agh                # run M0, writes runs/m0/ (same as python scripts/run_m0.py)
```

`run_m0.py` first generates or verifies the frozen-layer anchor `config/anchor.json`, then runs the full pipeline and writes the report plus the event log.

Expected output (excerpt):

```json
{
  "winner": "child-faithful",
  "contested": true,
  "scores": {"child-faithful": 0.62025, "child-dissent": 0.476},
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

Any OpenAI-compatible endpoint works: `--base-url https://... --model xxx --api-key-env MY_KEY`. The client enables JSON mode and retries; invalid output raises instead of silently returning a half-baked object.

## G1 experiments

One demo is not evidence. `scripts/run_experiment.py` runs arms across seeds and compares against same-seed baselines:

```bash
python scripts/run_experiment.py --seeds 100 --out runs/g1/experiment.json
```

- Baselines: `single` (first arm only) and `majority` (features shared by at least half the candidates)
- Statistics: paired bootstrap CI, bootstrap p-value, Holm correction; thresholds come from the frozen layer
- Report: valid/error counts, win rate, mean score per arm, contested rate, per-arm comparisons

Numbers from rule children only show the pipeline works; swap in `LlmChild` and the same script produces real experiments.

## Ablations and metrics

```bash
python scripts/run_ablation.py --seeds 50 --out runs/g1/ablation.json
```

- Eight single-point removals: vertical consistency, coverage, structural distance, update, calibrated confidence, dissent, arbitration, diversity
- Reports also carry three metrics: fact retention (parent features and required items kept), stance entropy (0 = agreement, 1 = even split), false-block rate (benign candidates rejected by the hard filter)
- Same statistics as G1: paired bootstrap CI, bootstrap p-value, Holm

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

## Timestamps, billing, forgetting, statements

- **External timestamps**: `anchor_log(log_head, tsa, path)`; `HmacTimestampAuthority` for local use, `HttpTimestampAuthority` for a remote service (transport injectable; swap in an RFC 3161 client without changing the interface)
- **External billing**: `BillingLedger(ledger, provider).settle(...)` settles the budget then charges once per ref; `JsonFileBilling` and `HttpBilling` included
- **Verifiable forgetting**: signed tombstones plus a residual scan over records and edges
- **Cross-org statements**: `sign_statement()` + `TransparencyLog` (Merkle tree, inclusion proofs, signed tree head)

## Self-iteration

```bash
agh evolve --generations 5 --population 3
```

Following DGM ([arXiv 2505.22954](https://arxiv.org/abs/2505.22954)), AlphaEvolve ([arXiv 2506.13131](https://arxiv.org/abs/2506.13131)) and the self-evolving agents survey ([arXiv 2507.21046](https://arxiv.org/abs/2507.21046)):

- The evolvable object is a **bounded genome**: child strategy features, coverage, confidence, vertical depth; mutations stay inside bounds
- The **archive keeps every variant**, selection is a score + novelty tournament, lineage is traceable
- Fitness comes from the arena across several skeleton benchmarks; acceptance requires no regression and passes governance `VALIDATING → VERIFIED`
- Every evaluation takes a budget lease; the run stops when the budget is exhausted. The misevolve failure mode ([arXiv 2509.26354](https://arxiv.org/abs/2509.26354)) is guarded by genome bounds, frozen config and the governance gate

With rule children the fitness only validates the mechanism. With a real model, let it propose mutations:

```python
from agh.evolution_llm import LlmStrategyMutator

mutator = LlmStrategyMutator(feature_pool, node_pool, complete=my_model)
```

Outputs are filtered to the pool and clamped; invalid replies fall back to rule mutation. Comparison run:

```bash
agh evolve --generations 5 --compare-runs 5   # paired comparison against random search
```

The point is falsifiability: if random search does just as well, the archive and selection add nothing. Two baselines are included — random search and greedy hill climbing with restarts — with Holm correction across them; `--seeds-per-run` averages several seeds per run before pairing to cut variance.

The evolution process itself is written to a hash-chained log (`runs/evolve/events.jsonl`): every mutation, acceptance and finish is recorded and can be verified with `agh verify`.

## M0 results

| Check | Result |
|---|---|
| Winner | `child-faithful`, 0.62025 |
| Dissent | `child-dissent` 0.476, novelty 1.0, marked `contested` |
| Forged provenance | rejected: `payload_hash_mismatch` |
| Shallow reconstruction | rejected by hard filter: missing C2 |
| Diversity | 3 clusters, min pairwise distance 0.6 |
| Governance | qualified dissent → T2, stops at `VERIFIED`; `RELEASED` after human approval |
| Ledger | 0 violations |
| Replay | L1 `bit_exact=true` |
| Tests | 166 passed |

## Design decisions

1. **L1 / L2 are separate.** The original plan asked replay to match the run, but LLM outputs are non-deterministic. L1 replays recorded child outputs bit-exactly; L2 only requires statistical equivalence.
2. **No exactly-once in the bus.** It follows real NATS JetStream semantics: at-least-once + publish-window dedup + consumer idempotency. See [NATS verification](docs/verification-nats.md).
3. **Governance is risk-tiered.** All eight states are kept, but T0 is automatic, T1 auto-verified, T2 requires a human.
4. **Confidence needs a verifier signal.** With only self-reported confidence, calibrated confidence returns 0.
5. **Vertical consistency counts only `vertical=True` moves**; flat horizontal spread earns nothing.

## References

All 13 cited IDs exist, but 4 items must be corrected:

- DGM's SWE-bench figure is **20.0% → 50.0%**, not 23.0%
- `2504.02049` is **Distributed Multi-agent Coordination over Cellular Sheaves**
- `2603.20640` is missing its subtitle: **Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention**
- four 2026 preprints must not be presented as peer-reviewed results

See [`docs/verification-references.md`](docs/verification-references.md) and [`docs/verification-nats.md`](docs/verification-nats.md).

## Boundaries

- Research prototype, not production. The `gw-dev` key is local-only; production needs Ed25519 and managed keys
- Children are rule functions; they do not represent real LLM behaviour. G1 arena experiments are not done
- The frozen layer prevents silent edits, not edits by whoever holds the signing key
- The hash chain gives ordering and integrity, not timestamp proof

## Contributing

`ash
pip install -e ".[dev]"
python -m ruff check .
python -m pytest
`

Run lint and the full suite before committing. After changing frozen config, rebuild the anchor with `python -m agh --refresh-anchor` and state the reason. See [CONTRIBUTING.md](CONTRIBUTING.md).
## License

MIT, see [LICENSE](LICENSE).
