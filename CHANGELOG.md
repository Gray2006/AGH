# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [1.9.2] - 2026-11-24

人工标注 · 平衡集：验证器与人工完全一致。

### Added

- `scripts/make_balanced_packet.py`：5 正 5 负标注包，题间粗分隔；负例由删边/删节点构造

### Measured

- 平衡集 10 题：一致率 1.0、Cohen's kappa 1.0、ECE 0.0
- 首批全正例 8 题：一致率 0.875、kappa 0.0（无负例）
- 注意：负例按同一条规则构造，属「规则实现正确 + 人机理解一致」，非语义正确性

## [1.9.1] - 2026-11-24

人工标注首轮结果：验证器仍未校准。

### Added

- `scripts/make_label_packet.py` / `scripts/score_labels.py`：是非题标注包与打分脚本；无垂直移动的题自动排除

### Measured

- 10 题人工标注：2 题因骨架无垂直移动排除；剩 8 题一致率 0.875、kappa 0.0、ECE 0.125
- 原因：候选集几乎全为正例（验证器全给 1），缺少负例，kappa 无法区分
- 结论：需要平衡的正负例集合才能校准

## [1.9.0] - 2026-11-24

计费、NATS 适配、SQLite 日志。

### Added

- `agh/costs.py`：usage → BudgetVector（单价可配），接 `Ledger`
- `agh/bus_nats.py`：JetStream 适配器（去重头、期望序号、ack/nak），客户端注入可测
- `agh/sqlite_log.py`：SQLite 事件日志，与 JSONL 同语义
- 测试 224 → 230

## [1.8.0] - 2026-11-24

红队演练 + 真实 token 用量。

### Added

- `agh/redteam.py` + `scripts/red_team.py`：7 类本地攻击，全部拦住
- `EventLog.verify_against(head, size)`、`head()`、`size()`：外部锚点才能发现日志尾部截断
- 实验报告带 `usage`（prompt/completion/total tokens）
- 测试 222 → 224

### Found

- 本地哈希链无法发现日志截断（剩余链自洽），必须靠外部链头+长度；红队里单列这一条并验证锚点方案

## [1.7.1] - 2026-11-24

### Added

- 验证器「已知答案」测试：5 个正反例全部符合声明规则（证明实现正确，不证明规则正确）

## [1.7.0] - 2026-11-24

盲裁判校准，结果是否定的。

### Added

- `LlmJudgeVerifier(blind=True)`：裁判不给规则，自行判断
- `run_verifier_calibration.py --blind`
- 测试 219 → 221

### Measured

- 盲裁判（10 候选）：一致率 0.8、Cohen's kappa 0.0、ECE 0.2；盲裁判对所有候选都给 1.0
- 结论：结构验证器尚未被独立校准；模型裁判不可靠，需要人工标注

## [1.6.0] - 2026-11-24

三件补齐：Ed25519 主链路、跨基准真模型实验、验证器校准。

### Added

- `agh run --sign ed25519`：主链路可用 Ed25519（开发密钥确定性派生）
- `scripts/run_llm_bench.py`：真模型在 10 个生成骨架上一一重构，与同骨架规则子级对比，候选落盘
- `agh/verifier.py`：`LlmJudgeVerifier`（模型裁判）
- `agh/calibration.py`：一致率、Cohen's kappa、ECE；`scripts/run_verifier_calibration.py`
- 测试 213 → 219

### Measured

- 跨 10 骨架：真模型 0.62229 vs 规则 0.69081，差 -0.06851（CI -0.11277–-0.02372）
- 校准 10 个候选：一致率 1.0、kappa 1.0、ECE 0.0（裁判提示复述同一规则，属不冲突而非独立佐证）

## [1.5.0] - 2026-11-24

独立验证器：自报指标改成可核对的结构证据。

### Added

- `agh/verifier.py`：`StructuralVerifier`（parts + edges 证据核对垂直移动）、`CoverageVerifier`、`make_verifier`
- `run_llm_experiment.py --verifier structural|coverage`；规则基线与被测模型使用同一个验证器

### Fixed

- `faithful_child` 现在上报 `content.vertical_moves` 的保留深度（之前没报，接验证器后基线被自己扣分）

