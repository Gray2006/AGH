# 动机与自我调节：五个理论怎么落到 AGH

> 这不是综述，是把五个理论拆成 AGH 能实现、能测的机制。每条都标了「可测 / 不可测」。

## 一句话结论

AGH 现在只有一个动机源：**绝对分数最大化**。这正是 SDT 说的「外部控制型动机」——
它会让系统只做能立刻涨分的事，遇到瓶颈就停。五个理论合起来给的是另一种结构：
**目标分级（目标设定）+ 过程自省（SRL）+ 情境触发（实施意图）+ 进步奖励（计算内在动机）+ 自主选择（SDT）**。

## 映射表

| 理论 | 核心主张 | AGH 现状 | 缺口 | 可落地的机制 |
|---|---|---|---|---|
| SDT（Ryan & Deci） | 自主 / 胜任 / 归属三需求；外部奖励削弱内在动机 | 子级只能按母体给的骨架重构，策略由变异器决定 | 没有「自己选」的环节 | 子级从母体给的目标池里自选，母体只定约束 |
| SRL（Zimmerman） | 三阶段循环：forethought → performance → self-reflection | 有评估，无自省 | 子级不回看自己的历史 | 子级记录失败模式，下一轮提示里引用 |
| 目标设定（Locke & Latham） | 具体 + 有难度 + 有反馈 → 更高绩效；具体目标降低绩效方差 | 目标是「分数最大化」，笼统 | 目标不具体、无难度分级 | 分级目标：visible → hidden → held-out，逐级解锁 |
| 实施意图（Gollwitzer） | if-then 计划把意图绑定到情境线索 | 策略是参数向量（权重、tau、采样数） | 没有情境结构 | 策略编码为「如果输入满足 X 则做 Y」的规则集 |
| 计算内在动机（Oudeyer / Schmidhuber） | 内在奖励 = **学习进步**（预测误差的下降），不是新奇度 | fitness = 绝对分数 | 无进步信号 | 奖励 = 本轮分数 − 上轮分数（LP） |

## 三个值得先做的改动

### 1. 把奖励从「绝对分数」换成「学习进步」（LP）

