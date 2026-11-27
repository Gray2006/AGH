# AGH 状态交接（v3.8.0，2026-11-27）

> 新会话先读这个文件，再读 `README.md` 的「版本与兼容」与 `memory/agh.md`。

## 一句话

机制完整、证据分层、缺口明确。进化适应度已接验证器；当前基准族上搜索空间接近上界，daemon 回写版本暂缓。

## 当前版本

- v3.8.0，`484 passed + 1 skipped`（NATS 在 CI 跑），ruff 干净，mypy 60 文件零错误
- 仓库 <https://github.com/Gray2006/AGH>，CI 双版本绿
- 依赖：pydantic v2、numpy、jsonschema、cryptography；Python 3.12+
- 自动异常检查（v3.5.0）：`agh/anomaly.py` 四条统计规则，报告出「自动发现」
- 导入保留时间戳（v3.6.0）：`ts` 字段 + 报告「时间」列，timeline 恢复可用
- **AGI 线开工（v3.7.0）**：`agh/repotask.py` 仓库级任务判定；方案见 `docs/agi-track.md`
- **AGI 阶段 1（v3.8.0）**：click 上 10 道题，基线 9/10（90%，上界）；三条泄漏已记录，容器隔离是下一步前提

## 能跑什么

```bash
pip install -e ".[dev]"
python -m pytest                    # 247 passed, 1 skipped
python -m agh run                   # M0 垂直切片
python -m agh experiment --seeds 50
python -m agh ablation --seeds 30
python -m agh evolve --mode meta --rounds 8
python -m agh daemon --rounds 4     # 自主迭代（默认 0 token）
python -m agh daemon --seed-drop 0.4 --llm-mutator --daily-budget 30000  # 降质任务族 + LLM 变异
python -m agh daemon --seed-drop 0.4 --hide-gold --llm-mutator     # 信息不足：缺的边得推断
python -m agh daemon --replay-mutations runs/daemon/events.jsonl   # L1 重放 LLM 进化轨迹
python -m agh run --anchor-store runs/anchors.jsonl                # 写签名锚点
python -m agh anchor --events runs/m0/events.jsonl --store runs/anchors.jsonl --verify
python -m agh report --runs runs
python scripts/red_team.py          # 7 类攻击
```

真模型（需 `COMMAND_CODE_API_KEY`；端点只支持 `deepseek/deepseek-v4.1-flash`）：

```bash
python scripts/run_llm_experiment.py --provider command-code --samples 20 --parallel 4 --verifier structural
python scripts/run_llm_bench.py --provider command-code --benchmarks 50 --min-nodes 7 --max-nodes 8
python scripts/make_graded_packet.py
python scripts/score_labels.py --labels ... --candidates ...
```

## 证据（按可信度）

