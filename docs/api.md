# 模块 API

| 模块 | 作用 |
|---|---|
| `agh.contracts` | 骨架/契约/重构模型，JSON Schema 硬化 |
| `agh.crypto` | HMAC/Ed25519 签名、验签顺序、结算签名 |
| `agh.bus` / `agh.bus_nats` | 总线语义 + JetStream 适配 |
| `agh.ledger` | 预算预授权、幂等结算、违规记账 |
| `agh.frozen` | 冻结层锚点 |
| `agh.arena` | 打分、硬过滤、异议、仲裁 |
| `agh.gate` | 写入/检索/提升/复用四门 |
| `agh.governance` | 八状态机、T0/T1/T2 |
| `agh.eventlog` / `agh.sqlite_log` | 哈希链日志与 SQLite 实现 |
| `agh.evalstats` / `agh.calibration` | 统计检验与评分器校准 |
| `agh.llm` / `agh.providers` | 子级适配与模型接入 |
| `agh.experiment` / `agh.ablation` | 实验与消融 |
| `agh.evolution*` / `agh.meta` | 进化、对照、元进化 |
| `agh.verifier` | 结构/覆盖/模型裁判验证器 |
| `agh.selfmod` / `agh.supervisor` | 自改底座与独立监督者 |
| `agh.costs` | token 用量折算预算 |
| `agh.sdk` / `agh.cli` | SDK 与命令行 |
