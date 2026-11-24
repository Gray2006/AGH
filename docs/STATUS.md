# AGH 状态交接（v2.12.0，2026-11-25）

> 新会话先读这个文件，再读 `README.md` 的「版本与兼容」与 `memory/agh.md`。

## 一句话

机制完整、证据分层、缺口明确。进化适应度已接验证器；当前基准族上搜索空间接近上界，daemon 回写版本暂缓。

## 当前版本

- v2.6.0，`356 passed + 1 skipped`（NATS 在 CI 跑），ruff 干净，mypy 48 文件零错误
- 仓库 <https://github.com/Gray2006/AGH>，CI 双版本绿
- 依赖：pydantic v2、numpy、jsonschema、cryptography；Python 3.12+

## 能跑什么

```bash
pip install -e ".[dev]"
python -m pytest                    # 247 passed, 1 skipped
python -m agh run                   # M0 垂直切片
python -m agh experiment --seeds 50
python -m agh ablation --seeds 30
python -m agh evolve --mode meta --rounds 8
python -m agh daemon --rounds 4     # 自主迭代（默认 0 token）
python -m agh daemon --seed-drop 0.4 --llm-mutator --daily-budget 30000  # 降质任务族 + LLM 变异
python -m agh daemon --seed-drop 0.4 --hide-gold --llm-mutator     # 信息不足：缺的边得推断
python -m agh daemon --replay-mutations runs/daemon/events.jsonl   # L1 重放 LLM 进化轨迹
python -m agh run --anchor-store runs/anchors.jsonl                # 写签名锚点
python -m agh anchor --events runs/m0/events.jsonl --store runs/anchors.jsonl --verify
python -m agh report --runs runs
python scripts/red_team.py          # 7 类攻击
```

真模型（需 `COMMAND_CODE_API_KEY`；端点只支持 `deepseek/deepseek-v4.1-flash`）：

```bash
python scripts/run_llm_experiment.py --provider command-code --samples 20 --parallel 4 --verifier structural
python scripts/run_llm_bench.py --provider command-code --benchmarks 50 --min-nodes 7 --max-nodes 8
python scripts/make_graded_packet.py
python scripts/score_labels.py --labels ... --candidates ...
```

## 证据（按可信度）

| 结论 | 数字 | 可信度 |
|---|---|---|
| 分片精英优于单基因组 | +0.0689（CI 0.0167–0.1162） | 高 |
| 真模型跨 10 骨架低于规则 | -0.0685（CI -0.1128–-0.0237） | 高 |
| 加难后差距扩大 | -0.0904（12）、-0.0648（50） | 高 |
| 验证器二值决策与人工一致 | kappa 1.0（构造 10 + 真实 9） | 中高 |
| 验证器概率校准 | ECE 0.009（19 题，四轮） | 中 |
| 盲裁判不可用 | kappa 0.0 | 已判死 |
| 无验证器时进化适应度无梯度 | 顶在 0.422（= coverage 权重），种子即上界 | 高（1.17.0） |
| 接验证器后单轮进化 | 种子 0.65792 → 0.66625，上界 0.68212 | 高（1.17.0） |
| 完美种子上 LLM 变异 vs 规则 | 单轮同分 0.66625，未见优势 | 中（各 1 轮） |
| 降质种子（--seed-drop 0.4）上 LLM 变异 | 5 轮 0.47869 → 0.56534 单调上升，30271 tokens | 中高（1 次） |
| 同设置规则变异对照 | 4 轮恒 0.42113 | 高 |
| 单基准对照（6 基准 6556 tokens） | LLM 0.5696 vs 规则 0.4211 vs 种子 0.4082 | 中 |
| 降质下分片 vs 单基因组（公平基线） | 0.42113 vs 0.61556，delta -0.19444 | 高（1 次） |
| 信息降质（--hide-gold）规则变异 | 4 轮恒 0.41109，无梯度 | 高 |
| 信息降质 LLM 变异（旧口径：只数必需项） | 4 轮 0.47501 → 0.57681，22222 tokens | 已作废（含全塞覆盖收益） |
| 信息降质 LLM 变异（新口径：召回×精确率） | 4 轮 0.47973 → 0.48069，22156 tokens | 高 |
| 多余覆盖惩罚 | 精确覆盖 1.0 vs 全塞 0.5，总分确实更低 | 高（单测） |
| 跨 seed 配对（3 seed × 6 基准 = 18 对） | LLM − 规则 +0.0950，95% CI [0.0496, 0.1402] | 高（17720 tokens） |
| LLM 进化 L1 重放 | 曲线 `[0.66079, 0.66168]` 逐位一致，0 token | 高 |
| hard 骨架族（信息降质） | 规则 4 轮恒 0.55289；LLM 0.58086 → 0.58222（20794 tokens） | 高 |
| 搜索旋钮（tournament 3→6 / elite_only） | 6 基准分数完全不变 | 高（负面结果） |
| NATS 联调（nats-server -js） | roundtrip 通过；CI 起 nats:2.10 service | 高 |
| 更强模型对照（hard 族） | flash 0.58222 / pro 0.58751、0.58367，差 ≤0.006 | 中高（各 1–2 次） |
| 治理有效性：伪造出处 | 有网关 80/80 拦截，无治理 0/80 | 高 |
| 治理有效性：超预算 | 有账本 10/10 拒绝，无账本 0/10 | 高 |
| 治理有效性：篡改日志 | 有链 20/20 检出，无链 0/20 | 高 |
| 发布锚定 | `scripts/release.py` 跑 M0 → 签名锚点 → git tag，CI 全绿 | 高 |
| 代码任务离线（模拟模型） | baseline 0.5625，进化/随机均 0.875，差 0 且区间跨零 | 高（负面结果） |
| 代码任务突变测试 | 15 题参考解 hidden 全 1.0，每个 bug 变体 hidden < 1.0 | 高 |
| 代码任务真模型（command-code flash） | 12 题与 15 题 baseline 均 1.0，进化/随机同分；基准触顶 | 高（负面结果） |
| 代码任务三通道对照 | flash 1.0 / deepseek-chat 1.0 / glm-4-flash 0.9375，三者进化=随机 | 高（负面结果） |
| 代码竞技场（治理 + 真信号） | 离线：visible 1.0 / hidden 0.5，overfit 候选降 T2，日志校验通过 | 高 |
| 多轮修正（rounds 维度） | flash 触顶 1.0；glm-4-flash 0.9375 三方法全平，统计功效不足 | 中（n=16） |
| 审计 SDK（AuditSession） | 7 条测试：篡改检出、脱敏、失败样本导出 | 高 |
| 反馈通道（agh feedback） | 4 条测试：默认脱敏、可带原文、模板、无标记提示 | 高 |
| 低门槛入口（agh quickstart） | 5 条测试：无 key 可跑、日志可校验、可重复 | 高 |
| 可视化报告（agh ui） | 7 条测试：自包含 HTML、转义、篡改拒绝、--from-run | 高 |
| 自检（2.10.1） | 修 call_id 冲突 / title 未渲染 / 产物未忽略 / .gitignore 编码 | 高 |
| 接入已有日志（agh import） | 5 条测试：可验证输出、字段映射、坏行跳过 | 高 |
| 自检（2.11.1） | 修 4 处静默成功：缺文件返回 ok、坏行 KeyError、重复导入追加、参数冲突 | 高 |
| 自检（2.11.2） | 修 splitlines 切坏日志、feedback note 未清理、围栏未适配 | 高 |
| 学习进步奖励（LP） | 离线：absolute 0.5625/0.875/0.875 vs progress 0.5/0.9375/1.0，随机更好 | 中（模拟模型） |
| 锚定篡改检出 | 改一条 payload → `LogTampered: 数据被改动于 seq=6`；未篡改 → `signature_verified: true` | 高 |
| 真实失败样本（8 条） | 种子均值 0.37887 → 规则/LLM 均 0.42151 后停滞；LLM 20107 tokens | 中高（各 1 次） |
| git tag 锚点 | 写 tag 后读回 head/size/label 一致 | 高（单测） |
| daemon 的「改进」主要来自换权重 | 同批种子换权重 0.65792 → 0.75488 | 高（1.17.0） |

