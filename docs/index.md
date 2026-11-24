# AGH

**可审计的多智能体重构框架**：契约约束子级输出，签名保证出处，竞技场做多候选比对，进化在受限基因组上迭代，所有过程可重放、可校准。

## 快速开始

```bash
pip install -e ".[dev]"
python -m pytest
python -m agh run
python -m agh report --runs runs
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
