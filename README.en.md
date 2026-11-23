# AGH

[English](README.en.md) · [简体中文](README.md) · MIT

**Agent Gestalt Hierarchy** — an M0 vertical slice of a multi-agent "gestalt reconstruction" framework. A parent issues a skeleton and a contract; children reconstruct the whole rather than reassembling parts; every submission is signed and provenance-checked. Gate, arena, arbitration, governance, budget ledger and a hash-chained log form one runnable, testable, replayable pipeline.

> Status: M0 (v0.1.0). Children are **rule-based reconstructors**, not LLMs. Every number below is reproducible locally.

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

python -m pytest -q          # 99 tests
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
| `agh/evalstats.py` | Paired bootstrap CI, Holm correction, Cohen's d |
| `agh/pipeline.py` | M0 orchestration, reducer, demo frozen layer |

Thresholds live in `config/frozen/` and are covered by the anchor. Docs in [`docs/`](docs/): implementation report, original plan, and two verification reports.

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
| Tests | 99 passed |

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