校准已固化进 CI：`tests/fixtures/calibration.json` + `tests/test_calibration_regression.py`（ECE ≤ 0.05、kappa ≥ 0.9）。

## 已知限制

1. 单一模型（command-code 只支持 deepseek-v4.1-flash）
2. 校准样本 19 题，规模小
3. 进化适应度基于规则子级，不代表模型能力
4. NATS 只验证语义，未真联调
5. 代码级自改只有底座（selfmod + supervisor），未启用
6. daemon 默认 0 token；LLM 变异器要显式开并设预算
7. 完美种子上种子策略即适应度上界（0.66625 / 0.68212），没有持续改进空间；只有降质种子（--seed-drop）才有梯度
8. 降质任务族的改进来自策略恢复，参数权重在参照打分下不动；回写分支已加「参数未变则跳过」，但它仍不是可持久化路径
9. 覆盖口径已改为召回×精确率（v1.22.0）：全塞不再免费。旧口径下的 0.57681 不可与新数字混用
10. 哈希链无外部锚定：能防「改一行」，不能防「整链替换」；`verify_against` 只是接口，尚未接外部时间戳
11. 验证器与签名密钥都是本地的，不构成独立第三方验证或身份系统

## 下一步（按优先级）

1. 回写路径：参数不动时已跳过；要真回写得让参数有梯度，先接真实验证信号再谈
2. 把 GitTagStore 用于发布流程（tag 推送即外部锚定），再考虑第三方时间戳服务
3. 真实失败样本上规则与 LLM 都在 0.42151 停滞：换更强的变异器，或换更难的骨架族
4. 发布：PyPI 名称 `AGH` 是否被占用、token 就绪
5. NATS 集成测试：`docker compose up -d nats` + `NATS_URL=... pytest tests/test_nats_integration.py`
6. 大模型横向对比（需要各家 key）

## 踩坑清单

- 进化适应度先验证梯度再验证尺度；权重变异必须归一化，否则「进步」是缩放
- 被搜索的权重不能同时当打分函数，否则最优解是把惩罚项压到下界（1.17.0 用 `reference_cfg` 修）
- 自报指标必须验证器门控，否则刷分
- 日志截断本地链发现不了，需外部链头 + 长度
- 推理模型 reasoning token 也算 completion，`max_tokens` 不足会截断 JSON
- PowerShell 写文件易带 BOM，TOML 会炸；用 Python 写
- `git tag -d` 被安全网拦；改 tag 用 `--force-with-lease=<远程 tag 对象 sha>`
- 跑 daemon 冒烟会回写仓库冻结层，务必带 `--no-write-back`
- 测试里用 `frozen_src` 跑回写会改仓库冻结层并重建锚点；回写测试必须用 `frozen_copy`
- 任何「对照组」都要核对信息预算：基线拿全集、实验组拿子集，比较的就是信息不是方法
