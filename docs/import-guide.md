# 从现有系统接入 AGH

三种方式，按「证据强度」从弱到强排。选哪种取决于你要证明什么。

| 方式 | 能证明 | 不能证明 | 成本 |
|---|---|---|---|
| 导入已有日志 | 从导入那一刻起未被改 | 导入前的记录是否真实 | 一条命令 |
| `AuditSession` 三行接入 | 从调用发生起未被改 | 调用本身的正确性 | 改几行代码 |
| 网关签名（`ProvenanceGateway`） | 谁在什么契约下产出了什么 | 子级是否诚实 | 接入治理层 |

大多数人从第一种开始，够用再往上升。

---

## 一、导入已有日志

### 从 Langfuse

Langfuse 的 JSONL 导出每行长这样：

```json
{"type": "generation", "trace_id": "t1", "input": "把 [3,1,2] 排序",
 "output": "[1,2,3]", "model": "gpt-x", "usage": {"input": 10, "output": 5}}
```

直接导入，格式会自动识别：

```bash
agh import --from-jsonl langfuse-export.jsonl
# 产物：langfuse-export.agh.jsonl
```

### 从 LangSmith

LangSmith 的 run 导出长这样：

```json
{"run_type": "llm",
 "inputs": {"messages": [{"role": "user", "content": "什么是哈希链"}]},
 "outputs": {"messages": [{"role": "assistant", "content": "一种链式结构"}],
             "token_usage": {"prompt_tokens": 7, "completion_tokens": 3}},
 "extra": {"metadata": {"ls_model_name": "claude-x"}}}
```

```bash
agh import --from-jsonl runs.jsonl --format langsmith
```

只取 `run_type=llm` 的记录，`chain` / `tool` 等会被跳过并计入 `skipped`。

### 从自己的日志

每行一个 JSON，至少要有 `model`、`prompt`、`response`：

```json
{"model": "deepseek-chat", "prompt": "问题", "response": "回答", "tokens": 120}
```

字段名不一样就用 `--map`：

```bash
agh import --from-jsonl my.log --map model=model_name --map prompt=input_text --map response=output_text
```

### 导入之后

```bash
agh audit summary --log langfuse-export.agh.jsonl   # 看统计
agh audit verify  --log langfuse-export.agh.jsonl   # 校验哈希链
agh ui            --log langfuse-export.agh.jsonl   # 生成 HTML 报告
agh feedback      --log langfuse-export.agh.jsonl   # 出问题时生成反馈
```

**边界**：导入是事后记录。日志里每条记录的哈希是导入时算的，它能证明「从导入到现在没被改」，不能证明「导入时那条记录是真的」。要后者，得在调用发生时接入。

---

## 二、在调用发生时接入（三行）

```python
from agh import AuditSession

audit = AuditSession("run.jsonl", label="my-pipeline")
with audit:
    reply = call_my_model(prompt)
    audit.call(model="deepseek-chat", prompt=prompt, response=reply, tokens=usage)
    if user_reported_bad:
        audit.flag(call_id, reason="wrong", note="把降序当成升序")
```

`call()` 返回 `call_id`，`flag()` 用它标记问题。日志落盘时已经算好哈希链，之后的 `verify` / `replay` 都以它为准。

**这一步的价值**：从「事后补记」变成「事前留痕」。调用发生时就算哈希，中间任何改动都会被 `agh audit verify` 发现。

---

## 三、接入治理层（子级不可信时）

如果你的架构里有「子模型回传结果、你不信任它自报」的场景，用网关：

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

子级回传的结构里没有 provenance 字段，签名由网关加。伪造、篡改、重放都会被 `admit` 拒掉。

**这一步的价值**：从「我记录了什么」变成「我能证明是谁在什么契约下产出了什么」。

---

## 常见问题

**Q：导入的日志能重放吗？**
能。`agh audit replay` 会重算哈希链并逐条比对，导入的记录也在链上。但重放证明的是「日志内部一致」，不是「当时的模型调用可复现」。

**Q：日志会很大吗？**
默认 `store_payload=True`，输入输出原文都存。要只存哈希，用 `AuditSession(..., store_payload=False)`，代价是不能 `--with-payload` 导出原文。

**Q：能导入混合格式吗？**
自动识别只看第一行。混合格式请分开导入，或用 `--format` 显式指定。
