# NATS / GitHub 仓库核验（2026-11-23）

核验入口：docs.nats.io 官方文档、nats-io/nats.py 源码、api.github.com。所有结论都带原文或代码位置，未命中项为 0。

## 一、仓库

| 项目 | 结论 | 许可 | 最近提交 | 量级 |
|---|---|---|---|---|
| [SpaceHunterInf/DMAD](https://github.com/SpaceHunterInf/DMAD) | REAL | CC-BY 4.0（非软件许可） | 2026-06-01 | 2 stars / 5 commits / 2 contributors |
| [jennyzzt/dgm](https://github.com/jennyzzt/dgm) | REAL | Apache-2.0 | 2025-08-13（约 15 个月无推送） | 2539 stars / 467 forks |
| [MineDojo/Voyager](https://github.com/MineDojo/Voyager) | REAL | MIT | 2023-07-27（已停更） | 7.3k stars / 710 forks |
| [kb1dds/pysheaf](https://github.com/kb1dds/pysheaf) | REAL | Apache-2.0 | 2024-11-07 | 159 stars / 274 commits |
| [AlgebraicJulia/CellularSheaves.jl](https://github.com/AlgebraicJulia/CellularSheaves.jl) | 组织名写错，应为 **AlgebraicJulia** | MIT | 2026-10-19，活跃 | 10 stars |
| [nats-io/nats.py](https://github.com/nats-io/nats.py) | REAL | Apache-2.0 | 2026-11-19 | 1271 stars / 298 forks，已改 monorepo |

- pysheaf README 确有 `Sheaf.ComputeConsistencyRadius()`；同时写「no PyPI package」又给 `pip install pysheaf`，自相矛盾，实际按 clone 安装
- DMAD 只宜作「论文配套代码」引用
- dgm、Voyager 不能称「活跃维护」

## 二、NATS 事实

**B1 去重不是 exactly-once**

header 页原文：`Unique message ID for deduplication. Messages with the same ID within the deduplication window will be rejected as duplicates.`
（<https://docs.nats.io/nats-concepts/jetstream/headers>）

去重窗口是 **stream 设置 Duplicate Window**（不是 header），示例默认 **2m0s**；JetStream 定位是 **at-least-once**：
`JetStream adds a persistence layer on top, giving you at-least-once delivery`
（<https://docs.nats.io/nats-concepts/jetstream>）

结论：去重只在**发布端**、只在**窗口内**有效，超窗重复消息会被再次存储。

**B2 ack 与重投**

- AckWait 默认 **30s**
- MaxDeliver 默认 **-1**（无限重投）
- 原文：`If a delivery is not ack'd, nak'd, or kept alive with in-progress before AckWait runs out, the server treats it as a silent failure and redelivers.`
- `A nak returns the message to the consumer, not to the worker that nak'd it`
- 重复消费触发条件：AckWait 到期未 ack，或客户端 nak；重投不保证回原 worker

<https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive/acknowledgment>

**B3 原子批量发布（ADR-50）**

`An atomic batch stores a group of messages all-or-nothing.`
stream 需 `AllowAtomicPublish`；客户端用 `Nats-Batch-Id` / `Nats-Batch-Sequence` / `Nats-Batch-Commit`；默认单批 **1000 条**、同时最多 **50 批**；10s 无消息批次被丢弃（`stream_batch_abandoned` advisory，无错误回包）；`Atomic batch was added in server 2.12.`

<https://docs.nats.io/using-nats/developer/develop_jetstream/model_deep_dive/advanced_publishing> · <https://github.com/nats-io/nats-architecture-and-design/blob/main/adr/ADR-50.md>

**B4 nats.py 支持度（源码 `nats-jetstream/`）**

- `JetStream.publish(subject, payload, *, headers=None, ...)`
- `PublishAck` 含 `duplicate` / `batch_id` / `batch_size`
- `StreamConfig` 含 `allow_atomic`（docstring 写 **Requires nats-server 2.14+**，与官方 2.12 冲突）、`duplicate_window`
- `nats/jetstream/headers.py` 有 `NATS_BATCH_*` 常量，**没有** `Nats-Msg-Id` / `Nats-Expected-*` 常量
- 结论：批量与期望序号都要手工打 header，没有一等 API；版本要求按实际 server 验证

**B5 [nats-server#4786](https://github.com/nats-io/nats-server/issues/4786)**

`JetStream should reject out-of-window acks.` open，proposal + stale，2023-11-09。超窗 ack 可能被算作对另一次投递的确认。

## 三、方案必须改的说法

1. 删「exactly-once」→ **at-least-once + 发布端窗口去重 + 消费端幂等**
2. 去重窗口写默认 2m 且可配（`duplicate_window`），不是永久/全局
3. `Nats-Msg-Id` 是可选 header，只在窗口内、只在发布端生效
4. ack 写清：AckWait 默认 30s、MaxDeliver 默认 -1；重复消费条件写全
5. 不承诺「重投回原 worker」
6. 原子批量标注 2.12+ / `AllowAtomicPublish` / 1000 条 / 50 批 / 10s abandoned
7. nats.py 批量是裸 header，非一等 API；版本冲突注明
8. 期望序号同样手写 `Nats-Expected-*` header
9. `JuliaAlgebra` 改 **AlgebraicJulia**
10. DMAD 许可 CC-BY 4.0；dgm、Voyager 不得称活跃维护

本项目 `agh/bus.py` 已按上述语义实现：`InProcBus` 只承诺去重 + 幂等 + 期望序号，测试 `tests/test_bus.py` 覆盖去重窗口过期、超时重投、nak 重排、消费端幂等。
