# AGH

[English](README.en.md) · [简体中文](README.md) · MIT

**Agent Gestalt Hierarchy**：多智能体「整体重构」框架的 M0 垂直切片。母体发骨架与契约，子级按整体重构而不是拼零件，回传带签名与出处；写入门、竞技场、仲裁、治理机、预算账本、哈希链日志串成一条可跑、可测、可重放的链路。

> 状态：M0（v0.3.0），子级是**规则重构器**，不接 LLM。所有数字都能在本地复现。

```
母体 M0
  │  骨架 + 契约 + 预算预留
  ▼
父 P1 ──┬── 子 C1 忠实重构
        ├── 子 C2 平铺/钻取（浅）
        └── 子 C3 异议重构（平铺特征）
  │
  ▼
写入门 ── 验签 · 风险评分 · 污点传播（不采信自报 trust）
  │
  ▼
竞技场 ── 硬过滤 → 校准置信 → 垂直一致性 → 覆盖率 → 多样性 → 异议
  │
  ▼
纯函数仲裁（固定种子）── 胜者 + contested 标记
  │
  ▼
治理机 T0/T1/T2 ── 自动发布 / 停车 / 等人工
  │
  ▼
预算账本结算 + 哈希链日志 + L1 逐位重放
```

---

## 它解决什么

多智能体讨论里常见两种失败：子级把整体拆成零件再拼回去，拼出来「像」但丢了关系；或者子级自报置信、自报出处，母体无法验证。

AGH 的做法：

- **给骨架，不给标准答案**：契约规定必须覆盖的节点/边与垂直移动，子级自己重构
- **出处由网关签发**：子级回传结构里没有 provenance 字段，伪造立即被签名校验拒绝
- **预算先授权后调用**：账本预留、幂等结算、超预留记违规
- **结论可复现**：仲裁是纯函数，日志是哈希链，L1 重放逐位比对

## 快速开始

需要 Python 3.12+。

```bash
git clone https://github.com/Gray2006/AGH.git
cd AGH
pip install -e ".[dev]"

python -m pytest -q          # 114 条测试
python -m agh                # 跑 M0，落盘 runs/m0/（等价 python scripts/run_m0.py）
```

`run_m0.py` 会先生成或校验冻结层锚点 `config/anchor.json`，再跑完整链路，输出报告与事件日志。

预期输出（节选）：

```json
{
  "winner": "child-faithful",
  "contested": true,
  "scores": {"child-faithful": 0.62025, "child-dissent": 0.476},
  "rejected": [
    "child-forged:rejected:payload_hash_mismatch",
    "child-shallow:hard_filter:parts 缺必需项: ['C2']"
  ],
  "l1_bit_exact": true,
  "governance_state": "VERIFIED",
  "ledger_violations": 0
}
```

## 模块

| 文件 | 作用 |
|---|---|
| `agh/contracts.py` | 单一真相源：骨架/契约/提交/重构，Pydantic v2，`extra=forbid`，JSON Schema 硬化 |
| `agh/crypto.py` | HMAC 网关签名、验签顺序、污点传播、结算签名 |
| `agh/bus.py` | 总线抽象：发布端去重 + 消费端幂等 + 期望序号（不承诺 exactly-once） |
| `agh/ledger.py` | 预算预授权、幂等结算、超预留违规、过期回收 |
| `agh/frozen.py` | 冻结层：目录外签名锚点，拒绝自引用，写冻结路径直接拒 |
| `agh/arena.py` | 校准置信、垂直一致性、覆盖率、硬过滤、多样性、异议、纯函数仲裁 |
| `agh/gate.py` | 写入门 / 检索门（选择完整性）/ 提升门 / 复用门 |
| `agh/governance.py` | 八状态机，T0/T1/T2 分级，劣化停车 |
| `agh/eventlog.py` | 哈希链日志、L1 逐位重放、L2 统计等价 |
| `agh/evalstats.py` | 配对 bootstrap CI、bootstrap p 值、Holm 校正、Cohen's d |
| `agh/llm.py` | LLM 子级适配：拼提示、抽 JSON、按契约 schema 校验（不含网络代码） |
| `agh/experiment.py` | G1 实验：多子级 × 多种子，含 single / majority 基线与配对统计 |
| `agh/pipeline.py` | M0 编排、reducer、演示冻结层 |