### Measured

- 无结构提示 12 次：0.79396 vs 规则 0.80795（差 -0.014）
- 加结构提示 12 次：0.76546（差 -0.043），提示仍有害
- M0：胜者 `child-faithful` 0.80233
- 测试 208 → 213

## [1.4.0] - 2026-11-24

门控自报垂直一致性，并修正由此暴露的假高分。

### Fixed

- `score_candidate`：没有验证器信号时垂直一致性不计分（此前候选自报 `vertical_moves` 即可拿满 0.3182 权重，属于自报刷分）
- `build_prompt`：写清 `content.vertical_moves` 的元素格式（`{"node": ..., "preserved_depth": ...}`），此前未定义导致模型写成字符串数组
- `vertical_consistency` 接受字符串条目（深度未报按声明深度计，不因格式差异惩罚）
- `ablation._winner_score`：仲裁因全 0 分不选人时按 0 分处理

### Measured（修正后）

- 无提示 12 次：均分 0.40187，规则基线 0.422，差 -0.02013（CI -0.02935–-0.01024）
- 加结构提示 12 次：0.379（差 -0.043），提示反而有害
- 1.4.0 之前的真模型分数（0.49–0.51）包含自报加分，作废
- 测试 206 → 208

## [1.3.0] - 2026-11-24

温度消融，并修脚本参数未生效。

### Fixed

- `run_llm_experiment.py` 的 `--max-tokens` / `--temperature` 之前没有真正赋给客户端（消融跑出来两组都是默认温度）

### Measured

- temperature 0.2（40 次）：均分约 0.498，配对差 -0.012，CI 不含 0
- temperature 0.9（12 次）：均分 0.50554，差 -0.005，CI 含 0
- command-code 端点只支持 deepseek-v4.1-flash；另外四个模型名均 400

## [1.2.0] - 2026-11-24

提示消融：验证「给骨架不给答案」的代价。

### Added

- `build_prompt` / `LlmChild` 支持可选 `reference`；`run_llm_experiment.py --include-reference`
- 测试 204 → 206

### Measured

- 不给参考（12 次）：均分 0.50315（0.474–0.511）
- 给参考（12 次）：12/12 精确复刻基线 0.511
- 结论：不给答案压低约 0.8 个点，模型无法自行发现 `pred:hierarchical` 这类结构标签

## [1.1.0] - 2026-11-24

真模型契约通过率实验，并修掉截断导致的假失败。

### Added

- `scripts/run_llm_experiment.py`：真模型重复重构，统计通过率、分数分布与对规则基线的配对差
- CLI `--max-tokens`

### Fixed

- `providers`：`finish_reason=length` 时按截断处理并放大预算重试（此前 reasoning token 吃满输出，表现为 JSON 括号不闭合）

### Measured

- deepseek-v4.1-flash，8 次：8/8 通过契约，均分 0.48899，规则基线 0.511，配对差 -0.02201（CI -0.03225–-0.00921）

## [1.0.0] - 2026-11-24

第一个稳定版本：公开 API 冻结，自我改写闭环补齐。

### Added

- `agh/supervisor.py`：独立监督者进程，持有指针、跑 gate、管理子进程；`request.json` 投递切换请求，启动失败自动回滚
- `python -m agh.supervisor` 入口
- 测试 198 → 204

### Compatibility

- 1.x 冻结公开 API（见 README「版本与兼容」）；破坏性改动走 2.0

## [0.17.0] - 2026-11-24

自我改写的安全底座，回答「能不能让 AGH 改自己代码」。

### Added

- `agh/selfmod.py`：不可变制品（tar.gz + manifest + sha256）、原子指针切换、门禁 promote、回滚、显式 gc
- `CallableGate` / `CommandGate`
- 测试 190 → 198

### Design note

- 不做「跑通就删旧代码」；旧版本永久保留，回收只按保留期与最近 N 个
- 门禁失败或异常时现网不动；监督者必须在被改代码之外，否则门禁无效

## [0.16.0] - 2026-11-24

元进化：学会怎么改自己，并自己加难度。

### Added

