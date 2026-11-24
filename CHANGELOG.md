# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [1.22.0] - 2026-11-24

覆盖口径修复：多余覆盖不再免费。

### Changed

- `arena.score_candidate` 的覆盖率从「必需项召回」改为 `recall × precision`：
  多余覆盖拉低精确率，全塞 `covered` 不再能刷分
- 新增 `over-coverage penalty: precision ...` 说明，分数来源可追

### Measured（`--seed-drop 0.4 --hide-gold`，4 轮）

| 口径 | 规则变异 | LLM 变异 |
|---|---|---|
| 旧：只数必需项交集 | 0.41109 平 | 0.47501 → **0.57681** |
| 新：召回 × 精确率 | 0.41109 平 | 0.47973 → **0.48069** |

结论：旧口径下 LLM 的「持续改进」约 +0.096 来自全塞覆盖，不是推断能力。堵上后
LLM 相对规则仍有 +0.07，但曲线不再增长。

### 兼容

- M0 数字不变（`child-faithful` 0.802325、`child-dissent` 0.45975），因为两者的 covered
  本来就等于必需项子集
- 冻结层权重未改；锚点无需重建。凡引用旧口径 0.57681 的地方必须标注口径

## [1.21.0] - 2026-11-24

事件日志的外部锚定：让「整链替换」可被发现。

### Added

- `agh/anchoring.py`：`Anchor` / `AnchorStore` / `anchor_log` / `check_log` / `verify_anchor`
- `agh anchor --events ... --store ... [--verify]`：写链头与长度，或校验日志是否被替换
- `agh run --anchor-store PATH`：跑完 M0 自动写锚点
- 锚点用 Ed25519 签名；签名覆盖 head / size / log_path / label / created_at
- 校验时从磁盘重新读日志（内存里的 entries 不参与），否则篡改不可能被发现

### Measured

- 未篡改：`{"ok": true, "signature_verified": true}`
- 改一条 payload：`LogTampered: 数据被改动于 seq=6`
- 截断日志：长度不符；换密钥验签：签名失败；锚点被改：签名失败

### 边界

- 本地锚点文件仍可被删：真正的「外部」需要把 AnchorStore 换成第三方时间戳或另一台机器，
  接口已预留，未接真实服务
- 开发密钥确定性派生，签名只证明「改动需要密钥」，不证明「密钥属于谁」

## [1.20.0] - 2026-11-24

LLM 路径的 L1 重放，以及对外部评估的诚实校准。

### Added

- `LlmStrategyMutator(recorder=...)`：每次模型提议都落一条 `llm.mutation` 记录
  （提示、原始输出、解析后的策略、是否退回规则）
- `ReplayStrategyMutator`：按记录顺序吐出策略，不调用模型；记录耗尽直接抛错，
  不会悄悄退回规则
- `agh daemon --replay-mutations EVENTS.jsonl`：用记录逐位复现 LLM 进化轨迹
- `CombinedReport` 之外无需改动：重放走同一条 `mutator_factory` 通道

### Measured

- 端到端重放：原始 2 轮 LLM 进化曲线 `[0.66079, 0.66168]`；重放同一份记录，
  曲线与最优策略逐位一致，0 token

### Docs

- README 增加「在 AGI 治理光谱里的位置」：个体安全壳 / 团队章程（AGH 所在层）/
  社会模拟器（SWARM）三层分工，只认领自己那一层
- README「边界」重写：本地哈希链不防整链替换、开发密钥可伪造、验证器不是独立第三方、
  L1 只覆盖 M0 管线与 LLM 变异，LLM 子级重构仍是 L2
- 移除过时表述（「子级是规则函数，不接 LLM」「G1 未做」）

## [1.19.0] - 2026-11-24

真难度任务族、显著性证据、缓存与回写卫生。

### Added

- `agh daemon --hide-gold`：信息降质。变异器只看得到降质后保留的边，缺的边必须靠推断，
  堵住「特征池泄漏正确答案」这条路（此前 `--seed-drop` 只降起点、不降信息）
