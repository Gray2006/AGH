# AGH v3.1 · M0 实现报告（2026-11-23）

对应方案：`AGH v3.1 优化版项目方案`。本报告只写「已经跑起来的」，不写「计划中」。

## 一、范围

M0 = 1 母体 + 1 父 + 3 子（规则重构器）的**垂直切片**，把方案里最难同时成立的约束串成一条能跑、能测、能重放的链路：

母体发骨架与契约 → 账本预授权 → 子级回传并签名 → 写入门验签/风险/污点 → 硬过滤与打分
→ 多样性预检 → 异议判定 → 纯函数仲裁 → 治理机 → 账本结算 → 哈希链日志 → L1 逐位重放。

不接 LLM：子级是规则重构器，输出全量落日志，因此 L1 可逐位重放。接真模型后子级输出照旧落日志，L1 仍成立，只有 L2 需要统计等价。

## 二、目录

```
agh/
├─ agh/
│  ├─ contracts.py   单一真相源（Pydantic v2，extra=forbid，frozen；JSON Schema 硬化）
│  ├─ crypto.py      HMAC 网关签名 / 验签顺序 / 污点传播 / 结算签名
│  ├─ bus.py         去重 + 幂等 + 期望序号（不承诺 exactly-once）
│  ├─ ledger.py      调用前预算预授权、幂等结算、超预留违规
│  ├─ frozen.py      冻结层 + 目录外签名锚点 + 自引用拒绝
│  ├─ arena.py       校准置信 / 垂直一致性 / 覆盖率 / 硬过滤 / 异议 / 仲裁
│  ├─ gate.py        写入门 / 检索门 / 提升门 / 复用门
│  ├─ governance.py  八状态机 + T0/T1/T2 分级 + 劣化停车
│  ├─ eventlog.py    哈希链日志 + L1 重放 + L2 统计等价
│  ├─ evalstats.py   bootstrap CI / Holm / Cohen's d
│  └─ pipeline.py    M0 编排 + reducer + 演示冻结层
├─ config/frozen/    thresholds / risk_model / phase_gates / scripts/go_no_go.py
├─ scripts/run_m0.py 一键跑 M0 并落盘
└─ tests/            10 个测试文件，95 条
```

## 三、需求落点

| 方案条目 | 实现 |
|---|---|
| D1 子级零信任、四门 | `gate.py`：验签失败直接拒收；`admit` 不采信自报 trust，`derive_trust` 取输入最小值 |
| D2 冻结层自引用 | `frozen.py`：锚点在冻结目录外、网关密钥签名；放进冻结目录抛 `SelfReferenceError`；写冻结路径抛 `FrozenLayerError` |
| D3 垂直移动 | `arena.vertical_consistency` 只算 `vertical=True` 的移动；无垂直移动返回 0，`ScoreBreakdown.notes` 记「无垂直移动，vc 归零」 |
| D4 风险模型进冻结配置 | `risk_model.json` + `RiskModel.from_frozen`；高风险条目不进主池，进隔离池 |
| D6 命名与 provenance | `ChildSubmission.payload` 结构里没有 provenance；`extra="forbid"`；`reconstruction_schema` 用 allOf + contains |
| D7 预算向量 | `BudgetVector`（compute_units / wall_ms / usd），`ledger.py` 预授权 + 幂等结算 |
| D8 可重放 | `eventlog.py`：哈希链 + L1 逐位重放；L2 另设统计等价 |
| D9 总线 | `bus.py`：发布端去重、消费端幂等、期望序号；显式声明 at-least-once |
| D10 治理 | 八状态机；T0 自动（需复验计数）、T1 自动验证后发布、T2 人工；冻结层改动直接拒 |
| D11 阈值进冻结配置 | `thresholds.json` 覆盖 arena / calibration / ledger / gate / governance |
| D12 结算重放 | `SettlementVerifier` 校验 judge_version_hash + epoch/seq + nonce |
| D13 检索门选择完整性 | `RetrievalGate`：边指向不存在/低信任/未复验投机边即 block 并记 violation；高风险条目随机消融复核 |
| §4.4 统计 | `evalstats.py`：配对 bootstrap、Holm 9 组、Cohen's d；预注册参数在 `phase_gates.json` |

## 四、实测结果

`python scripts/run_m0.py`：

- 胜者 `child-faithful`，得分 0.62025；异议 `child-dissent` 得分 0.476、novelty 1.0
- 伪造 provenance 的提交：`payload_hash_mismatch` 拒收（写入门之前）
- `child-shallow`：硬过滤拒收（parts 缺 C2）
- 多样性：3 簇、最小两两距离 0.6、充足
- 仲裁：`winner_changed=false`、`contested_removed=true`（异议没有改变胜者，只把结论标成 contested）
- 存在合格异议 → 发布升 T2，停在 `VERIFIED` 等人工；`human_approved=True` 时到 `RELEASED`
- 账本违规 0，L1 重放 `bit_exact=true`

`python -m pytest -q`：**95 passed**（10 个文件）。

## 五、与规格的偏离（都是有意的）

1. **L1 / L2 分开**：原规格要求「replay 与原运行一致」，但 LLM 输出非确定，单级做不到。L1 重放记录下来的子级输出，逐位一致；L2 重跑只要求统计一致。
2. **总线不写 exactly-once**：按 NATS 实际语义（at-least-once + 发布端窗口去重 + 消费端幂等）实现，测试覆盖窗口过期与超时重投。见 `NATS与仓库核验_2026-11.md`。
3. **治理按风险分级**：八状态全保留，但 T0 自动、T1 自动验证、T2 人工，「一切修改都走八状态」会把技能固化卡死。
4. **置信必须有验证器信号**：只有自报 confidence 时校准置信返回 0，避免自报高分。
5. **信号格式**：`Calibration.combine` 接受 `None` 表示「无验证器信号」，不用 -1 当哨兵。
6. **冒烟测试改用也不开始会话**：`go_no_go.py` 读 `results.json` 做 eq/gt/lt 判定，锚点存在时先比 manifest。

## 六、还没做的

- 真 LLM 子级接入（当前是规则重构器；接口已按 `GestaltReconstruction` 固定）
- NATS 适配器（`Bus` 协议已在，`InProcBus` 是阶段 0 替身）
- HMAC 换 Ed25519（生产要求，`crypto.py` 已注明）
- G1 竞争竞技场的正式实验与 9 组消融（统计工具与预注册参数已就位，缺实验数据）
- Go/No-Go 的 `results.json` 样例与 CI 接线

## 七、引用问题（来自独立核验）

13 条编号全部真实存在，但 4 处要改：

1. arXiv 2505.22954 (DGM) 的 SWE-bench 是 **20.0%→50.0%**，不是 23.0%→50.0%，连带收益结论要复核
2. arXiv 2504.02049 标题应为 **Distributed Multi-agent Coordination over Cellular Sheaves**，不能只写 Cellular Sheaves
3. 2603.20640 漏副标题：**Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention**
4. 2605.31005 应标「预印本，已被 ICML 2026 接收」；2606.12703 / 2606.12290 / 2607.29167 / 2604.16548 均为 2026 预印本，不能当同行评审结论

建议补：PoisonedRAG (2402.07867)、MemoryGraft (2512.16962)、A-MemGuard (2510.02373)、MemGuard (2608.21867)、Debate or Vote (2508.17536)、Gödel Agent (2410.04444)、SICA (2504.15228)。详见 `引用核验_2026-11_技术方案.md`。