- `agh/meta.py`：5 种参数算子 + UCB1 老虎机；连续两轮无改进自动升级课程（节点/边/必需项）
- CLI `agh evolve --mode meta`
- 权重钳制非负（修 `weight_down` 可能把权重压成负数）
- 测试 184 → 190

### Measured

- 8 轮：难度 1 → 4，参数收敛 `confidence 0.049 / structural 0.169 / update 0 / vertical 0.369 / coverage 0.414`

## [0.15.0] - 2026-11-24

第二轮进化结果写回冻结层。

### Changed

- `config/frozen/thresholds.json`：权重 `confidence 0.05 / structural 0.172 / update 0 / vertical 0.356 / coverage 0.422`，`dissent_tau 0.18`
- 锚点重建；M0 胜者不变，分数 0.55092 → 0.55313，异议 0.43320 → 0.45975
- 归一化后的进化曲线：0.54253 → 0.67324（6 轮）

## [0.14.2] - 2026-11-24

修一个让「进步」变假的缺陷：参数变异后权重和不再为 1。

### Fixed

- `mutate_params` 与 `ParamGenome.config` 对权重做归一化；此前变异后总和可到 1.1，分数被整体抬高，看上去的改进有一部分只是缩放
- 归一化后重跑（10 基准，6 轮）：曲线 0.54253 → 0.67324，参数收敛 `confidence 0.05 / structural 0.172 / update 0 / vertical 0.356 / coverage 0.422`，`dissent_tau 0.18`
- 测试 182 → 184

## [0.14.1] - 2026-11-24

修垂直一致性只由骨架决定的缺陷。

### Fixed

- `vertical_consistency` 现在按候选实际上报的 `content.vertical_moves` 计算；缺报按 0 计，不再让所有候选吃同一份骨架加分
- 冻结权重写回后重跑：M0 胜者仍为 `child-faithful`，分数 0.55092，异议 0.43320
- 测试 181 → 182

## [0.14.0] - 2026-11-24

把进化收敛出的权重写回冻结层。

### Changed

- `config/frozen/thresholds.json` 的 arena 权重改为进化结果（归一化后）：confidence 0.1818、structural 0.1818、update 0.0、vertical 0.3182、coverage 0.3182
- 锚点已重建；M0 胜者不变（`child-faithful`），分数 0.62025 → 0.77366，异议 0.476 → 0.65594

### Found

- `vertical_consistency` 目前只由骨架决定、与候选无关，高权重下会把所有候选的分数一起抬高。这是下一处要修的评分缺陷。

## [0.13.0] - 2026-11-23

参数层退火步长 + 多参数变异，combined 模式开始真正爬坡。

### Changed

- `mutate_params` 支持 `scale`，并可一次改 1–2 个权重
- `combined_evolve` 前半程步长 0.1、后半程 0.02（`anneal_scale`）
- 实测 10 基准 4 轮：均值 0.29863 → 0.55807，权重收敛到 `update=0, vertical=0.35, coverage=0.35`
- 测试 179 → 181

## [0.12.0] - 2026-11-23

结合两条路线：分片精英 + 全局参数进化。

### Added

- `agh/evolution_sharded.py`：`sharded_evolve`（每基准独立档案）与 `combined_evolve`（外层进化评分参数，内层分片）
- CLI `agh evolve --mode single|sharded|combined`、`--rounds`
- 测试 174 → 179
- 实测 10 基准：分片 0.29863 vs 单基因组 0.22972，配对差 +0.0689（CI 0.0167–0.1162）

## [0.11.0] - 2026-11-23

可配置基准生成器，让对照有区分度。

### Added

- `agh/benchmarks.py`：按固定节点词汇生成随机骨架（边、必需项随机），参照签名取自各自骨架
- CLI `agh evolve --benchmarks N --bench-seed S`
- 测试 170 → 174

## [0.10.3] - 2026-11-23

修一个让进化无法发生的适应度缺陷。

### Fixed

- `default_benchmarks` 的参照签名改为取自骨架本身（边），不再用种子策略。此前任何变异都会拉大与父代的结构距离、被评分惩罚，进化在数学上不可能赢；改后补全缺失边会加分
- 实测（LLM 变异器，5 代 × 3 个体）：曲线 0.33167 → 0.36306，11 个变异被接受，最优策略补上了缺失的 `P1-C3`

