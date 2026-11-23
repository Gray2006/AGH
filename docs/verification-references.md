# 2026-11 技术方案引用核验报告

核验时间：2026-11-23（Asia/Shanghai）
核验入口：arXiv abs 页与官方 API（export.arxiv.org/api/query）、ACL Anthology（含 2026.findings-acl.1694 页面）、OpenAlex API、GitHub REST API。Semantic Scholar API 本次返回 HTTP 429（限流），未作为证据来源。

结论概览：13 条编号全部真实存在，无编造编号、无 NOT_FOUND。命中问题 1 处硬数据错误（第 10 条）、1 处标题不完整（第 13 条）、1 处标题省略副标题（第 9 条）。第 2 条第 4 条第 6 条等细节数据（65.3%→5.3%、n=150、p=0.80、五原语名称）均与原文逐字一致。

## 逐条核验表

| # | 编号 | 方案声称 | 结论 | 实际标题 / 关键事实 | 来源 |
|---|---|---|---|---|---|
| 1 | 2608.00426 | MAPLE-Guard：记忆当受治理状态，写入/检索/提升/跨体复用四检查点，定位入侵后遏制 | REAL | MAPLE-Guard: Memory-Aware Link Enforcement Against Memory-Link Poisoning in Multi-Agent Systems；摘要在 write / retrieval / promotion / cross-agent reuse 四处设门；ASR 38.2%→0.9%（LongMemEval）、34.7%→0.2%（AppWorld） | https://arxiv.org/abs/2608.00426 |
| 2 | 2606.12703 | SMSR：HMAC-SHA256 写入签名 + 随机记忆消融多数裁决；65.3%→5.3%（n=150） | REAL | SMSR: Certified Defence Against Runtime Memory Poisoning in Persistent LLM Agent Systems；HMAC-SHA256 写入、randomised memory ablation + verdict-based majority voting、端到端 65.3%→5.3%（n=150）逐字一致 | https://arxiv.org/abs/2606.12703 |
| 3 | 2606.12290 | 图记忆选择完整性：只校验被检索记录来源的防御对结构选择通道盲 | REAL | Selection Integrity for LLM Graph Memory: An Accumulability Criterion for Information-Flow-Blind Retrieval；摘要即"整类 provenance 防御 by construction 盲"，给出 $28/499 账本转账实例 | https://arxiv.org/abs/2606.12290 |
| 4 | 2608.21230 | Utility Under Attack：来源先验软排序默认权重与无防御统计无差异（p=0.80） | REAL | Utility Under Attack: Agent Memory Poisoning and the Limits of Content Screening and Provenance Ranking；"shipped weight is statistically indistinguishable from no defense (p=0.80)" | https://arxiv.org/abs/2608.21230 |
| 5 | 2607.29167 | 记忆溯源洗白：摘要环节洗掉来源 | REAL | Memory Provenance Laundering in LLM Agents: A Non-Amplification Firewall for Persistent Memory；memory consolidation 把外部观察改写成用户历史、抹掉低信任来源 | https://arxiv.org/abs/2607.29167 |
| 6 | 2604.16548 | 长期记忆安全综述：五原语（写授权、来源可见、主体范围检索、可回滚、可验证遗忘） | REAL | A Survey on Long-Term Memory Security in LLM Agents: Attacks, Defenses, and Governance Across the Memory Lifecycle；VMG 五原语原文为 Write Authorization / Provenance Visibility / Principal-Scoped Retrieval / Rollbackability / Verified Forgetting，与方案中文译名一一对应 | https://arxiv.org/abs/2604.16548 |
| 7 | 2606.03032 | Deliberative Illusion：讨论抹去多达 72% 关键事实，立场熵塌缩 | REAL | The Deliberative Illusion: Diagnosing Factual Attrition and Stance Homogenization in Multi-Agent LLM Deliberation；"erases up to 72% of issue-critical facts"；stance homogenization 即方案所称立场熵塌缩 | https://arxiv.org/abs/2606.03032 |
| 8 | 2601.19921 | Demystifying MAD（ACL 2026 Findings）：原版辩论常不如简单多数投票 | REAL | Demystifying Multi-Agent Debate: The Role of Confidence and Diversity；ACL Anthology 收录，Findings of ACL 2026，pp. 33909–33930，DOI 10.18653/v1/2026.findings-acl.1694；摘要含"vanilla MAD often underperforms simple majority vote" | https://aclanthology.org/2026.findings-acl.1694/ |
| 9 | 2603.20640 | Hear Both Sides | REAL | Hear Both Sides: Efficient Multi-Agent Debate via Diversity-Aware Message Retention；方案漏写副标题 | https://arxiv.org/abs/2603.20640 |
| 10 | 2505.22954 | Darwin Gödel Machine（jennyzzt/dgm）：SWE-bench 23.0% → 50.0% | REAL（数值错误） | Darwin Godel Machine: Open-Ended Evolution of Self-Improving Agents；v1 与 v3 摘要均为 SWE-bench **20.0% → 50.0%**、Polyglot 14.2% → 30.7%，无 23.0% 这一数字；代码库 https://github.com/jennyzzt/dgm 存在且描述一致 | https://arxiv.org/abs/2505.22954 |
| 11 | 2305.16291 | Voyager（MineDojo/Voyager）：可执行技能库 + 描述嵌入索引 | REAL | Voyager: An Open-Ended Embodied Agent with Large Language Models；§2.2 原文"Each program is indexed by the embedding of its description"，键为程序描述嵌入、值为程序本身，检索 top-5；GitHub 仓库 MineDojo/Voyager 存在（MIT，7.3k stars） | https://arxiv.org/abs/2305.16291 |
| 12 | 2605.31005 | Sheaf-ADMM（声称 ICML 2026） | REAL | Learning Multi-Agent Coordination via Sheaf-ADMM；arXiv comment 明写 "Accepted at ICML 2026"；cellular sheaf 约束 + 展开 ADMM + 反传 | https://arxiv.org/abs/2605.31005 |
| 13 | 2504.02049 | Cellular Sheaves | REAL（标题不完整） | 实际标题 Distributed Multi-agent Coordination over Cellular Sheaves；"Cellular Sheaves"只是主题词，不是论文名 | https://arxiv.org/abs/2504.02049 |

