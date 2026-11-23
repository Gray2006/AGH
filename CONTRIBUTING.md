# 贡献指南

## 环境

```bash
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q
```

Python 3.12+。提交前全量测试必须通过，CI 会跑 3.12 / 3.13。

## 改动范围

- `agh/` 是库代码；`tests/` 跟着改
- `config/frozen/` 是冻结层。改阈值要重新生成锚点（`python scripts/run_m0.py` 会写），并在 PR 说明里写清为什么改、影响哪些测试
- 不要提交 `runs/`、`config/anchor.json`、`__pycache__/`

## 代码风格

- 无 linter 强制，但保持现有风格：`from __future__ import annotations`、类型注解、短函数、纯函数优先
- 阈值不进代码，读冻结配置
- 新增不变量必须有测试；测试名写清「防的是什么」

## 提交信息

Conventional Commits：`feat:` / `fix:` / `docs:` / `test:` / `refactor:` / `chore:`。一条改动一个主题。

## PR

- 描述里写：改了什么、为什么、怎么验证（命令与输出）
- 涉及安全边界（签名、冻结层、写入门、断言）的改动单独标注
- 不要在同一 PR 里混重构与行为变更

## 安全

发现签名绕过、锚点自引用、日志篡改、预算越权一类问题，不要开公开 issue，按仓库 Security 页的联系方式私下报。