**文献依据**：Oudeyer 等指出，新奇度和复杂度本身不是好的探索信号——环境里充满
「新奇但学不会」的东西；只有**预测误差在下降**的区域才值得投入（[Oudeyer et al. 2016](http://www.pyoudeyer.com/oudeyerGottliebLopesPBR16.pdf)）。

**为什么对 AGH 关键**：前面所有负面结果都指向同一件事——种子在分数顶点，
任何变异都只减分，所以搜索没有梯度。用 LP 后，**从 0.55 到 0.58 是正奖励，从 0.58 掉到 0.56 是负奖励**，
梯度回来了，哪怕最终分数不高。

**可测**：同一批任务，fitness 用绝对分数 vs 用 Δ分数，看曲线形状和最终值。

### 2. 分级目标，而不是「最大化」

**文献依据**：Locke & Latham 的元分析结论是「具体且有难度的目标」优于「尽力而为」，
且具体目标降低绩效方差（[Locke & Latham 2002](https://med.stanford.edu/content/dam/sm/s-spire/documents/PD.locke-and-latham-retrospective_Paper.pdf)）。

**为什么对 AGH 关键**：现在契约只说「覆盖必需项」，子级不知道「先做到什么算及格」。
分级目标让反馈有意义：过了 visible 才有 hidden 的反馈，过了 hidden 才看 held-out。

**可测**：分级目标 vs 单一分数目标，看子级在第几轮达到 visible 全过。

### 3. 策略编码成 if-then

**文献依据**：Gollwitzer 的实施意图——把「我要做 X」变成「如果情境 S 出现，就做 R」，
执行率显著提高，因为它把决策从当下挪到了事前（Gollwitzer, *Am Psychol* 1999, 54(7):493-503）。

**为什么对 AGH 关键**：现在的策略是参数向量，变异是调数字，语义上是黑的。
改成 if-then 规则后，变异有语义（改条件、加规则），而且**边界条件天然可表达**——
代码任务里最容易错的就是边界（空输入、单元素、负数）。

**可测**：if-then 规则集 vs 参数向量，在带边界的任务上比 hidden 通过率。

## 不做 / 不可测

- **归属需求（SDT 第三项）**：需要子级之间有真实交互。蜂巢预实验已经否过
  （分片合并 ≤ 单体，0.5534 vs 0.5563），不重启。
- **「内在动机」的心理学测量**：AGH 没有主观体验，只能测行为代理指标（探索多样性、坚持轮数）。
  任何声称「AGH 有内在动机」的说法都是过度解释。
- **用 SDT 解释分数提升**：即使加了自主选择后分数变好，也不能归因于「内在动机」——
  可能是选择本身带来了更好的初始化。这类归因需要消融实验，成本高、收益低。

## 实验设计（最小可测）

一个问题：**LP 奖励能不能让搜索重新有梯度？**

```
条件 A：fitness = 绝对分数（现状）
条件 B：fitness = 本轮分数 − 上轮分数（LP）
其余全部相同：同一批任务、同一个变异器、同样的调用预算、同样的随机种子
指标：曲线斜率、最终分数、停滞轮数
```

如果 B 的曲线在 A 停滞的地方还在动，说明 LP 有效。如果 B 只是把噪声放大，说明无效——
那也是结论。

### 已跑的一次（离线模拟模型，budget 300，15 题）

| 奖励 | baseline | evolution | random | evolution − random |
|---|---|---|---|---|
| absolute | 0.5625 | 0.875 | 0.875 | 0，区间跨零 |
| progress | 0.5 | 0.9375 | **1.0** | 跨零 |

progress 模式下随机搜索反而更好。解释：progress 奖励让父代选择偏向「刚进步过的」策略，
探索变多、利用变少——在 45 个策略的小空间里，纯随机本来就能覆盖得差不多。

**这不是 LP 无效的证据**，是「任务太简单、策略空间太小」的又一次重复。要测 LP，
需要一个策略空间足够大、且存在明显局部最优的任务。

### 实现位置

`agh/code_evolution.py` 的 `_pick_parent`：`reward="absolute"` 按分数选父代，
`reward="progress"` 按 `(progress, fitness)` 选。`scripts/run_code_bench.py --reward progress` 可切换。

## 与现有架构的关系

这五个机制都不动治理层。它们作用在「子级怎么选目标、怎么得奖励、怎么编码策略」上，
而网关、账本、哈希链、仲裁保持不变。换句话说：**改的是动机结构，不是可信结构**。

这也符合 AGH 的定位——治理层负责「结论可验证」，动机层负责「搜索有方向」。两者独立演进。

## 参考文献

- Ryan, R. M., & Deci, E. L. (2020). Intrinsic and extrinsic motivation from a self-determination theory perspective. *Contemporary Educational Psychology*. [PDF](https://selfdeterminationtheory.org/wp-content/uploads/2020/04/2020_RyanDeci_CEP_PrePrint.pdf)
- Oudeyer, P.-Y., Gottlieb, J., & Lopes, M. (2016). Intrinsic motivation, curiosity, and learning. *Progress in Brain Research*. [PDF](http://www.pyoudeyer.com/oudeyerGottliebLopesPBR16.pdf)
- Locke, E. A., & Latham, G. P. (2002). Building a practically useful theory of goal setting and task motivation. *American Psychologist*. [PDF](https://med.stanford.edu/content/dam/sm/s-spire/documents/PD.locke-and-latham-retrospective_Paper.pdf)
- Zimmerman, B. J. (2000). Attaining self-regulation: A social cognitive perspective. 综述见 [Panadero 2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5408091/)
- Gollwitzer, P. M. (1999). Implementation intentions: Strong effects of simple plans. *American Psychologist*, 54(7), 493–503.
- 内在动机的神经科学综述：[PMC5364176](https://pmc.ncbi.nlm.nih.gov/articles/PMC5364176/)
