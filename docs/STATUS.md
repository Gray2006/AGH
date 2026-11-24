# AGH 状态交接（v1.10.1）

一句话：**机制完整、证据分层、缺口明确**。下面是给后来者（或三个月后的自己）的现状。

## 能跑什么

```bash
pip install -e ".[dev]"
python -m pytest                 # 230 条
python -m agh run                # M0 垂直切片
python -m agh experiment --seeds 50
python -m agh ablation --seeds 30
python -m agh evolve --mode meta --rounds 8
python scripts/red_team.py       # 7 类攻击，全拦住
```

真实模型（需要 `COMMAND_CODE_API_KEY`）：

```bash
python scripts/run_llm_experiment.py --provider command-code --samples 30 --verifier structural
python scripts/run_llm_bench.py --provider command-code --benchmarks 50 --min-nodes 7 --max-nodes 8
python scripts/make_real_packet.py   # 挑真实失败样本给人标注
```

## 证据（按可信度排序）

| 结论 | 数字 | 可信度 |
|---|---|---|
| 分片精英优于单基因组 | +0.0689（CI 0.0167–0.1162，n=10） | 高：配对统计 |
| 真模型跨 10 骨架低于规则子级 | -0.0685（CI -0.1128–-0.0237） | 高：配对统计 |
| 加难后差距扩大 | -0.0904（12 骨架）、-0.0648（50 骨架） | 高 |
| 验证器二值决策与人工一致 | kappa 1.0（构造负例 10 题、真实失败 9 题） | 中高：样本小 |
| 验证器概率校准 | ECE 0.241 | 未成立：分级分 vs 二值标签 |
| 温度不影响结论 | 0.2 与 0.9 均低于基线 | 中：样本 12–40 |

## 已知限制（都写进了 README）

1. **单一模型**：command-code 端点只支持 `deepseek/deepseek-v4.1-flash`，多模型对比做不了
2. **概率校准缺失**：验证器分数不是概率；要校准需要分级人工标签
3. **规则子级的局限**：进化的适应度来自规则子级，不代表模型能力
4. **NATS 只验证语义**：适配器有测试，没起真 JetStream 联调
5. **自改未启用**：`selfmod` + `supervisor` 是底座，没有真正让 AGH 改自己代码

## 踩过的坑（值得记住）

- 进化适应度先验证梯度，再验证尺度：权重变异不归一化会让「进步」变成缩放
- 自报指标必须有验证器门控：`vertical_consistency` 曾按候选自报算，自报即可刷分
- 日志截断本地哈希链发现不了，必须外部链头 + 长度
- 推理模型的 `reasoning token` 也算 completion，`max_tokens` 不足会截断 JSON
- PowerShell 写文件容易带 BOM，TOML 会炸；用 Python 写

## 如果要继续

优先级从高到低：

1. **分级人工标签**：给验证器打分（0/0.5/1）而不是二值，才能校准概率
2. **多模型**：换端点或加 key，看 -0.07 的结论是否跨模型成立
3. **NATS 真联调**：起 JetStream，验证 ack 超时重投与幂等
4. **代码级自改**：需要沙箱 + 独立权限 + 人工审批，风险最高
