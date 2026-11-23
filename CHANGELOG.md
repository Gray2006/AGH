# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

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