- `visible_pool_for(bench, degrade=, seed=)`：信息降质后的可见边池
- `sharded_evolve/combined_evolve(hide_gold=, mutator_factory=)`：按基准构造变异器，
  让 LLM 变异器也吃同一份受限池
- `evolve(feature_pool=, node_pool=)`：显式覆盖变异池
- `_params_changed`：参数与冻结层一致时跳过回写，只留说明，不再「写回同值 + 重建锚点」

### Changed

- `_SHARD_CACHE` 不再要求 `verifier is None`：验证器是确定性的，缓存键补上可见池与验证器类型
- 缓存键含 `bench_seed.features/covered`，跨轮精英延续不会串味

### Measured

- `--seed-drop 0.4 --hide-gold` 规则变异 4 轮：恒 0.41109（无梯度）
- 同设置 LLM 变异 4 轮（22222 tokens）：0.47501 → 0.54593 → 0.57593 → 0.57681
- 跨 seed 配对（3 个基准 seed × 6 基准 = 18 对，17720 tokens）：LLM - 规则均值 +0.0950，
  95% CI [0.0496, 0.1402]，不跨 0

### 结论

- 信息不足时 LLM 仍能改进：它补不了缺的边，但能把覆盖补满、把深度校准到位；规则变异完全爬不动
- 覆盖项不惩罚多余节点（over-cover 免费）仍是打分口径的漏洞，下一版要么加惩罚，要么把必需项藏起来

## [1.18.1] - 2026-11-24

修掉降质模式下单基因组基线的信息优势。

### Fixed

- `combined_evolve` 的单基因组基线在 `--seed-drop > 0` 时仍拿全集特征池，而分片只拿到降质子集，
  `per_benchmark_delta` 比的不是「分片 vs 单基因组」而是「信息少 vs 信息多」
- 新增 `single_seed_features(benchmarks, degrade=, seed=)`：降质时基线取各分片降质种子的并集，保持同等信息预算

### Measured

- 6 基准、`seed_degrade=0.4`、2 代 × 1 个体：分片 0.42113 vs 单基因组 0.61556（delta -0.19444）
- 无降质同设置：分片 0.66079 vs 单基因组 0.60059（与 1.16 的 +0.0689 一致）

## [1.18.0] - 2026-11-24

让自主迭代在「更难的任务族」上有真实梯度。

### Added

- `seed_for(bench, degrade=..., rng=...)`：可确定地抽掉种子策略的部分边与必需项
- `agh daemon --seed-drop FRAC`：种子降质比例（0–0.9），把适应度从「种子即上界」解放出来
- `sharded_evolve(carry=...)` / `combined_evolve(carry=...)`：跨轮精英延续，每轮从上一轮各基准最优策略继续
- `CombinedReport.carry`：把本轮各分片精英交回调用方

### Measured

- 完美种子（无降质）：曲线仍水平，种子即上界，和 1.17.0 结论一致
- `--seed-drop 0.4` + 规则变异：种子均值 0.40822，5 轮 0.51575 → 0.52391 后停
- 同设置 + LLM 变异（30271 tokens，5 轮）：0.47869 → 0.51453 → 0.55220 → 0.56176 → 0.56534，单调上升
- 同设置规则变异对照 4 轮：恒 0.42113
- 单基准对照（2 代 × 1 个体，6 基准共 6556 tokens）：LLM 均值 0.5696 vs 规则 0.4211 vs 种子 0.4082
- 参数权重在参照打分下不再漂移（3 轮恒为冻结值），写回版本因此没有可写的东西

### 结论

- LLM 变异在降质任务族上确实持续改进，且显著优于规则变异；但在完美种子上无梯度可爬
- 回写暂缓：本轮改进来自策略而非冻结参数，写回只会写回同值并重建锚点

## [1.17.0] - 2026-11-24

杩涘寲閫傚簲搴︽帴涓婇獙璇佸櫒锛屽苟淇帀 daemon 瑙傚療妯″紡鐨勪袱澶勫け鐪熴€?
### Added