### Tests

- 169 → 170：补全缺失边应比缺边得分高

## [0.10.2] - 2026-11-23

跑通真实模型（command-code / deepseek-v4.1-flash）。

### Fixed

- `providers`：请求带浏览器 User-Agent（command-code 的 Cloudflare 会拦默认 UA）；`content` 为 null 时抛明确错误并带 `finish_reason`
- `llm.build_prompt`：`signature.abstraction` 示例改成布尔（模型照抄字符串会导致校验失败）
- CLI `--llm-mutator` 的特征池扩到节点、边与 `pred:*`，此前只能从父代特征里选，变异几乎没有空间

### Added

- `command-code` 提供商预设
- 测试 167 → 169

## [0.10.1] - 2026-11-23

### Fixed

- `compare_search` 透传 `mutator`：此前对照里的进化用的是规则变异器，与主循环不一致；CLI 现在会把 `--llm-mutator` 带进对照

## [0.10.0] - 2026-11-23

接入真模型。

### Added

- `agh/providers.py`：OpenAI 兼容 chat completions 适配器（DeepSeek / OpenAI / OpenRouter / Ollama 预设），密钥只从环境变量读，JSON 模式 + 重试
- `evolve(..., mutator=...)`：变异器可注入；CLI `--llm-mutator --provider --model --api-key-env`
- `scripts/run_llm_child.py`：用真模型跑一次子级重构
- 测试 162 → 166

## [0.9.0] - 2026-11-23

对照实验降方差、基线加强。

### Added

- `hill_climb` 支持 `restarts`，默认对照用 3 次重启
- `compare_search` 支持 `seeds_per_run`：每轮多种子取均值再配对
- CLI `agh evolve --seeds-per-run N`
- 报告输出每轮进化与基线的逐项分数
- 测试 160 → 162

## [0.8.0] - 2026-11-23

让进化过程可审计，让对照更严格。

### Added

- `evolve(..., log=EventLog)`：变异、接受、结束写入哈希链日志，报告带 `log_entries` / `log_ok`
- `hill_climb` 基线：贪心爬山，不留档案
- `compare_search` 支持多基线（random / hill），Holm 校正多重比较
- CLI `agh evolve` 默认写 `runs/evolve/events.jsonl`
- 测试 158 → 160

## [0.7.0] - 2026-11-23

让自我迭代可被真模型驱动，也让它可被证伪。

### Added

- `agh/evolution_llm.py`：`LlmStrategyMutator`（模型提议变异，池子过滤 + 边界钳制 + 失败退回规则变异）
- `random_search` 基线：同评估预算的随机搜索
- `compare_search`：进化 vs 随机搜索的配对 bootstrap 比较
- CLI `agh evolve --compare-runs N`
- 测试 152 → 158

## [0.6.0] - 2026-11-23

加入档案式自我迭代，参考 DGM（2505.22954）、AlphaEvolve（2506.13131）、自进化智能体综述（2507.21046），并针对 misevolve 风险（2509.26354）设边界。

### Added

- `agh/evolution.py`：受限基因组（特征/覆盖/置信/深度）、有界变异、档案保留全部变体、分数+新颖度锦标赛、血统记录、预算租约、治理门
- `agh evolve` 子命令；`scripts/` 无新增，CLI 直接可用
- 测试 144 → 152

### Notes

- 适应度来自规则子级在多个骨架基准上的竞技场分数，只验证机制
- 接 `LlmChild` 后可进化提示词策略，接口不变

## [0.5.0] - 2026-11-23

补齐生产化与跨组织能力。

### Added

- `agh/timestamp.py`：外部可信时间戳（HMAC 本地 TSA / HTTP TSA），链头锚点落盘与验证
- `agh/billing.py`：外部计费接入，结算后按 ref 幂等扣款，收据可核对
- `agh/forgetting.py`：可验证遗忘，签名墓碑 + 残留扫描
- `agh/claims.py`：跨组织声明与 Merkle 透明日志（包含证明、签名树头）
- `agh/sdk.py`：Python SDK；CLI 增加 verify / replay / experiment / ablation / version 子命令
- 测试 122 → 144