| 结论 | 数字 | 可信度 |
|---|---|---|
| 分片精英优于单基因组 | +0.0689（CI 0.0167–0.1162） | 高 |
| 真模型跨 10 骨架低于规则 | -0.0685（CI -0.1128–-0.0237） | 高 |
| 加难后差距扩大 | -0.0904（12）、-0.0648（50） | 高 |
| 验证器二值决策与人工一致 | kappa 1.0（构造 10 + 真实 9） | 中高 |
| 验证器概率校准 | ECE 0.009（19 题，四轮） | 中 |
| 盲裁判不可用 | kappa 0.0 | 已判死 |
| 无验证器时进化适应度无梯度 | 顶在 0.422（= coverage 权重），种子即上界 | 高（1.17.0） |
| 接验证器后单轮进化 | 种子 0.65792 → 0.66625，上界 0.68212 | 高（1.17.0） |
| 完美种子上 LLM 变异 vs 规则 | 单轮同分 0.66625，未见优势 | 中（各 1 轮） |
| 降质种子（--seed-drop 0.4）上 LLM 变异 | 5 轮 0.47869 → 0.56534 单调上升，30271 tokens | 中高（1 次） |
| 同设置规则变异对照 | 4 轮恒 0.42113 | 高 |
| 单基准对照（6 基准 6556 tokens） | LLM 0.5696 vs 规则 0.4211 vs 种子 0.4082 | 中 |
| 降质下分片 vs 单基因组（公平基线） | 0.42113 vs 0.61556，delta -0.19444 | 高（1 次） |
| 信息降质（--hide-gold）规则变异 | 4 轮恒 0.41109，无梯度 | 高 |
| 信息降质 LLM 变异（旧口径：只数必需项） | 4 轮 0.47501 → 0.57681，22222 tokens | 已作废（含全塞覆盖收益） |
| 信息降质 LLM 变异（新口径：召回×精确率） | 4 轮 0.47973 → 0.48069，22156 tokens | 高 |
| 多余覆盖惩罚 | 精确覆盖 1.0 vs 全塞 0.5，总分确实更低 | 高（单测） |
| 跨 seed 配对（3 seed × 6 基准 = 18 对） | LLM − 规则 +0.0950，95% CI [0.0496, 0.1402] | 高（17720 tokens） |
| LLM 进化 L1 重放 | 曲线 `[0.66079, 0.66168]` 逐位一致，0 token | 高 |
| hard 骨架族（信息降质） | 规则 4 轮恒 0.55289；LLM 0.58086 → 0.58222（20794 tokens） | 高 |
| 搜索旋钮（tournament 3→6 / elite_only） | 6 基准分数完全不变 | 高（负面结果） |
| NATS 联调（nats-server -js） | roundtrip 通过；CI 起 nats:2.10 service | 高 |
| 更强模型对照（hard 族） | flash 0.58222 / pro 0.58751、0.58367，差 ≤0.006 | 中高（各 1–2 次） |
| 治理有效性：伪造出处 | 有网关 80/80 拦截，无治理 0/80 | 高 |
| 治理有效性：超预算 | 有账本 10/10 拒绝，无账本 0/10 | 高 |
| 治理有效性：篡改日志 | 有链 20/20 检出，无链 0/20 | 高 |
| 发布锚定 | `scripts/release.py` 跑 M0 → 签名锚点 → git tag，CI 全绿 | 高 |
| 代码任务离线（模拟模型） | baseline 0.5625，进化/随机均 0.875，差 0 且区间跨零 | 高（负面结果） |
| 代码任务突变测试 | 15 题参考解 hidden 全 1.0，每个 bug 变体 hidden < 1.0 | 高 |
| 代码任务真模型（command-code flash） | 12 题与 15 题 baseline 均 1.0，进化/随机同分；基准触顶 | 高（负面结果） |
| 代码任务三通道对照 | flash 1.0 / deepseek-chat 1.0 / glm-4-flash 0.9375，三者进化=随机 | 高（负面结果） |
| 代码竞技场（治理 + 真信号） | 离线：visible 1.0 / hidden 0.5，overfit 候选降 T2，日志校验通过 | 高 |
| 多轮修正（rounds 维度） | flash 触顶 1.0；glm-4-flash 0.9375 三方法全平，统计功效不足 | 中（n=16） |
| 审计 SDK（AuditSession） | 7 条测试：篡改检出、脱敏、失败样本导出 | 高 |
| 反馈通道（agh feedback） | 4 条测试：默认脱敏、可带原文、模板、无标记提示 | 高 |
| 低门槛入口（agh quickstart） | 5 条测试：无 key 可跑、日志可校验、可重复 | 高 |
| 可视化报告（agh ui） | 7 条测试：自包含 HTML、转义、篡改拒绝、--from-run | 高 |
| 自检（2.10.1） | 修 call_id 冲突 / title 未渲染 / 产物未忽略 / .gitignore 编码 | 高 |
| 接入已有日志（agh import） | 5 条测试：可验证输出、字段映射、坏行跳过 | 高 |
| 自检（2.11.1） | 修 4 处静默成功：缺文件返回 ok、坏行 KeyError、重复导入追加、参数冲突 | 高 |
| 自检（2.11.2） | 修 splitlines 切坏日志、feedback note 未清理、围栏未适配 | 高 |
| 自检（3.3.2） | 导入 0 条时先删后写会毁掉原日志；改为先解析后原子替换，5 条测试 | 高 |
| 学习进步奖励（LP） | 离线：absolute 0.5625/0.875/0.875 vs progress 0.5/0.9375/1.0，随机更好 | 中（模拟模型） |
| 扩大策略空间（135→270） | absolute 下 evolution 0.9375 vs baseline 0.5，区间不跨零（首次显著） | 中（模拟模型） |
| mutate 的 rounds 基因 | 分支列表漏写 → 该基因从未被选中，已修 | 高 |
| 分级目标（ladder） | 离线：与单一分数完全相同（0.5/0.9375/0.75），闸门几乎总开着 | 中（模拟模型） |
| 270 空间真模型 | flash：baseline/evolution/random 全 1.0，触顶；离线显著结果不可外推 | 高（负面结果） |
| 加难题（通配符/表达式/罗马数字） | flash 三道全 1.0：纯函数型任务已到极限 | 高（负面结果） |
| 调试题（给 bug 代码修复） | flash 一次 hidden 1.0：三类任务全试过，题库路线终止 | 高（负面结果） |
| 多 bug 模块（debug_textstats） | flash 两次尝试均 1.0：五类难度尝试全部失败 | 高（负面结果） |
| 平台导出导入（Langfuse/LangSmith） | 4 条测试：往返、非 llm 跳过、强制格式 | 高 |
| 报告筛选（模型/已标记/搜索） | 前端过滤，单文件仍自包含 | 高 |
| 日志比较（audit-diff） | 5 条测试：新增/消失/全替换/CLI | 高 |
| 环境自检（agh doctor） | 4 条测试：检查项、不泄漏 key、CLI | 高 |
| 大日志截断（ui --max-calls） | 3 条测试：截断、标记优先、不超限 | 高 |
| 日志统计（audit-stats） | 5 条测试：按模型/小时聚合、时间范围、CLI | 高 |
| 项目自我审计 | docs/what-it-proves.md：证明/未证明/积木/负面清单 | 高 |
| 日志解析性能 | 5000 条统计 0.08s；iter_entries 流式 API | 高 |
| Python 3.11 兼容 | 三版本矩阵 380 passed | 高 |
| 英文接入教程 | docs/import-guide.en.md | 高 |
| 端到端示例 | examples/demo_import.py：Langfuse 导出→导入→统计→报告 | 高 |
| 事件时间线（audit-timeline） | CLI 按序看事件，--limit / --json | 高 |
| 测试覆盖率 | 90%（5815 行），CI 门槛 88% | 高 |
| Windows CI | 上线即抓到 GBK 输出崩溃，已在 main() 修 | 高 |
| 打包验证 | CI 构建 wheel → 干净 venv 安装 → 跑 5 个命令 | 高 |
| 日志导出（audit-export） | CSV / 去原文 JSONL，5 条测试 | 高 |
| 大日志性能 | 1 万条：ui 0.38s/8MB（自动截断到 4.3MB），stats 0.33s | 高 |
| 死代码清理 | vulture 80% 无输出；删 run_experiment 的死参数 | 高 |
| CLI 帮助分组 | --help 加常用路径 epilog，研究类命令单独说明 | 高 |
| 文档-实现一致性 | README 里的命令必须存在且 --help 能跑；包体积 0.46 MB | 高 |
| release workflow | 已验证：2026-11-26 用 Trusted Publishing 发布 3.3.3，OIDC 无 token，带 attestations | 完成 |
| 报告校验徽章 | HTML 顶部显示哈希链校验状态 | 高 |
| 文档站构建 + 部署 | CI 跑 mkdocs --strict，deploy-docs job 推 Pages：https://gray2006.github.io/AGH/ | 完成 |
| 真实调用示例 | trace_real_call.py：2 次真实调用 → 校验 → 统计（268 tokens）→ 报告 | 高 |
| 安全扫描（bandit） | High 0 / Medium 0；三处 urlopen 改走 scheme 校验 | 高 |
| 基准回归测试 | 模拟模型分数精确断言（0.2875 / 0.1875 / 0.4375），改动即红 | 高 |
| README 分层 | 中英各 446/465 行；研究记录移到 docs/research*.md | 高 |
| 开发者入口 | scripts/dev.py 统一 test/lint/check/build/docs/clean | 高 |
| 用户旅程冒烟 | 9 步全通，每步 0.26–0.52s，产物逐项检查；CI package job 里跑 | 高 |
| 安全文档 | docs/security.md：威胁模型（防/不防）、依赖清单、复查方法 | 高 |
| quickstart 出报告 | 第 8 步生成 report.html，收尾给打开路径 | 高 |
| 报告内 CSV 下载 | 纯前端，从内嵌数据生成，字段与 audit-export 一致 | 高 |
| 路径边界 | 中文/空格/Unicode 目录下 quickstart/verify/ui/export/import 全通 | 高 |
| 空导入不再静默 | imported=0 时返回 2 并提示 --map | 高 |
| 统计粒度 | audit-stats --by day/hour | 高 |
| 导入格式 | Langfuse / LangSmith / OpenAI / 自定义（--map） | 高 |
| 锚定篡改检出 | 改一条 payload → `LogTampered: 数据被改动于 seq=6`；未篡改 → `signature_verified: true` | 高 |
| 真实失败样本（8 条） | 种子均值 0.37887 → 规则/LLM 均 0.42151 后停滞；LLM 20107 tokens | 中高（各 1 次） |
| git tag 锚点 | 写 tag 后读回 head/size/label 一致 | 高（单测） |
| daemon 的「改进」主要来自换权重 | 同批种子换权重 0.65792 → 0.75488 | 高（1.17.0） |