- `evaluate_strategy` / `evolve` / `sharded_evolve` / `combined_evolve` 鏀寔 `verifier`锛氬瀭鐩翠竴鑷存€т笌缃俊鍒嗙粡鐙珛楠岃瘉鍣ㄦ牳瀵瑰悗鎵嶈鍒?- `combined_evolve(reference_cfg=...)`锛氬弬鏁板€欓€夋敼鐢ㄥ浐瀹氬弬鐓ф潈閲嶉噸鎵撳垎锛岄伩鍏嶃€岃鎼滅储鐨勬潈閲嶅悓鏃跺厖褰撴墦鍒嗗嚱鏁般€?- `agh daemon` 鍙傛暟璺ㄨ疆鍦ㄥ唴瀛樺欢缁紙`--no-write-back` 涔熻兘鐪嬪埌绱Н锛夛紱鍐呭眰鎸?`generations` 杞€€鐏€佹瘡杞?3 涓弬鏁板€欓€?
### Fixed

- 鏃犻獙璇佸櫒鏃惰繘鍖栭€傚簲搴﹂《鍦?`coverage` 鏉冮噸锛?.422锛夛紝鑰岀瀛愮瓥鐣ュ氨鏄笂鐣岋紝浠讳綍鍙樺紓鍙兘鏇村樊鈥斺€旀悳绱㈢┖闂存病鏈夋搴?- `tests/conftest.py` 鏂板 `frozen_copy`锛氬洖鍐欐祴璇曚笉鍐嶇洿鎺ユ敼浠撳簱 `config/frozen/thresholds.json`锛堟鍓嶈窇鍏ㄩ噺娴嬭瘯浼氭薄鏌撲粨搴撳苟閲嶅缓閿氱偣锛?
### Measured

- 6 鍩哄噯銆佸喕缁撴潈閲嶏細绉嶅瓙 0.65792锛堟棤楠岃瘉鍣ㄥ彛寰?0.422锛夛紝鍗曡疆杩涘寲 0.66625锛岀瓥鐣ョ┖闂寸悊璁轰笂鐣?0.68212
- 鍚屼竴鎵圭瀛愮瓥鐣ュ彧鎹㈡潈閲嶅嵆鍙粠 0.65792 鍒峰埌 0.75488锛氭鍓?daemon 鐨勩€屾敼杩涖€嶄富瑕佹槸鎹㈠昂瀛愶紱鍥哄畾鍙傜収鎵撳垎鍚庝笉鍐嶅崟璋冧笂鍗?- LLM 鍙樺紓鍣ㄤ笌瑙勫垯鍙樺紓鍣ㄥ崟杞悓鍒嗭紙0.66625锛夛紝鏈瀵熷埌浼樹簬瑙勫垯鎼滅储

### 缁撹

- 璇ュ熀鍑嗘棌 + 绉嶅瓙绛栫暐宸叉帴杩戜笂鐣岋紝daemon 娌℃湁鍙寔缁敼杩涚┖闂达紱鍥炲啓鐗堟湰鏆傜紦锛岄渶瑕佹洿闅剧殑鍩哄噯鎴栫湡瀹炲け璐ユ牱鏈?
## [1.16.0] - 2026-11-24

daemon 支持 LLM 变异器与 token 硬预算。

### Added

- `agh daemon --llm-mutator --provider --model --api-key-env --daily-budget`
- 预算用尽自动停止并写进报告 `tokens_used`；预算内退化回规则变异
- `combined_evolve` 透传 `mutator`

### Measured

- 冒烟（2 基准、1 代、population 1）：tokens_used 1607，未触顶

## [1.15.0] - 2026-11-24

自主迭代闭环。

### Added

- `agh/autonomous.py` + `agh daemon`：多轮进化 → 校准门禁 → 回写冻结层 → 失败回滚；plateau 自动停
- 默认零 token（规则变异 + 本地打分）；`--no-write-back` 只观察不落盘
- 测试 238 → 241

## [1.14.0] - 2026-11-24

工程化收尾：类型检查、文档站、构建产物。

### Added

