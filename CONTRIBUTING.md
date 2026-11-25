# 贡献指南

## 环境

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

python scripts/dev.py check   # lint + 全量测试（跨平台）
python scripts/dev.py test    # 只跑测试
python scripts/dev.py lint    # ruff + mypy + vulture
python scripts/dev.py docs    # 构建文档站
```

Python 3.11+。提交前 lint 与全量测试必须通过，CI 会跑 3.11 / 3.12 / 3.13，另加 Windows 与打包冒烟。

## 改动范围

- `agh/` 是库代码；`tests/` 跟着改
- `config/frozen/` 是冻结层。改阈值要重新生成锚点（`python -m agh --refresh-anchor`），并在 PR 说明里写清为什么改、影响哪些测试
- 不要提交 `runs/`、`config/anchor.json`、`__pycache__/`

## 代码风格

- lint 用 ruff，配置在 `pyproject.toml`（line-length 120，忽略中文全角标点的 RUF001-003）
- 保持现有风格：`from __future__ import annotations`、类型注解、短函数、纯函数优先
- 阈值不进代码，读冻结配置
- 新增不变量必须有测试；测试名写清「防的是什么」

## 什么时候 bump 版本

不是每次提交都发版。判断标准是「用户能不能感知到」：

| 改动 | bump 吗 |
|---|---|
| 新命令、新参数、新输出字段 | 是（minor） |
| 修 bug（用户会遇到的行为错误） | 是（patch） |
| 改分数语义 / 删字段 / 改签名 | 是（minor / major，标 Semantics） |
| 纯文档、README、CHANGELOG 措辞 | **不**，攒着跟下次一起发 |
| CI 配置、测试、开发脚本 | **不** |
| 内部重构（行为不变） | **不** |

攒着的意思是：这些改动正常提交，但不动 `version`、不打 tag。等下一次有用户可见变化时，
它们跟着一起进那一个版本。

反例（真实踩过）：一晚上连发 2.29.0–2.29.3，后三个分别是「修 CI 装包顺序」「加安全文档」
「改待办清单」，用户完全感知不到，却各占一个 tag。

已发布的 tag 不回退、不改写。

## 提交信息

Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`。一条改动一个主题。

## PR

- 描述里写：改了什么、为什么、怎么验证（命令与输出）
- 涉及安全边界（签名、冻结层、写入门、断言）的改动单独标注
- 不要在同一 PR 里混重构与行为变更

## 安全

发现签名绕过、锚点自引用、日志篡改、预算越权一类问题，不要开公开 issue，按仓库 Security 页的联系方式私下报。