## [0.4.0] - 2026-11-23

按对比报告补齐消融、度量与生产签名。

### Added

- `agh/ablation.py`：9 组消融（完整链路 + 8 个单点关闭），配对 bootstrap + Holm；`scripts/run_ablation.py`
- `agh/experiment.py`：新增 `best_of_n` 基线；报告增加三个度量——关键事实保留率、立场熵、误拦率
- `agh/crypto.py`：Ed25519 签名后端（`KeyRing.with_ed25519` / `register_ed25519`），密钥轮换 `rotate(overlap_ms=...)`，HMAC 与 Ed25519 按 kid 自动分派
- 依赖 `cryptography>=42`
- 测试 114 → 122

### Changed

- README 增加「消融与度量」「签名后端」两节

## [0.3.0] - 2026-11-23

补上「M0 只有规则子级」和「没有竞技场实验」两个最大缺口。

### Added

- \gh/llm.py\：LLM 子级适配器。\LlmChild\ 接收任意 \complete(prompt) -> str\ 传输函数，负责拼提示、抽 JSON、按 econstruction_schema\ 校验；失败抛 \ChildOutputError\（带原始文本与逐条错误）
- \gh/experiment.py\：G1 竞技场实验。多子级 × 多种子跑完整链路，输出胜率、均分、contested 比例，并和 \single\ / \majority\ 基线做配对比较
- \gh/evalstats.py\：新增 \ootstrap_pvalue- \scripts/run_experiment.py\：一键跑实验并写 uns/g1/experiment.json- 测试 102 → 114

### Changed

- README 增加「接真 LLM」「G1 实验」两节，模块表补 \llm.py\、\experiment.py
## [0.2.0] - 2026-11-23

项目改名 AGH，补齐命令行与 lint。

### Added

- `python -m agh` 入口与 `agh` 控制台脚本；`--refresh-anchor` 重建冻结层锚点
- ruff 配置（line-length 120，忽略中文全角标点的 RUF001-003）；CI 加 lint 步骤
- `py.typed` 标记；`SECURITY.md`；版本号一致性测试

### Fixed

- `bus.publish_batch`：批次大于去重窗口时 KeyError
- `governance.observe`：停车不幂等，`from_state` 记错
- `ledger.settle`：超预留未比较 `wall_ms`
- `arena.diversity_precheck`：两两距离重复计算，O(n³) → O(n²)

### Changed

- 包名 `agh-framework` → `AGH`；仓库与文档统一为 AGH
- 清理 55 处 lint 问题（未用导入、导入排序、可合并判断等）
- 测试 95 → 102

## [0.1.0] - 2026-11-23

首个版本：AGH v3.1 M0 垂直切片。

### Added

- `contracts`：骨架 / 契约 / 提交 / 重构模型，Pydantic v2，`extra=forbid`，硬化 JSON Schema（`allOf + contains` 表达必需项）
- `crypto`：HMAC 网关签名与验签顺序、污点传播、结算签名与 judge 版本校验
- `bus`：去重 + 幂等 + 期望序号的总线抽象与进程内实现
- `ledger`：预算预授权、幂等结算、超预留违规、过期回收
- `frozen`：冻结层清单与目录外签名锚点，自引用拒绝
- `arena`：校准置信、垂直一致性、覆盖率、硬过滤、多样性预检、异议判定、纯函数仲裁
- `gate`：写入门、检索门选择完整性、提升门、复用门
- `governance`：八状态机与 T0/T1/T2 分级、劣化停车
- `eventlog`：哈希链日志、L1 逐位重放、L2 统计等价
- `evalstats`：配对 bootstrap、Holm、Cohen's d
- `pipeline`：M0 编排与 reducer；`scripts/run_m0.py` 一键复现
- 99 条测试；冻结配置（thresholds / risk_model / phase_gates / go_no_go）
- 文档：实现报告、引用核验、NATS 与仓库核验

### Known limitations

- 子级是规则重构器，未接 LLM
- 总线为进程内实现，NATS 适配器未写
- HMAC 开发密钥仅限本地
- G1 竞技场实验与 9 组消融尚未做
