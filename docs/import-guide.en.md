# Connecting AGH to an existing system

Three ways in, ordered by evidence strength. Pick by what you need to prove.

| Approach | Proves | Does not prove | Cost |
|---|---|---|---|
| Import an existing log | unchanged since import | the record was truthful before import | one command |
| `AuditSession` (three lines) | unchanged since the call happened | the call itself was correct | a few lines |
| Gateway signing (`ProvenanceGateway`) | who produced what under which contract | that the child was honest | wire the governance layer |

Most people start with the first one.

---

## 1. Import an existing log

### From Langfuse

A Langfuse JSONL export looks like:

```json
{"type": "generation", "trace_id": "t1", "input": "sort [3,1,2]",
 "output": "[1,2,3]", "model": "gpt-x", "usage": {"input": 10, "output": 5}}
```

```bash
agh import --from-jsonl langfuse-export.jsonl
# writes langfuse-export.agh.jsonl
```

### From LangSmith

```json
{"run_type": "llm",
 "inputs": {"messages": [{"role": "user", "content": "what is a hash chain"}]},
 "outputs": {"messages": [{"role": "assistant", "content": "a chained structure"}],
             "token_usage": {"prompt_tokens": 7, "completion_tokens": 3}},
 "extra": {"metadata": {"ls_model_name": "claude-x"}}}
```

```bash
agh import --from-jsonl runs.jsonl --format langsmith
```

Only `run_type=llm` rows are imported; `chain` / `tool` rows are skipped and counted.

### From your own logs

One JSON object per line, at least `model`, `prompt`, `response`:

```json
{"model": "deepseek-chat", "prompt": "question", "response": "answer", "tokens": 120}
```

Different field names? Map them:

```bash
agh import --from-jsonl my.log --map model=model_name --map prompt=input_text --map response=output_text
```

### After importing

```bash
agh audit summary --log langfuse-export.agh.jsonl
agh audit verify  --log langfuse-export.agh.jsonl
agh ui            --log langfuse-export.agh.jsonl
agh feedback      --log langfuse-export.agh.jsonl
```

**Boundary**: an import is a retroactive record. Hashes are computed at import time, so it proves
"unchanged since import", not "the record was true when it was written". For the latter, wire in at call time.

---

## 2. Wire in at call time (three lines)

```python
from agh import AuditSession

audit = AuditSession("run.jsonl", label="my-pipeline")
with audit:
    reply = call_my_model(prompt)
    audit.call(model="deepseek-chat", prompt=prompt, response=reply, tokens=usage)
    if user_reported_bad:
        audit.flag(call_id, reason="wrong", note="treated descending as ascending")
```

`call()` returns a `call_id`; `flag()` marks it. The hash chain is written as the log is appended, so any later
edit is caught by `agh audit verify`.

**What changes**: from "retroactive notes" to "tamper-evident at source".

---

## 3. Wire the governance layer (when children are untrusted)

```python
from agh.crypto import KeyRing, ProvenanceGateway, EnvelopeVerifier
from agh.gate import WriteGate, MemoryStore, RiskModel

keyring = KeyRing.with_secret("my-kid", "my-secret")
gateway = ProvenanceGateway(keyring, "my-kid")
verifier = EnvelopeVerifier(keyring)
gate = WriteGate(verifier, RiskModel.from_frozen("config/frozen"), MemoryStore())

envelope = gateway.issue(
    payload=result_dict, producer_id="child-1", producer_kind="child",
    parent_contract_id="ct-1", trust=1,
)
admission = gate.admit(envelope, record_id="child-1")
if not admission.admitted:
    drop(admission.reason)
```

The child's payload has no provenance field; the gateway adds it. Forgery, tampering and replay are all rejected
by `admit`.

**What changes**: from "what I recorded" to "who produced what, under which contract".

---

## FAQ

**Can imported logs be replayed?**
Yes. `agh audit replay` recomputes the hash chain and compares entry by entry. What it proves is internal
consistency, not that the original model call is reproducible.

**Do logs get large?**
By default `store_payload=True` keeps prompts and responses. Use `AuditSession(..., store_payload=False)` to keep
only hashes; the cost is that `--with-payload` can no longer export raw text.

**Mixed formats in one file?**
Auto-detection only inspects the first line. Import them separately, or pass `--format` explicitly.