校准已固化进 CI：`tests/fixtures/calibration.json` + `tests/test_calibration_regression.py`（ECE ≤ 0.05、kappa ≥ 0.9）。

## 已知限制

1. 单一模型（command-code 只支持 deepseek-v4.1-flash）
2. 校准样本 19 题，规模小
3. 进化适应度基于规则子级，不代表模型能力
4. NATS 只验证语义，未真联调
5. 代码级自改只有底座（selfmod + supervisor），未启用
6. daemon 默认 0 token；LLM 变异器要显式开并设预算
7. 完美种子上种子策略即适应度上界（0.66625 / 0.68212），没有持续改进空间；只有降质种子（--seed-drop）才有梯度
8. 降质任务族的改进来自策略恢复，参数权重在参照打分下不动；回写分支已加「参数未变则跳过」，但它仍不是可持久化路径
9. 覆盖口径已改为召回×精确率（v1.22.0）：全塞不再免费。旧口径下的 0.57681 不可与新数字混用
10. 哈希链无外部锚定：能防「改一行」，不能防「整链替换」；`verify_against` 只是接口，尚未接外部时间戳
11. 验证器与签名密钥都是本地的，不构成独立第三方验证或身份系统

## 下一步（按优先级）

1. **AGI 阶段 1 已完成，阶段 2 卡在隔离**：click 上 10 道题基线 9/10（90%，上界）。
   下一步不是加题，是**容器隔离**——候选不能读宿主文件系统、不能有预装的目标包、要断网。
   没有隔离，任何通过率都不可信。详见 `docs/agi-track.md`