- mypy 渐进接入（`check_untyped_defs`，5 个动态模块先忽略，其余 32 个文件检查通过）
- `mkdocs.yml` + `docs/index.md` + `docs/api.md`，可本地构建站点
- `python -m build` 产出 sdist/wheel；`docker-compose.yml` 可起 NATS 做联调

## [1.13.1] - 2026-11-24

### Added

- `run_llm_experiment.py --parallel N`：样本级并发，每个任务独立客户端，usage 汇总

## [1.13.0] - 2026-11-24

性能与回归兜底。

### Added

- `run_llm_bench.py --parallel N`：真模型跨基准并发跑（每任务独立客户端）
- `evolution_sharded` 分片评估记忆化：同骨架同策略同参数直接复用，进化重复轮次不再重算
- 监督者进程端到端测试：真实子进程启动/停止

### Note

- `EventLog` 原本就在内存缓存 entries，`verify()` 不重复读盘，无需改动

### Tests

- 237 → 238

## [1.12.0] - 2026-11-24

校准进 CI：验证器改动不能悄悄回退。

### Added

- `tests/fixtures/calibration.json`：19 题人工分级标注固化
- `tests/test_calibration_regression.py`：ECE ≤ 0.05、二值 kappa ≥ 0.9、正负样本下限
- 测试 234 → 237（CI 自动执行）

## [1.11.4] - 2026-11-24

分级校准累计 19 题。

### Added

- `make_graded_packet.py --exclude`：按内容排除已标注候选

### Measured

- 新增 7 题：ECE 0.0
- 合并 19 题：ECE 0.009、MAE 0.009；四轮 0.024 → 0.019 → 0.014 → 0.009

## [1.11.3] - 2026-11-24

分级校准扩到 12 题。

### Measured

- 12 题：ECE 0.014、MAE 0.014；验证器均值 0.806 vs 人工 0.792
- 三轮 ECE：0.024 → 0.019 → 0.014，稳定

## [1.11.2] - 2026-11-24

分级校准扩到 9 题。

### Measured

- 9 题分级标注：ECE 0.019、MAE 0.019；验证器均值 0.796 vs 人工 0.778
- 与上一轮 7 题（ECE 0.024）一致，概率校准结论稳定

## [1.11.1] - 2026-11-24

分级标注：概率校准初步成立。

### Added

- `scripts/make_graded_packet.py`：0/0.5/1 分级标注包
- `score_labels.py` 支持分级标签（ECE + MAE）；`calibration.ece` 支持浮点标签

### Measured

- 7 题分级标注：ECE 0.024、MAE 0.024，验证器均值 0.738 vs 人工 0.714
- 样本小，需扩大

## [1.11.0] - 2026-11-24

### Added

- `agh/report`：汇总 `runs/` 下各实验（M0、实验、消融、真模型、校准）成一张表
- 测试 230 → 234

## [1.10.2] - 2026-11-24

### Added

- `docs/STATUS.md`：交接文档，按可信度列出证据、限制与下一步优先级

## [1.10.1] - 2026-11-24

真实失败样本校准。

### Added

- `scripts/make_real_packet.py`：从真实模型输出里挑失败样本与正例
- `score_labels.py --threshold`：验证器判为支持的阈值（默认 0.99）

### Measured

- 50 次难基准：45 满分、5 个部分失败（其中 1 个骨架无垂直移动，排除）
- 9 题人工标注：二值一致率 1.0、kappa 1.0；ECE 0.241（验证器分级分 vs 人工二值，粒度不同）

## [1.10.0] - 2026-11-24

加难基准：差距扩大，真实失败样本开始出现。

### Added

- `run_llm_bench.py` 支持 `--min-nodes/--max-nodes/--extra-edges/--required-ratio`，报告记录每个骨架的验证器分数

### Measured

- 难基准 12 个（7–8 节点、必需项 0.6）：真模型 0.6744 vs 规则 0.76478，差 -0.09038（CI -0.11809–-0.05952）
- 验证器分布：11 个 1.0、1 个 0.5（真实部分失败，8%）

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
