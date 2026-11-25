# 研究类内容

这些章节讲的是 M0 管线、进化实验、红队与消融——属于研究记录，日常审计用不到。
产品用法见 [README](../README.md)。

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

## 自主迭代（默认零 token）

```bash
agh daemon --rounds 4 --benchmarks 6 --patience 2
```

每轮：生成基准 → 分片进化 + 参数进化 → 门禁（校准回归）→ 回写冻结层并重建锚点；校准不达标自动恢复备份并回滚。连续 `patience` 轮无改进即停。

- 默认只用规则变异器与本地打分，**0 token**；`--llm-mutator --provider command-code --daily-budget 30000` 开启模型变异并设 token 硬顶，用尽自动停
- `--no-write-back` 只迭代不落盘；报告带 `tokens_used`
- 回写只碰 `arena.weights` 与 `dissent_tau`，不碰代码

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
| 测试 | 356 passed + 1 skipped |

## 代码任务：执行型验证器

前面所有任务族的分数都由 AGH 自己定义。这一组换掉信号源：**在子进程里真跑测试**，对错不由 AGH 决定。

`agh/execverify.py`：

- 期望值只留在父进程，子进程拿到入参、只回传输出——候选无法伪造「通过」，伪造输出等价于算出正确答案
- 测试分 visible / hidden：visible 写进提示，hidden 只给验证器。背可见用例的候选在 hidden 上得 0，`overfit_gap()` 量化这个差距
- 子进程 + 超时 + rlimit + 清空环境 + 临时目录。**只防失控，不防恶意**：不隔离网络与文件读权限，评估不可信输出时请放进容器或无网络沙箱

`agh/codetasks.py`：12 道小题，每题带参考解和「已知有 bug 的变体」。变体是给测试本身做突变测试——若某个变体也能过 hidden，说明用例太弱、分数不可信。

`agh/codesolve.py` + `agh/code_evolution.py`：求解策略是有界基因组（采样数 / 选择方式 / 提示），进化以 hidden 通过率为适应度，与随机搜索用同样的调用预算，任务分 train / held-out，配对 bootstrap 给区间。

```bash
python scripts/run_code_bench.py --simulate --budget 400      # 离线，只验证流水线
python scripts/run_code_bench.py --provider deepseek --budget 400   # 真模型
```

离线模拟的结论是负面的：进化与随机搜索在 45 种策略的小空间里打平，held-out 只有 4 题、区间跨零。这说明流水线通了，不说明方法有效。

## 代码竞技场：治理层 + 真实信号

前面两条线是分开的：主链路有治理但信号自定，代码任务有真信号但绕开治理。`agh/code_arena.py` 把它们接起来。

候选仍然要过网关签名、写入门、预算账本、哈希链日志，只是分数来自子进程里真跑测试。

一个刻意的设计：**仲裁只看 visible 分**（模拟真实场景：只有公开用例），hidden 分只用于报告真实质量。两者的差距 `visible - hidden` 超过 0.25 就记一条警告——它暴露「被选中的候选是不是在背可见答案」。

```bash
python scripts/run_code_arena.py --task dedupe --simulate
python scripts/run_code_arena.py --task dedupe --provider deepseek --samples 3
```

离线示例（模拟模型）会稳定触发警告：visible 1.0、hidden 0.5、差距 0.50。这正是治理层该让人看见的东西——**按公开用例选出来的赢家，可能不是真实最好的那个**。