2. **真实用户**：目前零真实接入。`agh import` 是最低门槛的验证方式——
   没人拿它导自己的日志，说明「审计」这个需求本身要重新审视
3. NATS 集成：CI 已起 `nats:2.10` service 并跑真实联调；本地需要 docker
4. **升级 Actions 版本**：`checkout@v4` / `setup-python@v5` / `upload-artifact@v4`
   已被强制跑在 Node 24（GitHub 报 Node 20 弃用）。不紧急，但迟早要迁到 v5/v6

> 2026-11-26 已解决：PyPI 发布（3.3.3 上线，Trusted Publishing + OIDC）、
> 文档站部署（GitHub Pages，deploy-docs job）。

## 真实使用发现（2026-11-27）

拿本机 DSH 会话日志（7 个会话、3693 次真实模型调用、96.1 小时跨度）跑了一遍完整链路。
详细报告在 `runs/real-usage/REPORT.md`（本地，未入库）。

**发现一个致命 bug 并已修**：`agh ui` 的 HTML 报告从 v3.1.0 起一直是**白页**——
模板是普通 Python 字符串，JS 里的 `\n` 被 Python 转成真实换行，造成
`Uncaught SyntaxError`，整段脚本不执行。之前的测试只做字符串断言，从没真渲染过。
v3.3.8 已修（模板改 raw string）+ 加了能抓住它的回归测试。

