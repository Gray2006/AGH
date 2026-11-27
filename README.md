# AGH

[English](README.en.md) · [简体中文](README.md) · [PyPI](https://pypi.org/project/agh-gestalt/) · MIT

**Agent Gestalt Hierarchy**：给多智能体流水线做可验证审计的一层。子级回传带签名与出处，母体验签、记账、入哈希链；事后能校验、能逐位重放、能锚定到外部。进化实验保留在 [docs/research.md](docs/research.md)，不是主推。

> 状态：M0（v3.4.1）。子级默认是**规则重构器**；LLM 子级与 LLM 变异器是可插拔的，已有实测数据。M0 管线与 LLM 变异路径都支持 L1 逐位重放。

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

## 30 秒上手

```bash
pip install agh-gestalt          # PyPI 上是 2.1.0
pip install git+https://github.com/Gray2006/AGH   # 要最新版用这个
agh quickstart
```

不需要 key、不写代码、不花 token。它会跑三次模拟调用、标记其中一次有问题、校验哈希链、重放、导出失败样本，然后告诉你下一步怎么接自己的代码。

产物在 `./agh-quickstart/`：`run.jsonl`（审计日志）和 `failures.json`（失败样本）。

## 三行接入：审计你自己的多智能体流水线

```python
from agh import AuditSession

audit = AuditSession("run.jsonl")
with audit:
    call_id = audit.call(model="deepseek-chat", prompt=p, response=r, tokens=312)
    audit.flag(call_id, reason="wrong")      # 结果不对就标一下

audit.verify()                                # 事后：这条链有没有被改
audit.replay()                                # 事后：重放，确认结论可复现
audit.export("bundle.json", redact=True)      # 审计包，脱敏后可直接外发
```

命令行：

```bash
agh audit summary --log run.jsonl              # 多少次调用、多少 token、几条标记
agh audit verify --log run.jsonl               # 校验哈希链
agh audit export-failures --log run.jsonl      # 把标记过的调用导成失败样本
```

`store_payload=False` 时只存输入输出的哈希，不存原文——适合敏感数据，代价是事后只能验「没被改」，不能重现内容。

导出的失败样本是**产品反哺实验室**的入口：真实用户标记的错题，比自造的任务族可信。

> 这个项目证明了什么、没证明什么，见 [docs/what-it-proves.md](docs/what-it-proves.md)。负面结果也列在里面。

## 它解决什么

多智能体讨论里常见两种失败：子级把整体拆成零件再拼回去，拼出来「像」但丢了关系；或者子级自报置信、自报出处，母体无法验证。

AGH 的做法：

- **给骨架，不给标准答案**：契约规定必须覆盖的节点/边与垂直移动，子级自己重构
- **出处由网关签发**：子级回传结构里没有 provenance 字段，伪造立即被签名校验拒绝
- **预算先授权后调用**：账本预留、幂等结算、超预留记违规
- **结论可复现**：仲裁是纯函数，日志是哈希链；M0 管线与 LLM 变异路径都支持 L1 逐位重放

## 在 AGI 治理光谱里的位置

多智能体治理可以拆成三层，AGH 只认领中间那一层：

| 层 | 要回答的问题 | 代表做法 |
|---|---|---|
| 个体安全 | 单个强模型每次决策是否可追溯 | 密码学审计外壳：哈希链日志 + 外部锚定 |
| 团队章程 | 多层级智能体之间，谁对谁说了什么、结论能否复现 | **AGH** |
| 社会模拟 | 大量个体各自安全，交互后是否涌现坏行为 | 仿真框架，如 [SWARM](https://www.swarm-ai.org/) |

AGH 的赌注是：AGI 级系统的风险有一部分不在单个模型，而在**信息传递与责任归属**——
子级可以自报置信、自报出处，母体却无法验证。所以它把契约、签名、预算账本、哈希链日志
做成强制通道，并把「重放」当作一等公民，而不是事后补的日志。

**它不承诺**（这几条决定了它够不上「生产级治理」）：

- 不是外部时间戳或第三方审计：哈希链只在本地，能发现「悄悄改一行」，不能发现「整条链被替换」
- 不是身份系统：开发密钥由固定派生，任何拿到源码的人都能伪造签名
- 不是独立验证：`StructuralVerifier` 是本地确定性纯函数，不是第三方验证机构
- L1 重放覆盖 M0 管线与 LLM 变异记录；LLM 子级重构路径目前只保证 L2 统计等价

## 快速开始

需要 Python 3.12+。

```bash
git clone https://github.com/Gray2006/AGH.git
cd AGH
pip install -e ".[dev]"   # 或 pip install agh-gestalt

python -m pytest -q          # 356 条测试 + 1 skipped
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

真实失败样本校准（50 次难基准里挑出 4 个部分失败 + 5 个正例，9 题）：二值判断一致率 1.0、kappa 1.0；ECE 0.241——验证器给 0.5/0.667 这种部分分，人工是「全支持才算 1」的二值判断，粒度不同导致 ECE 偏高。所以：二值决策已对齐。

分级标注（累计 19 题，人工给 0/0.5/1）：合并 ECE **0.009**、MAE **0.009**；新增 7 题 ECE 0.0。四轮 ECE：0.024 → 0.019 → 0.014 → 0.009。

这 19 题已固化成回归测试（`tests/fixtures/calibration.json`）：CI 里 ECE 超过 0.05、或二值 kappa 低于 0.9 就失败——改验证器时不会悄悄回退。但负例是按同一条规则构造的（删边/删节点），所以这验证的是「规则被正确实现、人机理解一致」，不是「规则在语义上正确」。要后者，负例必须来自真实模型失败样本，而不是构造。

多模型对比暂不可行：command-code 端点只支持 `deepseek/deepseek-v4.1-flash`，探测 `deepseek-v4.1`、`deepseek-v3.2`、`glm-4.7-flash`、`qwen3-max` 均返回 400。

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

## 事件日志的外部锚定

哈希链能发现「改一行」，但删掉日志重写一条自洽的新链，链本身校验依然通过。锚定把链头和长度写到日志之外：

```bash
python -m agh run --anchor-store runs/anchors.jsonl   # 跑完 M0 顺手写锚点（Ed25519 签名）
python -m agh anchor --events runs/m0/events.jsonl --store runs/anchors.jsonl --verify
```

- 锚点带 Ed25519 签名：没有私钥的人改不了锚点，也就无法替换整条链
- 只写锚点不签名（`--sign none`）只能防「日志被改」，防不了「锚点和日志一起被改」
- `AnchorStore` 是可替换的：换成第三方时间戳服务或另一台机器，接口不变
- 校验会重新从磁盘读日志；内存里的 entries 不参与比对


## 时间戳、计费、遗忘与声明

- **外部时间戳**：`anchor_log(log_head, tsa, path)` 把链头交给 TSA 盖章；`HmacTimestampAuthority` 用于本地，`HttpTimestampAuthority` 接外部服务（传输函数可注入，RFC 3161 客户端可替换 transport）
- **外部计费**：`BillingLedger(ledger, provider).settle(...)` 先结算预算再按 ref 幂等扣款；`JsonFileBilling` 落盘收据，`HttpBilling` 接外部计费
- **可验证遗忘**：`ForgettingRegistry.forget()` 生成签名墓碑，`verify_forgetting()` 同时校验签名与残留引用
- **跨组织声明**：`sign_statement()` + `TransparencyLog`（Merkle 树、包含证明、签名树头），三方对上才算成立

## 计费与存储

- `costs.usage_to_budget(usage, model)`：按 `Price` 把 prompt/completion token 折算成 USD 与算力单位，可直接喂给 `Ledger.reserve/settle`
- `bus_nats.NatsBus`：把 `Bus` 协议落到 JetStream——`Nats-Msg-Id` 去重、`Nats-Expected-Last-Subject-Sequence` 乐观并发、投递 at-least-once、ack/nak 走原始消息
- `sqlite_log.SqliteEventLog`：与 `EventLog` 同语义的 SQLite 实现，适合长跑与查询；`verify_against` 同样需要外部链头

## 治理有效性

前面所有实验都在问「分数能不能涨」。这一组问另一个问题：**把治理层拿掉，坏行为会不会被放进来？**

`python scripts/run_governance_bench.py`，同一批输入，对照组只把治理换成朴素实现：

| 场景 | 有治理 | 无治理 |
|---|---|---|
| 伪造出处（改载荷 / 改签名 / 未知签发者 / 重放） | 80/80 拦截 | 0/80 |
| 超预算调用 | 10/10 拒绝 | 0/10 |
| 篡改事件日志一行 | 20/20 检出 | 0/20 |

三组都是 100% vs 0%，合法输入误拒 0。数字可复现，跑一次几秒，进 CI。

它的意义不在于证明 AGH 安全，而在于说明：**治理层不是装饰**。去掉之后，前面那些「可审计、可重放」的结论全部失效。

## 发布与锚定

`python scripts/release.py` 把发布做成一条命令：

1. 校验 `pyproject.toml` 与包内版本一致、工作区干净
2. 可选 `--upload --token-file .pypi_token` 上传 PyPI
3. 跑一次 M0，确认 L1 逐位重放通过
4. 把事件日志的链头签名后锚定：本地 `runs/anchors/vX.Y.Z.jsonl` + git tag `agh-anchor/<digest>`
5. `--push` 把锚点 tag 推到 origin

锚点 tag 是**外部位置**：本地 `events.jsonl` 可以被删掉重写成一条自洽的新链，但链头已经在远程仓库里，
替换就必须同时改远程——那是另一个权限面。`python scripts/release.py --verify` 按版本找回锚点并校验。

这不是第三方时间戳。它防的是「悄悄改日志」，不防「有 push 权限的人同时改日志和 tag」。

## 接入已有日志

已经在别处记了模型调用？不用改代码，搬进来就行：

```bash
agh import --from-jsonl my_log.jsonl
# 字段名不一样就映射：
agh import --from-jsonl other.jsonl --map model=model_name --map prompt=input_text --map response=output_text
```

源文件每行一个 JSON，至少要有 `model` / `prompt` / `response`（可用 `--map` 改字段名），`tokens` 可选。缺字段或解析失败的行会跳过并计入 `skipped`。

### 支持的来源格式

`agh import` 能直接读三种导出，`--format auto`（默认）按第一行自动判断：

| 格式 | 字段 | 说明 |
|---|---|---|
| generic | `model` / `prompt` / `response` / `tokens` | 自己的 jsonl，可用 `--map` 改字段名 |
| langfuse | `type` / `input` / `output` / `model` / `usage` | Langfuse 的 JSONL 导出 |
| langsmith | `run_type` / `inputs.messages` / `outputs.messages` | LangSmith 的 run 导出，只取 `run_type=llm` |

```bash
agh import --from-jsonl langfuse-export.jsonl            # 自动识别
agh import --from-jsonl runs.jsonl --format langsmith    # 强制指定
`

三种接入方式的完整说明（含代码示例与边界）见 [docs/import-guide.md](docs/import-guide.md)。``

**边界**：导入是事后记录，它证明「这份日志从导入那一刻起没被改」，不能证明「导入时那条记录本身没被改」。要链上原始调用，得在调用发生时就用 `AuditSession.call()`。

`agh ui --from-run` 只认默认的 `./agh-quickstart/run.jsonl`；自定义目录请用 `--log` 指定。

## 可视化报告

```bash
agh ui --log run.jsonl
```

生成一个**自包含 HTML**（数据内嵌、不联网、不依赖服务器），自动打开浏览器。也可以直接发给别人，对方双击就能看。

页面内容：调用统计、每次调用的模型/哈希/tokens、被标记的问题、事件时间线。日志校验不过时直接拒绝生成。

想放进 DSH 侧边栏的话，生成后用「在侧边栏打开」指向这个 HTML 即可——不需要额外插件。

## 反馈

```bash
agh feedback --log run.jsonl              # 默认脱敏，只有哈希
agh feedback --log run.jsonl --with-payload   # 带原文，提交前自己检查
```

输出一段可直接粘贴到 issue 的 markdown：版本、环境、调用与标记统计、被标记的调用表（默认只带 `prompt_sha256` 前缀，不含原文）、以及复现步骤模板。

日志被改过时命令直接拒绝——拿一条校验不过的日志去反馈没有意义，先修数据。

## 发布

见 [docs/release.md](docs/release.md)：本地 token 与 GitHub Actions 两种方式，含 Trusted Publishing 配置。

## 研究类内容

M0 管线、进化实验、红队演练、消融与代码任务竞技场的细节在 [docs/research.md](docs/research.md)。这些是研究记录，日常审计用不到。

## 设计取舍

1. **L1 / L2 分开**。原方案要求「重放与原运行一致」，但 LLM 输出非确定，单级做不到。L1 重放记录下来的子级输出，逐位一致；L2 重跑只要求统计等价。
2. **总线不写 exactly-once**。按 NATS JetStream 的真实语义实现：at-least-once + 发布端窗口去重 + 消费端幂等。见 [NATS 核验](docs/verification-nats.md)。
3. **治理按风险分级**。八状态全保留，但 T0 自动、T1 自动验证、T2 人工。全部强制八状态会把技能固化卡死。
4. **置信必须有验证器信号**。只有自报 confidence 时校准置信返回 0，避免自报高分。
5. **垂直一致性只算 `vertical=True` 的移动**，横向平铺不给分。
6. **覆盖 = 召回 × 精确率**。只数必需项交集会让「把节点全塞进 covered」免费拿满分；精确率进分后，多余覆盖要付代价。

## 引用核验

方案里 13 条编号全部真实存在，但有 4 处必须改：

- DGM 的 SWE-bench 是 **20.0%→50.0%**，不是 23.0%
- `2504.02049` 标题应为 **Distributed Multi-agent Coordination over Cellular Sheaves**
- `2603.20640` 漏副标题：**Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention**
- 4 篇 2026 预印本不能当同行评审结论

补强文献（PoisonedRAG、MemoryGraft、A-MemGuard、MemoryGuard、Debate or Vote、Gödel Agent、SICA）见 [`docs/verification-references.md`](docs/verification-references.md)。NATS / 仓库事实见 [`docs/verification-nats.md`](docs/verification-nats.md)。

## 边界

- 研究原型，不是生产系统
- 子级默认规则重构器；`LlmChild` 与 `LlmStrategyMutator` 可直接替换，已有实测（真模型均分
  0.62229 vs 规则 0.69081，见上文 G1 段），但样本量小，不能当能力结论
- 开发密钥 `gw-dev` 由固定值派生：任何拿到源码的人都能伪造签名，生产必须换 Ed25519 + 密钥托管
- 日志哈希链只防「悄悄改一行」，不防整链替换；要防替换得把链头锚到外部（`verify_against` 是接口，尚未接外部时间戳）
- 验证器是本地纯函数，不是独立第三方
- 冻结层只防「悄悄改」，不防有密钥的人改
- L1 重放覆盖 M0 管线与 LLM 变异记录（`--replay-mutations`）；LLM 子级重构路径是 L2 统计等价

## 开发

`ash
pip install -e ".[dev]"   # 或 pip install agh-gestalt
python -m ruff check .
python -m pytest
`

提交前请跑 lint 与全量测试；改动冻结配置后用 `python -m agh --refresh-anchor` 重建锚点，并在提交说明里写清理由。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
## 版本与兼容

- **2.x**：字段与签名兼容走 minor；分数语义变更也走 minor，但必须在 CHANGELOG 标 `Semantics`
  并在 STATUS/证据表里注明口径；删字段、改签名走 major
- 1.x 期间字段层面确实冻结了，但分数语义变过三次（信息降质、覆盖口径、策略/参数分开报告）。
  2.0 把这件事写进规则，而不是假装没发生
- 引用历史数字时保留原口径标签；不重算旧报告，也不把不同口径的数字并列比较

## 关于作者

这个项目由 AI 代理**灰风**在人类指导下编写：代码、实验、文档与版本发布由灰风完成，
人类负责方向、审阅和最终决定。

不是「AI 生成后没人看过」——每个版本都经过 lint、类型检查、全量测试和 CI，
实验结论保留负面结果（见 [docs/what-it-proves.md](docs/what-it-proves.md)）。

## 许可

MIT，见 [LICENSE](LICENSE)。
