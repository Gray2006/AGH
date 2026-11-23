# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

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
