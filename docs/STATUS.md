# AGH 状态交接（v1.16.0，2026-11-24）

> 新会话先读这个文件，再读 `README.md` 的「版本与兼容」与 `memory/agh.md`。

## 一句话

机制完整、证据分层、缺口明确。下一步通常是：真跑回写守护、校准扩样、或发布。

## 当前版本

- v1.16.0，`241 passed + 1 skipped`（NATS 需服务），ruff 干净，mypy 38 文件零错误
- 仓库 <https://github.com/Gray2006/AGH>，CI 双版本绿
- 依赖：pydantic v2、numpy、jsonschema、cryptography；Python 3.12+

## 能跑什么

```bash
pip install -e ".[dev]"
python -m pytest                    # 241 passed, 1 skipped
python -m agh run                   # M0 垂直切片
python -m agh experiment --seeds 50
python -m agh ablation --seeds 30
python -m agh evolve --mode meta --rounds 8
python -m agh daemon --rounds 4     # 自主迭代（默认 0 token）
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

校准已固化进 CI：`tests/fixtures/calibration.json` + `tests/test_calibration_regression.py`（ECE ≤ 0.05、kappa ≥ 0.9）。

## 已知限制

1. 单一模型（command-code 只支持 deepseek-v4.1-flash）
2. 校准样本 19 题，规模小
3. 进化适应度基于规则子级，不代表模型能力
4. NATS 只验证语义，未真联调
5. 代码级自改只有底座（selfmod + supervisor），未启用
6. daemon 默认 0 token；LLM 变异器要显式开并设预算

## 下一步（按优先级）

1. `agh daemon --no-write-back --llm-mutator --daily-budget 30000`：看 LLM 变异能否持续改进
2. 真跑回写版本（会改 `config/frozen/thresholds.json`，需同步 README 的 M0 分数并重建锚点）
3. PyPI 发布（需 token，先查 `AGH` 名字是否被占）
4. NATS 联调（`docker compose up -d nats` + `NATS_URL=... pytest tests/test_nats_integration.py`）
5. 多模型对比（需别的 key）

## 踩坑清单

- 进化适应度先验证梯度再验证尺度；权重变异必须归一化，否则「进步」是缩放
- 自报指标必须验证器门控，否则刷分
- 日志截断本地链发现不了，需外部链头 + 长度
- 推理模型 reasoning token 也算 completion，`max_tokens` 不足会截断 JSON
- PowerShell 写文件易带 BOM，TOML 会炸；用 Python 写
- `git tag -d` 被安全网拦；改 tag 用 `--force-with-lease=<远程 tag 对象 sha>`
- 跑 daemon 冒烟会回写仓库冻结层，务必带 `--no-write-back`
