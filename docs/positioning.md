# AGH 的定位：验证层，不是编排框架

一句话：AGH 不是 LangGraph 的替代品，两者不在同一层。LangGraph 解决「怎么把任务跑起来」，AGH 解决「跑出来的东西凭什么可信、出了事能不能逐位重放」。把它当编排框架用会失望；把它当「多智能体结果的可验证性协议」看，才有意义。

> 本文所有外部项目与数字均于 2026-11-23 核验，未核实的不写进结论表（见文末「核验记录」）。

## 四类邻居

| 类别 | 代表 | 强在哪 | 缺什么 |
|---|---|---|---|
| 编排框架 | [LangGraph](https://www.langchain.com/langgraph)、[Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/)、CrewAI、OpenAI Agents SDK | 生态、生产可用、durable execution、checkpoint、人工介入、可观测接入 | 没有密码学意义的出处；重放靠状态快照；预算靠自觉 |
| 可观测 / 评测 | LangSmith、Langfuse、AgentOps、Braintrust | 把 trace 记全，做评测、成本、调试 | 记录是给人看的，日志本身可改，没有「母体验证子级」的强制门 |
| 审计 / 可复现研究 | [awesome-auditable-ai](https://github.com/yzhao062/awesome-auditable-ai) 生态、[arXiv 2606.04990 证据溯源综述](https://arxiv.org/abs/2606.04990) | 把「事后归因」做成一门学问 | 多数是记录与诊断，不是运行时的强制约束 |
| 底层可复现 / 出处技术 | Temporal（确定性重放）、in-toto / Sigstore / SLSA、W3C PROV-DM | 工程上已经成熟 | 不是为 LLM 智能体设计的，语义单元对不上 |

AGH 的引用来源也能说明位置：它对照的文献是记忆投毒（MAPLE-Guard、SMSR）、辩论与投票（Debate or Vote）、自改进智能体（DGM、Gödel Agent），属于智能体安全与可信研究，不是工程编排。

## 四个近似项目（都真实存在，但都不是 AGH）

| 项目 | 是什么 | 有 | 没有 |
|---|---|---|---|
| [Sovereign-OS](https://github.com/Justin0504/Sovereign-OS)（[arXiv 2603.14011](https://arxiv.org/abs/2603.14011)） | 宪章（Charter）治理的自治智能体 OS 原型 | 宪章约束、CFO 国库预算闸门、审计哈希 | 没有骨架-完形重构，没有多候选竞技场，没有字节级重放 |
| [DOAgent](https://github.com/cabrerac/doagent) | 以共享数据为接口的可问责多智能体库 | 数据模型即接口、贡献来源记录 | 来源非网关强制签名；无预算账本、无竞技场 |
| [Bernstein](https://github.com/sipyourdrink-ltd/bernstein)（[官网](https://bernstein.run/why-bernstein)） | 代码智能体的开源治理层 | HMAC 审计链、确定性调度、可重放、Merkle 封存 | 面向代码 Agent 的流水线，不是重构保真评估；beta，单人维护 |
| Hypermind | 二手资料称为 IETF SCITT 方向争议协议 SDK | — | **未核到对应仓库或文档，本文不采信** |

## AGH 真正不同的四点

1. **出处由网关签发，不采信自报**：子级回传结构里没有 provenance 字段，伪造被 HMAC 校验打回。可观测工具是「记录你说的」，AGH 是「验证你说的是不是真的」。
2. **冻结层锚点**：阈值与脚本放目录外签名，谁悄悄改了配置都会被锚点发现。主流框架的阈值写在代码或 yaml 里，改了没有痕迹。
3. **预算先授权**：预授权、幂等结算、超预留记违规；编排框架只有递归上限与 token 统计。
4. **纯函数仲裁 + L1 逐位重放**：固定种子，哈希链日志，重放时逐位比对。Temporal 有确定性重放但不针对 LLM 输出；LangGraph 的 checkpoint 复现状态，不复现决策。

再加「给骨架不给答案、子级必须整体重构」的完形契约：从整体到部分的结构能否保真，是评估里很少有人认真做的一件事。

## 短板

- M0 子级是规则函数，不接 LLM；0.62025 的分数不代表真实模型行为，G1 竞技场实验未做
- 单作者、2026-11-23 建仓、无生产集成、无 SDK、无社区
- 开发密钥、哈希链无时间戳证明、冻结层防不了持钥者，均在 README 边界里写明
- 预算账本只对走自己总线的调用生效，接不了外部计费

## 选型

- **上线做产品**：LangGraph 或 Microsoft Agent Framework；AGH 不在候选里
- **要可审计、可复现、要「子级别自称可信」**：AGH 的思路比现有框架更进一步；最接近的组合是审计生态 + Temporal，但都没有「运行时就拦」的设计
- **要评估多智能体输出质量**：AGH 的打分（校准置信、垂直一致性、覆盖率、多样性、异议）比「跑通就行」严谨，但必须先接真实模型

旁证：[awesome-auditable-ai](https://github.com/yzhao062/awesome-auditable-ai) 自述「Consistency and Determinism 是覆盖最薄的一维，八个直接资源，对面 Security Review 有 76 个」。方向确实是空白，但 AGH 现在填的是草图。

## 核验记录（2026-11-23）

| 条目 | 结论 | 依据 |
|---|---|---|
| arXiv 2606.04990 | 真实，标题 *From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents* | arXiv abs 页 |
| awesome-auditable-ai 8 vs 76 | 原文一致 | 仓库 README「Coverage note」 |
| Sovereign-OS / arXiv 2603.14011 | 真实 | 仓库与 arXiv |
| DOAgent | 真实 | GitHub cabrerac/doagent |
| Bernstein | 真实，beta、单人维护 | 官网 why-bernstein 与仓库 |
| Hypermind（SCITT 争议协议 SDK） | 未核实，不采信 | 多次检索无对应仓库/文档 |
| 「AGH 私有仓库」 | 错误：2026-11-23 起为公开仓库 | GitHub |
| 「101 条测试」 | 当前 102 | pytest |

## 参考

- [LangGraph](https://www.langchain.com/langgraph) · [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/overview/)
- [From Agent Traces to Trust (arXiv 2606.04990)](https://arxiv.org/abs/2606.04990)
- [Awesome Auditable AI](https://github.com/yzhao062/awesome-auditable-ai)
- [Sovereign-OS](https://github.com/Justin0504/Sovereign-OS) · [DOAgent](https://github.com/cabrerac/doagent) · [Bernstein](https://bernstein.run/why-bernstein)