**两个未修的真问题**

1. **导入丢时间戳**：`importers.DEFAULT_MAP` 没有 `ts`，`AuditSession.call` 也不接受外部
   时间戳。96 小时的真实跨度导入后变成 2 秒，`audit-timeline` 和 `audit-stats --by hour`
   对导入数据完全失效。修法：DEFAULT_MAP 加 `ts`，call 加可选 `ts`。改动小、收益最大
2. **token 口径太笼统**：真实数据里缓存读占 97%（997M / 1026M），
   单一 `tokens` 字段会让成本判断失真。建议拆「新算 / 缓存」两列

**一个产品定位问题**

`flags: 0`——审计层只做「记录 + 校验」，不做异常检测。报告能证明「没被改」，
但回答不了「哪次贵、哪次慢、有没有重复 prompt」。用户看完会问「所以呢」。
审计 ≠ 可观测性。要么补异常检测，要么明确边界。

## 现状评估（2026-11-27，暂停点）

用户提问「已实现 / 未实现 / 还能怎么改 / 意义是什么」，下面是当时的结论，供下次接续。

**判断：功能已经过剩，再修外围 bug 的边际收益在下降。**
2026-11-26 到 27 之间连发 27 个版本（v2.13 → v3.3.7）、修 20 个真 bug，
但全部落在编码、错误提示、导入边界这类外围；核心机制（签名、哈希链、仲裁、治理机）
一个没动过。这说明核心是稳的，也说明该动的不是这里。

**下一步优先级（已重新排序）**

1. **接 RFC 3161 外部时间戳** —— 唯一能堵住「整链替换」的口子，
   接口已留好（`HttpTimestampAuthority`，transport 可注入）。工作量小、价值明确。
   这是产品叙事当前最大的短板：号称可审计，却防不住最基础的那条攻击。
2. **拿一个真实用户** —— 不需要写代码。拿真实会话日志（DSH / QQ 机器人调用记录）
   用 `agh import` 导一遍，出一份 `agh ui` 报告，看是不是真的有人愿意看。
   现在连「导入真实日志长什么样」的样例都没有。
3. **重建任务抽象** —— 要验证策略搜索，必须换成多文件改动 / 真实项目 bug /
   需要运行调试的任务。成本高，不保证成功。
4. **性能摸底** —— 目前只测到 1 万条（ui 0.38s / stats 0.33s）；十万条未测。
5. 杂活：Actions 升 v5/v6（Node 20 弃用）、文档站加「5 分钟接入」页。

**意义的诚实结论**

- 工程上有值：8 个模块可单独拿走（见 `what-it-proves.md`「可复用的积木」）
- 研究上的价值主要是负面结果：7 条证伪，能省别人几周
- 产品上未验证：零真实用户不是「还没推广」，是一个需要正面的信号
- 一句话：机制做全了，假设诚实记录了哪些是错的，但还没证明有人需要它

## 踩坑清单

- 进化适应度先验证梯度再验证尺度；权重变异必须归一化，否则「进步」是缩放
- 被搜索的权重不能同时当打分函数，否则最优解是把惩罚项压到下界（1.17.0 用 `reference_cfg` 修）
- 自报指标必须验证器门控，否则刷分
- 日志截断本地链发现不了，需外部链头 + 长度
- 推理模型 reasoning token 也算 completion，`max_tokens` 不足会截断 JSON
- PowerShell 写文件易带 BOM，TOML 会炸；用 Python 写
- `git tag -d` 被安全网拦；改 tag 用 `--force-with-lease=<远程 tag 对象 sha>`
- 跑 daemon 冒烟会回写仓库冻结层，务必带 `--no-write-back`
- 测试里用 `frozen_src` 跑回写会改仓库冻结层并重建锚点；回写测试必须用 `frozen_copy`
- 任何「对照组」都要核对信息预算：基线拿全集、实验组拿子集，比较的就是信息不是方法
