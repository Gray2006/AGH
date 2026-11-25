# Research notes

M0 pipeline, evolution experiments, red team and ablations — research records, not needed for daily auditing.
For product usage see [the home page](index.md).

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

The default three skeletons are too coarse to separate methods. Generate N random benchmarks:

```bash
agh evolve --benchmarks 10 --bench-seed 0 --generations 5 --population 3
```

Generated skeletons share a node vocabulary but differ in edges and required items; each reference signature comes from its own skeleton. Evaluation stays local and deterministic.

Across heterogeneous benchmarks a single genome cancels itself out. Two better shapes:

```bash
agh evolve --benchmarks 10 --mode sharded    # one archive per benchmark
agh evolve --benchmarks 10 --mode combined   # sharded elites + global parameter evolution
```

Measured on 10 benchmarks, 3 generations × 3 individuals: sharded 0.29863 vs single 0.22972, paired delta +0.0689 (CI 0.0167–0.1162, n=10).

Meta-evolution (`--mode meta`) goes one step further: parameter mutations are split into five operators, scored by a UCB1 bandit on whether they improved, and the benchmark difficulty is raised whenever two rounds in a row fail to improve.

```bash
agh evolve --mode meta --rounds 8
```

Eight rounds: difficulty rose from 1 to 4, the curve dipped and recovered on each harder level, and parameters settled at `update=0, coverage≈0.41, vertical≈0.37`.

With annealed step sizes (0.1 early, 0.02 late), up to two weight changes per mutation and weight normalization, six rounds lift the mean from 0.54253 to 0.67324, converging to `confidence=0.05, structural=0.172, update=0, vertical=0.356, coverage=0.422`, `dissent_tau=0.18`.

## Autonomous iteration (zero tokens by default)

```bash
agh daemon --rounds 4 --benchmarks 6 --patience 2
```

Each round: generate benchmarks → sharded + parameter evolution → calibration gate → write back to the frozen layer and rebuild the anchor; if calibration fails, the backup is restored and the write-back rolls back. Stops after `patience` rounds without improvement.

- Rule-based mutations and local scoring only by default: **0 tokens**; `--llm-mutator --provider command-code --daily-budget 30000` enables model mutations with a hard token cap and stops when spent
- `--no-write-back` iterates without touching disk
- Write-back only touches `arena.weights` and `dissent_tau`

## Red team

```bash
python scripts/red_team.py
```

Seven local attacks, all expected to be blocked: forged signature, tampered payload, replayed nonce, stale sequence, log truncation, frozen-layer tamper, settlement replay.

One boundary that must be stated: **a local hash chain cannot detect tail truncation** — the remaining chain is still self-consistent. It takes an external record of the head and size (`EventLog.verify_against(head, size)`, together with a timestamp anchor). `red_team.py` verifies exactly that.

## Safe self-modification

"Do not delete the old code until the new one runs flawlessly" is the right instinct, but "runs" does not prove absence of bugs, and deleting removes the only way back. `agh/selfmod.py` does this instead:

- **Immutable artifacts**: each version is a `tar.gz` with a manifest and a whole-archive sha256; a bad checksum is refused
- **Atomic switch**: a single `current.json` pointer decides what runs, written via tmp + replace
- **Gates**: the candidate is extracted to a temp dir and every gate must pass before switching; a failing or crashing gate leaves production untouched
- **Rollback**: the pointer returns to the previous version, which is still there
- **GC**: explicit `gc(keep_last, min_age_days)`; the current version is never removed

The boundary: this assumes the **supervisor lives outside the code being changed**. If new code can rewrite the pointer, the gates or the supervisor, the gates are decoration.

The supervisor is implemented (`agh/supervisor.py`): it owns the pointer, runs gates and manages the child process; switch requests arrive as a `request.json` file, and a failed start rolls back automatically.

```bash
python -m agh.supervisor --store runs/selfmod --gate "python -m pytest -q" -- python -m agh run
```

## M0 results

| Check | Result |
|---|---|
| Winner | `child-faithful`, 0.55313 |
| Dissent | `child-dissent` 0.45975, novelty 1.0, marked `contested` |
| Forged provenance | rejected: `payload_hash_mismatch` |
| Shallow reconstruction | rejected by hard filter: missing C2 |
| Diversity | 3 clusters, min pairwise distance 0.6 |
| Governance | qualified dissent → T2, stops at `VERIFIED`; `RELEASED` after human approval |
| Ledger | 0 violations |
| Replay | L1 `bit_exact=true` |
| Tests | 356 passed + 1 skipped |

## Code tasks: an execution verifier

Every other task family is scored by rules AGH defines. This one changes the signal: **tests run for real in a
subprocess**, so correctness is not AGH's own opinion.

`agh/execverify.py`:

- Expected values stay in the parent process; the child only gets inputs and returns outputs. A candidate cannot
  fake a pass — faking the output is equivalent to computing the right answer
- Tests are split into visible / hidden: visible goes into the prompt, hidden only into the verifier. A candidate
  that memorizes visible cases scores 0 on hidden, and `overfit_gap()` measures that gap
- Subprocess with timeout, rlimits, cleared environment and a temp directory. **It stops runaway code, not hostile
  code**: no network or filesystem isolation. Evaluate untrusted output in a container or network-less sandbox

`agh/codetasks.py`: 12 small tasks, each with a reference solution and known-buggy mutants. The mutants are a
mutation test for the tests themselves — if a mutant passes hidden cases, the cases are too weak and the score is
not trustworthy.

`agh/codesolve.py` + `agh/code_evolution.py`: the solving policy is a bounded genome (sample count / selection /
hint). Evolution uses hidden pass rate as fitness, runs against random search with the same call budget, splits
tasks into train / held-out, and reports paired bootstrap intervals.

```bash
python scripts/run_code_bench.py --simulate --budget 400      # offline, pipeline check only
python scripts/run_code_bench.py --provider deepseek --budget 400   # real model
```

The offline result is negative: evolution and random search tie in a 45-policy space, held-out has 4 tasks, and the
interval crosses zero. The pipeline works; the method is not shown to work.

## Code arena: governance plus a real signal

The two lines used to be separate: the main path had governance but self-defined scores, the code tasks had a
real signal but bypassed governance. `agh/code_arena.py` joins them.

Candidates still go through gateway signing, the write gate, the budget ledger and the hash-chained log; only the
score now comes from running real tests in a subprocess.

A deliberate design choice: **arbitration looks only at visible scores** (the realistic case — only public cases
are visible), while hidden scores are reported for true quality. When `visible - hidden` exceeds 0.25 a warning is
recorded: it exposes whether the winner is memorizing visible cases.

```bash
python scripts/run_code_arena.py --task dedupe --simulate
python scripts/run_code_arena.py --task dedupe --provider deepseek --samples 3
```

The offline example reliably triggers the warning: visible 1.0, hidden 0.5, gap 0.50. That is exactly what the
governance layer should make visible — **the winner picked on public cases may not be the genuinely best one**.
