# AGH

[English](README.en.md) · [简体中文](README.md) · MIT

**Agent Gestalt Hierarchy**：多智能体「整体重构」框架的 M0 垂直切片。母体发骨架与契约，子级按整体重构而不是拼零件，回传带签名与出处；写入门、竞技场、仲裁、治理机、预算账本、哈希链日志串成一条可跑、可测、可重放的链路。

> 状态：M0（v1.11.0），子级是**规则重构器**，不接 LLM。所有数字都能在本地复现。

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

python -m pytest -q          # 166 条测试
python -m agh                # 跑 M0，落盘 runs/m0/（等价 python scripts/run_m0.py）
```

`run_m0.py` 会先生成或校验冻结层锚点 `config/anchor.json`，再跑完整链路，输出报告与事件日志。

预期输出（节选）：

```json
{
  "winner": "child-faithful",
  "contested": true,
  "scores": {"child-faithful": 0.80233, "child-dissent": 0.45975},
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
| `agh/experiment.py` | G1 实验：多子级 × 多种子，含 single / majority / best-of-N 基线与配对统计 |
| `agh/ablation.py` | 9 组消融：完整链路 + 8 个单点关闭，配对 bootstrap + Holm |
| `agh/timestamp.py` | 外部可信时间戳：HMAC 本地 TSA / HTTP TSA，锚点落盘与验证 |
| `agh/billing.py` | 外部计费：结算后按 ref 幂等扣款，收据可核对 |
| `agh/forgetting.py` | 可验证遗忘：签名墓碑 + 残留扫描 |
| `agh/claims.py` | 跨组织声明：签名声明 + Merkle 透明日志 + 包含证明 |
| `agh/sdk.py` | Python SDK：run / verify / replay / experiment / ablation |
| `agh/evolution.py` | 档案式自我迭代：受限基因组、血统、治理门与预算 |
| `agh/evolution_llm.py` | LLM 变异器 + 进化 vs 随机搜索对照 |
| `agh/benchmarks.py` | 可配置基准生成器（节点固定、边/必需项随机） |
| `agh/evolution_sharded.py` | 分片精英 + 全局参数进化（combined 模式） |
| `agh/meta.py` | 元进化：算子老虎机 + 课程加难（meta 模式） |
| `agh/selfmod.py` | 自我改写底座：不可变制品 + 门禁 + 原子切换 + 回滚 |
| `agh/supervisor.py` | 独立监督者进程：唯一有权切换版本的角色 |
| `agh/verifier.py` | 独立验证器：结构证据核对 / 覆盖率 / 模型裁判 |
| `agh/calibration.py` | 评分器校准：一致率、Cohen's kappa、ECE |
| `agh/costs.py` | 真实 token 用量折算预算（单价可配） |
| `agh/bus_nats.py` | NATS JetStream 适配器（去重头、期望序号、at-least-once） |
| `agh/sqlite_log.py` | SQLite 事件日志（与 JSONL 同语义，支持长跑查询） |
| `agh/providers.py` | OpenAI 兼容模型适配器（环境变量取密钥，JSON 模式 + 重试） |
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

仓库提供 OpenAI 兼容适配器 `agh/providers.py`，密钥只从环境变量读：

```bash
set DEEPSEEK_API_KEY=sk-...                 # PowerShell: $env:DEEPSEEK_API_KEY="sk-..."
python scripts/run_llm_child.py --provider deepseek
agh evolve --llm-mutator --provider deepseek --generations 5
```

签名后端：`agh run --sign ed25519` 走 Ed25519（密钥由开发密钥确定性派生，可复现），默认仍是 HMAC。

任何 OpenAI 兼容端点都行：`--base-url https://... --model xxx --api-key-env MY_KEY`。客户端带 JSON 模式与重试；解析失败会抛错，不会静默返回半成品。

契约通过率实验（真模型重复重构，统计合格率与分数分布）：

```bash
python scripts/run_llm_experiment.py --provider command-code --samples 8
```

实验报告现在带真实 token 用量（3 次样本合计 2956 tokens，其中 completion 1861，含推理 token）。

实测（deepseek-v4.1-flash，12 次，接 `StructuralVerifier` 核对结构证据）：12/12 通过契约，均分 0.79396，规则子级同验证器基线 0.80795，差 -0.014 —— 真模型稳定合格，仍略低于手工规则子级。

提示消融（各 12 次，同一验证器）：不给结构提示 0.79396；给「特征命名约定」0.76546（差 -0.043）——提示让模型把 `vertical_moves:*` 塞进特征，结构距离变大，反而更差。

> 1.4.0 之前的真模型分数（0.49–0.51）包含「候选自报垂直移动」的加分，已被门控修正；旧数据作废。1.5.0 起分数由独立验证器核对，规则子级与被测模型用同一口径。

跨 10 个生成骨架（`scripts/run_llm_bench.py`）：真模型均分 0.62229，规则子级 0.69081，配对差 -0.06851（CI -0.11277–-0.02372）——单骨架上的 -0.014 在跨骨架时放大到 -0.07。

加难（7–8 节点、更多边、必需项 0.6，12 个骨架）：真模型 0.6744 vs 规则 0.76478，差 -0.09038（CI -0.11809–-0.05952）；12 个里有 1 个结构验证器只给 0.5——这是真实的部分失败样本，但比例只有 8%。

验证器校准（`scripts/run_verifier_calibration.py`，10 个真实候选）：
- 给规则当裁判：一致率 1.0、kappa 1.0、ECE 0.0——但裁判只是复述规则，不能算独立佐证
- 盲裁判（`--blind`，不给规则）：一致率 0.8、**kappa 0.0**、ECE 0.2；盲裁判对所有候选都给 1.0，没有区分力
- 人工标注 · 首批（全是正例）：8 题可判，一致率 0.875、kappa 0.0——没有负例，kappa 无意义
- 人工标注 · 平衡集（5 正 5 负，10 题）：一致率 **1.0**、kappa **1.0**、ECE **0.0**

结论：在平衡集上，结构验证器与人工判断完全一致。

真实失败样本校准（50 次难基准里挑出 4 个部分失败 + 5 个正例，9 题）：二值判断一致率 1.0、kappa 1.0；ECE 0.241——验证器给 0.5/0.667 这种部分分，人工是「全支持才算 1」的二值判断，粒度不同导致 ECE 偏高。所以：二值决策已对齐，概率校准仍未成立。但负例是按同一条规则构造的（删边/删节点），所以这验证的是「规则被正确实现、人机理解一致」，不是「规则在语义上正确」。要后者，负例必须来自真实模型失败样本，而不是构造。

多模型对比暂不可行：command-code 端点只支持 `deepseek/deepseek-v4.1-flash`，探测 `deepseek-v4.1`、`deepseek-v3.2`、`glm-4.7-flash`、`qwen3-max` 均返回 400。

## G1 实验

单次演示不足以判断架构是否有效。`scripts/run_experiment.py` 跑多子级 × 多种子，并和同种子的简单基线做配对比较：

```bash
python scripts/run_experiment.py --seeds 100 --out runs/g1/experiment.json
```

- 基线：`single`（只看第一个子级）、`majority`（过半候选共有特征拼成的多数票重构）
- 统计：配对 bootstrap CI + bootstrap p 值 + Holm 校正，阈值来自冻结层
- 报告：每个子级的有效数/错误数/胜率/均分、contested 比例、逐项比较

规则子级下跑出的数字只说明链路正确，不能当真实模型结论；换成 `LlmChild` 后同一脚本可直接跑真实实验。

## 消融与度量

```bash
python scripts/run_ablation.py --seeds 50 --out runs/g1/ablation.json
```

- 8 个单点关闭：垂直一致性、覆盖率、结构距离、更新量、校准置信、异议、仲裁、多样性
- 实验报告同时给出三个度量：关键事实保留率（父级特征与必需项保住了多少）、立场熵（候选间分歧程度，0=一致 1=对半）、误拦率（良性候选被硬过滤挡掉的比例）
- 统计口径与 G1 一致：配对 bootstrap CI + bootstrap p 值 + Holm

## 签名后端

默认 HMAC-SHA256；生产可切 Ed25519，并支持轮换：

```python
from agh.crypto import KeyRing

ring = KeyRing.with_ed25519("gw-1", private_bytes)
ring.rotate("gw-1", "gw-2", private_bytes=new_private, overlap_ms=3_600_000)
```

轮换后旧密钥在 overlap 窗口内仍可验签，窗口过后返回 `expired_kid`。密钥类型由 `kid` 自动分派，HMAC 与 Ed25519 可以混用。

## 命令行与 SDK

```bash
agh run                 # 跑 M0（默认）
agh verify              # 校验事件日志哈希链
agh replay              # L1 逐位重放
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

## 时间戳、计费、遗忘与声明

- **外部时间戳**：`anchor_log(log_head, tsa, path)` 把链头交给 TSA 盖章；`HmacTimestampAuthority` 用于本地，`HttpTimestampAuthority` 接外部服务（传输函数可注入，RFC 3161 客户端可替换 transport）
- **外部计费**：`BillingLedger(ledger, provider).settle(...)` 先结算预算再按 ref 幂等扣款；`JsonFileBilling` 落盘收据，`HttpBilling` 接外部计费
- **可验证遗忘**：`ForgettingRegistry.forget()` 生成签名墓碑，`verify_forgetting()` 同时校验签名与残留引用
- **跨组织声明**：`sign_statement()` + `TransparencyLog`（Merkle 树、包含证明、签名树头），三方对上才算成立

## 自我迭代

```bash
agh evolve --generations 5 --population 3
```

做法参考 DGM（[arXiv 2505.22954](https://arxiv.org/abs/2505.22954)）、AlphaEvolve（[arXiv 2506.13131](https://arxiv.org/abs/2506.13131)）与自进化智能体综述（[arXiv 2507.21046](https://arxiv.org/abs/2507.21046)）：

- 可进化对象收窄成**受限基因组**：子级策略的特征集、覆盖、置信、垂直深度；变异有边界，不会进化出越权行为
- **档案保留所有变体**，按「分数 + 新颖度」锦标赛选父代，血统可追溯
- 适应度来自竞技场在多个骨架基准上的分数；接受要分数不倒退，再走治理机 `VALIDATING → VERIFIED`
- 每次评估都走预算租约，预算耗尽提前停；失败模式「misevolve」（[arXiv 2509.26354](https://arxiv.org/abs/2509.26354)）的防线是基因组边界 + 冻结配置 + 治理门

规则子级下的适应度只验证机制，不代表真实模型能力。接真模型后用 `LlmStrategyMutator` 让模型提议变异：

```python
from agh.evolution_llm import LlmStrategyMutator

mutator = LlmStrategyMutator(feature_pool, node_pool, complete=my_model)
```

输出会被池子过滤与边界钳制，解析失败自动退回规则变异。对照实验：

```bash
agh evolve --generations 5 --compare-runs 5   # 同预算下与随机搜索配对比较
```

对照的意义是能证伪：如果随机搜索一样好，档案与选择就没有价值。基线有两条——随机搜索与带重启的贪心爬山，多重比较用 Holm 校正；`--seeds-per-run` 让每轮在多个种子上取均值再配对，降方差。

进化过程本身也写进哈希链日志（`runs/evolve/events.jsonl`）：每次变异、接受、结束都有记录，`agh verify` 可校验。

默认只有 3 个骨架，区分度不够。用生成器铺开到 N 个随机基准：

```bash
agh evolve --benchmarks 10 --bench-seed 0 --generations 5 --population 3
```

生成的骨架节点数固定、边与必需项随机，参照签名取自各自骨架；单次调用仍只评估本地规则子级，不花模型 token。

跨异构基准时，单一基因组会被互相抵消。两种更合适的形态：

```bash
agh evolve --benchmarks 10 --mode sharded    # 每基准独立档案
agh evolve --benchmarks 10 --mode combined   # 分片精英 + 全局参数进化
```

实测（10 基准，3 代 × 3 个体）：分片均值 0.29863，单基因组 0.22972，配对差 +0.0689（CI 0.0167–0.1162，n=10）。

元进化（`--mode meta`）再进一步：参数变异拆成 5 种算子，用 UCB1 按「是否带来改进」记功，
越有用的算子被选得越多；连续两轮没改进就把基准难度抬一档（更多节点/边/必需项）。

```bash
agh evolve --mode meta --rounds 8
```

实测 8 轮：难度从 1 升到 4，曲线在加难时回落再爬升，参数稳定在 `update=0, coverage≈0.41, vertical≈0.37`；老虎机最后偏向 `weight_up`。

参数层用退火步长（前半程 0.1、后半程 0.02）、一次可动两个权重、并对权重做归一化后，6 轮把均值从 0.54253 推到 0.67324，收敛到 `confidence=0.05, structural=0.172, update=0, vertical=0.356, coverage=0.422`，`dissent_tau=0.18`。

## 计费与存储

- `costs.usage_to_budget(usage, model)`：按 `Price` 把 prompt/completion token 折算成 USD 与算力单位，可直接喂给 `Ledger.reserve/settle`
- `bus_nats.NatsBus`：把 `Bus` 协议落到 JetStream——`Nats-Msg-Id` 去重、`Nats-Expected-Last-Subject-Sequence` 乐观并发、投递 at-least-once、ack/nak 走原始消息
- `sqlite_log.SqliteEventLog`：与 `EventLog` 同语义的 SQLite 实现，适合长跑与查询；`verify_against` 同样需要外部链头

## 红队演练

```bash
python scripts/red_team.py
```

本地跑 7 类攻击，全部应被拦住：伪造签名、篡改载荷、重放 nonce、序号回退、日志截断、冻结层篡改、结算重放。

一个必须写明的边界：**本地哈希链发现不了「截掉日志尾部」**——剩下的链仍然自洽。要靠外部记录的长度与链头（`EventLog.verify_against(head, size)`，配合时间戳锚点）才能发现。`red_team.py` 里这条也是这么验的。

## 自我改写的安全边界

「新代码跑通就删旧代码」不能做，因为「跑通」证明不了没有 bug，删掉就没了退路。`agh/selfmod.py` 给的是另一条路：

- **制品不可变**：每个版本打成 `tar.gz`，算 manifest 与整包 sha256；校验失败拒绝切换
- **原子切换**：只有 `current.json` 指针决定跑哪个版本，写入用 tmp + replace
- **门禁**：候选版本在临时目录解开，跑完所有 gate 才切换；任一 gate 失败或异常，现网不动
- **回滚**：指针回到上一版，旧版本一直都在
- **回收**：显式 `gc(keep_last, min_age_days)`，当前版本永不删

```python
from agh.selfmod import ArtifactStore, CallableGate, CommandGate, promote

store = ArtifactStore("runs/selfmod")
store.stage("build/agh", "v2")
promote(store, "v2", [CommandGate("pytest", ["python", "-m", "pytest", "-q"])])
```

边界：这套设计假设**监督者在被改代码之外**。如果新代码能改指针、改 gate 或改监督者，门禁就是装饰；真正的自改需要独立进程、独立权限与人工批准。

独立监督者已经实现（`agh/supervisor.py`）：它持有指针、跑 gate、管理子进程；切换请求通过 `request.json` 文件投递，
新版本启动失败会自动回滚并恢复旧版本。

```bash
python -m agh.supervisor --store runs/selfmod --gate "python -m pytest -q" -- python -m agh run
```

## M0 实测

| 检查 | 结果 |
|---|---|
| 胜者 | `child-faithful`，0.80233 |
| 异议 | `child-dissent` 0.45975，novelty 1.0，结论标 `contested` |
| 伪造 provenance | 拒收：`payload_hash_mismatch` |
| 浅重构 | 硬过滤拒收：parts 缺 C2 |
| 多样性 | 3 簇，最小两两距离 0.6，充足 |
| 治理 | 有合格异议 → 升 T2 停在 `VERIFIED`；人工批准后 `RELEASED` |
| 账本 | 违规 0 |
| 重放 | L1 `bit_exact=true` |
| 测试 | 166 passed |

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
## 版本与兼容

- **1.x**：公开 API 冻结（`agh.contracts`、`crypto`、`arena`、`experiment`、`evolution*`、`selfmod`、`supervisor`、`sdk`、CLI 子命令与 JSON 报告字段）；破坏性改动走 2.0
- **1.x.y**：只修 bug 与文档，不改签名、不删字段；新增能力以可选参数/新模块形式加入
- 0.x 期间接口多次变动，1.0 起以此为准

## 许可

MIT，见 [LICENSE](LICENSE)。
