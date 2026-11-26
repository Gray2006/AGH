# AGH

**给多智能体流水线做可验证审计的一层**：子级回传带签名与出处，母体验签、记账、入哈希链；事后能校验、能逐位重放、能锚定到外部。

进化实验保留在[研究记录](research.md)里，不是主推。

## 快速开始

```bash
pip install agh-gestalt
agh quickstart          # 30 秒看完整链路，不需要 key

# 或者接你自己的日志
agh import --from-jsonl my_log.jsonl
agh audit verify --log my_log.jsonl
agh ui --log my_log.jsonl
```

## 能做什么

| 命令 | 用途 |
|---|---|
| `agh run` | M0 垂直切片 |
| `agh experiment` | 竞技场实验（含基线） |
| `agh ablation` | 9 组消融 |
| `agh evolve --mode meta` | 档案式进化 + 课程 |
| `agh verify` / `replay` | 校验日志 / 逐位重放 |
| `agh report` | 汇总所有运行结果 |

## 设计边界

- 不做编排，做验证层
- 自报指标必须有验证器门控
- 进化只动受限参数，不做代码级自改（底座见 `selfmod` + `supervisor`）

完整限制见 [状态交接](STATUS.md)。