配置在 `config/frozen/`，阈值全部进冻结层，改配置会被锚点发现。文档在 [`docs/`](docs/)：实现报告、方案原文、两份引用/事实核验。

## 接真 LLM

M0 的子级是规则函数，但接口已经留好：`LlmChild` 只需要一个传输函数，框架负责拼提示、抽 JSON、按契约 schema 校验。

```python
from agh.llm import LlmChild
from agh.pipeline import m0_skeleton

child = LlmChild(
    name="llm-child",
    complete=lambda prompt: my_model(prompt),   # 返回字符串即可
    skeleton=m0_skeleton(),
)
recon = child.reconstruct("ct-1")               # 校验不过抛 ChildOutputError
```

`ChildOutputError` 带原始文本与逐条 schema 错误，可以直接拿去重试或换模型。框架里没有网络代码：模型怎么调是部署方的事。

## G1 实验

单次演示不足以判断架构是否有效。`scripts/run_experiment.py` 跑多子级 × 多种子，并和同种子的简单基线做配对比较：

```bash
python scripts/run_experiment.py --seeds 100 --out runs/g1/experiment.json
```

- 基线：`single`（只看第一个子级）、`majority`（过半候选共有特征拼成的多数票重构）
- 统计：配对 bootstrap CI + bootstrap p 值 + Holm 校正，阈值来自冻结层
- 报告：每个子级的有效数/错误数/胜率/均分、contested 比例、逐项比较

规则子级下跑出的数字只说明链路正确，不能当真实模型结论；换成 `LlmChild` 后同一脚本可直接跑真实实验。

## M0 实测

| 检查 | 结果 |
|---|---|
| 胜者 | `child-faithful`，0.62025 |
| 异议 | `child-dissent` 0.476，novelty 1.0，结论标 `contested` |
| 伪造 provenance | 拒收：`payload_hash_mismatch` |
| 浅重构 | 硬过滤拒收：parts 缺 C2 |
| 多样性 | 3 簇，最小两两距离 0.6，充足 |
| 治理 | 有合格异议 → 升 T2 停在 `VERIFIED`；人工批准后 `RELEASED` |
| 账本 | 违规 0 |
| 重放 | L1 `bit_exact=true` |
| 测试 | 114 passed |

## 设计取舍

1. **L1 / L2 分开**。原方案要求「重放与原运行一致」，但 LLM 输出非确定，单级做不到。L1 重放记录下来的子级输出，逐位一致；L2 重跑只要求统计等价。
2. **总线不写 exactly-once**。按 NATS JetStream 的真实语义实现：at-least-once + 发布端窗口去重 + 消费端幂等。见 [NATS 核验](docs/verification-nats.md)。
3. **治理按风险分级**。八状态全保留，但 T0 自动、T1 自动验证、T2 人工。全部强制八状态会把技能固化卡死。
4. **置信必须有验证器信号**。只有自报 confidence 时校准置信返回 0，避免自报高分。
5. **垂直一致性只算 `vertical=True` 的移动**，横向平铺不给分。

## 引用核验

方案里 13 条编号全部真实存在，但有 4 处必须改：

- DGM 的 SWE-bench 是 **20.0%→50.0%**，不是 23.0%
- `2504.02049` 标题应为 **Distributed Multi-agent Coordination over Cellular Sheaves**
- `2603.20640` 漏副标题：**Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention**
- 4 篇 2026 预印本不能当同行评审结论

补强文献（PoisonedRAG、MemoryGraft、A-MemGuard、MemoryGuard、Debate or Vote、Gödel Agent、SICA）见 [`docs/verification-references.md`](docs/verification-references.md)。NATS / 仓库事实见 [`docs/verification-nats.md`](docs/verification-nats.md)。

## 边界

- 研究原型，不是生产系统。开发密钥 `gw-dev` 只用于本地，生产必须换 Ed25519 与密钥托管
- 子级是规则函数，不代表真实 LLM 行为；G1 竞技场实验尚未做
- 冻结层只防「悄悄改」，不防有密钥的人改
- 日志哈希链不提供时间戳证明，只保证顺序与完整性

## 开发

`ash
pip install -e ".[dev]"
python -m ruff check .
python -m pytest
`

提交前请跑 lint 与全量测试；改动冻结配置后用 `python -m agh --refresh-anchor` 重建锚点，并在提交说明里写清理由。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
## 许可

MIT，见 [LICENSE](LICENSE)。