## 补充：已核验编号与标题的替代/加固文献（2024–2026）

| 编号 | 标题 | 证据状态 | 对方案的直接支撑 |
|---|---|---|---|
| 2402.07867 | PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models | REAL，USENIX Security 2025，GitHub sleeepeer/PoisonedRAG | 记忆投毒的上游标准基线：5 条恶意文本即可 90% ASR，方案讲"写入污染"必须引它做威胁模型起点 |
| 2512.16962 | MemoryGraft: Persistent Compromise of LLM Agents via Poisoned Experience Retrieval | REAL，GitHub Jacobhhy/Agent-Memory-Poisoning | 经验检索型持久污染，直接支撑方案"记忆即攻击面、跨会话持久"的立论，且演示"良性摄入工件→毒化经验库"链条 |
| 2510.02373 | A-MemGuard: A Proactive Defense Framework for LLM-Based Agent Memory | REAL，GitHub TangciuYueng/AMemGuard | 共识校验 + 双记忆"lessons"，正好支撑方案写入/检索两检查点的"自检自纠"设计，且报告 ASR 降幅 >95% |
| 2608.21867 | MemGuard: Persisting Verifier Signals for LLM-Agent Memory Governance | REAL，GitHub whyyyyy123/MemGuard | 把验证器信号作为持久生命周期元数据，支撑方案"提升/归档阶段仍需治理"这一检查点的必要性 |
| 2402.06782 | Debating with More Persuasive LLMs Leads to More Truthful Answers | REAL，ICML 2024，GitHub ucl-dark/llm_debate | 辩论有效的正面证据（非专家评审 76%/88% vs 基线 48%/60%），与方案"辩论 vs 投票"一节构成对照 |
| 2508.17536 | Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models? | REAL，NeurIPS 2025 Spotlight，GitHub deeplearning-wisc/debate-or-vote | 拆解出多数投票贡献了 MAD 大部分收益、辩论本身是鞅；比第 8 条更直接地支撑"原版辩论常不如投票" |
| 2410.04444 | Gödel Agent: A Self-Referential Agent Framework for Recursive Self-Improvement | REAL，ACL 2025 main，GitHub Arvid-pku/Godel_Agent | 自我改写但无版本档案的对照组，可反衬 DGM 的 archive 设计价值 |
| 2504.15228 | A Self-Improving Coding Agent | REAL，NeurIPS 2025 投稿，SWE-bench Verified 随机子集 17%→53% | DGM 之外的自改进智能体版本演化证据，支撑方案"版本档案 + 基准验证"路线 |

## 必须从方案里撤掉或替换的清单（按严重度）

1. 【必须改，硬伤】第 10 条 SWE-bench 数字 `23.0% → 50.0%` 改为 `20.0% → 50.0%`。arXiv v1 与 v3 摘要一致写 20.0%，方案里的 23.0% 无任何版本依据。若该数字被用于推导收益幅度或对比表，需连带复核结论。
2. 【必须改，错引】第 13 条不得以 `Cellular Sheaves` 作论文标题引用，应改为 `Distributed Multi-agent Coordination over Cellular Sheaves`（2504.02049），否则属标题与编号不符。
3. 【必须补，格式】第 9 条补全副标题 `Efficient Multi-Agent Debate via Diversity-Aware Message Retention`；第 12 条标注"arXiv 预印本，已被 ICML 2026 接收"，避免把预印本当正式会议论文引。
4. 【必须标，证据等级】第 2、3、5、6 条均为 2026 年 arXiv 预印本（第 6 条自述为 EMNLP 2026 论文扩展版，第 5 条为 EMNLP 2026 投稿），方案若把它们当"已同行评审结论"使用需降级标注。第 8 条是唯一已完成 ACL 2026 Findings 出版的条目。
5. 【建议替换，覆盖不足】"记忆投毒防御"目前只引 MAPLE-Guard 与 SMSR 两篇同源新预印本，缺经典基线。至少补 PoisonedRAG（2402.07867）作威胁模型基线、A-MemGuard（2510.02373）作防御对照、MemoryGraft（2512.16962）作持久化污染证据。
6. 【建议替换，论证更稳】"辩论 vs 投票"若只引第 8 条，建议并列 Debate or Vote（2508.17536，NeurIPS 2025 Spotlight），其"投票贡献大部分收益、辩论是鞅"的结论比第 8 条更硬。
7. 【建议补，对照组】"自我改进智能体版本档案"只引 DGM 一条，建议补 Gödel Agent（2410.04444，无档案的对照组）与 SICA（2504.15228），使"为什么需要 archive"有对照。
