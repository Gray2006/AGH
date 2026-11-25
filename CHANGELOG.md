# Changelog

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [2.28.2] - 2026-11-25

`scripts/dev.py`：跨平台的开发者命令入口。

### Added

- `python scripts/dev.py {test,lint,check,build,docs,clean}`
  - `check` = ruff + mypy + vulture + 全量测试（带覆盖率门槛）
  - `build` = `python -m build` + `twine check`
  - `docs` = `mkdocs build --strict`
- CONTRIBUTING.md 改用它，并把 Python 版本说明从 3.12+ 更正为 3.11+

### Notes

- 没用 Makefile：这个项目主要在 Windows 上开发，`make` 不一定有。
  Python 脚本在所有平台行为一致
- 顺带修了 CONTRIBUTING 里过期的版本说明（CI 早就跑 3.11/3.12/3.13 + Windows + 打包冒烟了）

## [2.28.1] - 2026-11-25

英文 README 同步拆分。

### Changed

- `README.en.md` 从 649 行降到 465 行，同样的 9 个研究章节移到 `docs/research.en.md`
- `research.en.md` 进 mkdocs nav

### Notes

- 中英文结构保持一致：产品面在前，研究记录在后，各自有指针

## [2.28.0] - 2026-11-25

README 瘦身：研究类章节移到 docs/research.md。

### Changed

- README 从 626 行降到 446 行。移走 9 个章节：G1 实验、消融与度量、自我迭代、
  自主迭代、红队演练、自我改写的安全边界、M0 实测、代码任务、代码竞技场
- 原位置留一段指针，指向 `docs/research.md`
- `docs/research.md` 进 mkdocs nav

### Notes

- 产品面（30 秒上手 / 三行接入 / 接入已有日志 / 可视化 / 反馈）和研究面混在一起时，
  第一次打开的人看不出重点。拆开后 README 只回答「怎么用」
- 研究记录没有被删，只是换了位置——`docs/research.md` 里保留全部实测数字与负面结果

## [2.27.1] - 2026-11-25

离线基准的回归测试：分数变了就红。

### Added

- `tests/test_benchmark_regression.py`：模拟模型确定性，所以直接断言精确分数
  - baseline 0.2875 / evolution 0.1875 / random 0.4375（20 题、held-out 4、p_correct=0.4）
  - 另外断言「同种子两次跑结果相同」

### Notes

- 这条测试会拦住两类改动：不小心改了评分逻辑、以及加题后忘了更新期望值
- 改题库或评分口径时，期望值要同步更新并在 CHANGELOG 注明——这是有意的摩擦

## [2.27.0] - 2026-11-25

安全加固：网络调用禁止 file:// 等本地协议。

### Added

- `agh/netutil.py`：`ensure_http_url` 校验 scheme 只允许 http/https 且必须有主机名；
  `open_http` 是唯一的网络入口
- `providers`、`billing`、`timestamp` 三处 `urllib.request.urlopen` 全部改走 `open_http`
- 7 条测试：接受 http/https、拒绝 file/ftp/data/相对路径/空主机、校验发生在发请求之前

### Verified

`bandit -r agh`：High 0 / Medium 0（此前 3 个 Medium，都是 B310「urlopen 允许 file:」）。

### Notes

- `urllib.request.urlopen` 默认接受 `file:`、`ftp:` 等 scheme。URL 若来自配置或用户输入，
  可以诱导读本地文件。AGH 是安全相关的项目，这类洞不该留着
- 剩下的 33 个 Low 是 subprocess 调用和 `random.Random(seed)`（确定性用途），不是问题

## [2.26.1] - 2026-11-25

真实调用示例：`examples/trace_real_call.py`。

### Added

- 用 command-code 通道跑两次真实调用，全程记进审计日志，然后校验、统计、出报告
- 从 `client.last_usage` 取真实 token 数（实测 268），不再是 0
- 没有 API key 时直接跳过（返回 0），不算失败
- 调用失败也记录成 `llm.error` 事件，不静默跳过

### Verified

本地实跑：两次调用 → `哈希链校验通过` → 统计显示 `2 次 / 268 tokens` → 报告生成。

### Notes

- 这和 `demo_import.py` 的区别：那个演示「导入别人的日志」，这个演示「自己记一条真实调用」
- 两个示例都不进 CI（需要网络和 key），但 `ruff check examples` 覆盖语法与风格

## [2.26.0] - 2026-11-25

文档站进 CI：`mkdocs build --strict` 通过，产物作为 artifact。

### Added

- CI 加 `docs` job：装 mkdocs-material，`NO_MKDOCS_2_WARNING=1 mkdocs build --strict`，
  把 `site/` 作为 `docs-site` artifact 上传
- `mkdocs.yml` 的 nav 补全：项目自审、状态交接、动机映射、接入指南、发布、模块 API
- `.gitignore` 加 `site/`

### Notes

- 一开始直接配了 `upload-pages-artifact` + `deploy-pages`，CI 报
  `No artifacts named "github-pages" were found`——Pages 站点没在仓库设置里启用。
  改成只构建 + 传 artifact，部署留给仓库设置好 Pages 之后再做
- `mkdocs build --strict` 有个 `mkdocs 2.0` 的升级警告会让退出码变 1，
  设 `NO_MKDOCS_2_WARNING=1` 后正常

## [2.25.6] - 2026-11-25

`agh ui` 的报告顶部加校验状态徽章。

### Added

- HTML 报告顶部显示「哈希链校验通过」；`build_report` 输出 `verified: true`
- 1 条测试

### Notes

- 之前校验状态只在 CLI 的 JSON 输出里，打开 HTML 的人看不到
- 「校验通过」在生产路径上等价于「没抛异常」——`build_report` 里 `log.verify()` 失败会直接拒绝生成，
  所以走到渲染这一步就一定是通过的

## [2.25.5] - 2026-11-25

README 说清楚 PyPI 版本落后，并验证 release workflow 的构建路径可用。

### Changed

- 安装段标注「PyPI 上是 2.1.0」，并给出从源码安装的命令

### Verified

- 手动触发 `release.yml`（`confirm=build`）：build job 成功，publish job 按设计跳过
- 真发布需要先在 PyPI 配 Trusted Publishing，步骤见 `docs/release.md`

### Notes

- 不把「PyPI 落后」藏起来：用户装到旧版会以为新功能不存在
- `gh workflow run release.yml -f confirm=""` 会被 GitHub 拒绝（空值不算提供），
  要用任意非 `publish` 的值

## [2.25.4] - 2026-11-25

文档与实现的一致性测试：README 里写的命令必须真实存在。

### Added

- `tests/test_readme_commands.py`：从 README 代码块提取所有 `agh <command>`，
  检查每个都在 CLI 里注册过；并逐个跑 `--help` 确认退出码为 0

### Notes

- 文档漂移是「看起来能用其实不能」的典型来源。这条测试让 README 里写错命令名时 CI 直接红
- 包体积顺手查了：64 个文件、0.46 MB，只有 `agh/` 和 dist-info，没有打包进 tests 或 docs

## [2.25.3] - 2026-11-25

`agh --help` 加了「常用路径」和「研究类命令」的区分。

### Changed

- help 的 epilog 列出五条常用命令，并说明 `run/verify/replay/experiment/...`
  是 M0 管线与进化实验，日常审计用不到
- `add_subparsers` 加 `metavar="<command>"`，usage 行不再堆一长串命令名

### Notes

- 20 个子命令平铺时，新人看不出从哪开始。分组信息放在 epilog 里，
  而不是重排 argparse 的注册顺序（那会打乱既有脚本的肌肉记忆）

## [2.25.2] - 2026-11-25

用 vulture 扫死代码，清掉一个真参数和两处命名。

### Changed

- `experiment.run_experiment` 删掉 `benchmark` 参数：全仓库没有一处传它，是纯死参数
- `AuditSession.__exit__` 的 `tb` 改名 `_tb`（协议要求，但确实不用）
- `JetStreamLike.pull_subscribe` 的 `durable` 改名 `_durable`（同上）

### Notes

- vulture 80% 置信度现在无输出；60% 置信度的其余条目都是公共 API（被外部或测试调用），不删
- 这类清理的价值不在代码量，在于「看到未使用的东西时不必再判断一次」

## [2.25.1] - 2026-11-25

大日志自动截断：1 万条能生成 8MB HTML，浏览器打不开。

### Changed

- `agh ui` 在日志超过 5000 条事件时自动截断（被标记的调用优先保留），
  并在 JSON 输出里加 `note` 说明；显式给 `--max-calls 0` 表示要全量

### Measured

- 1 万条、每条约 500 字节的日志：全量 8.03 MB / 0.38s；截断到 5000 后 4.32 MB
- `audit-stats` 同样 1 万条 0.33s

### Tests

- 4 条：小日志不截断、大日志截断并提示、显式 `--max-calls` 优先、常量下限

## [2.25.0] - 2026-11-25

`agh audit-export`：导出 CSV 或去原文的日志。

### Added

- `agh audit-export --log run.jsonl [--format csv|hashonly] [--out path]`
  - `csv`：每行一次调用，含 call_id / 模型 / tokens / 哈希 / 是否标记 / 标记原因，
    可直接用 Excel 或 pandas 分析
  - `hashonly`：保留完整事件结构但去掉 prompt/response 原文，适合把日志发给别人排查
- 5 条测试：CSV 表头与行、不泄漏原文、写文件、去原文导出、CLI

### Notes

- CSV 只导元数据，不导原文——这是有意的，导出文件经常会被转发
- 要带原文用 `agh audit export-failures --with-payload`（那是给 issue 用的，有脱敏提示）

## [2.24.0] - 2026-11-25

CI 验证「装出来能不能用」：构建 wheel → 干净 venv 安装 → 跑命令。

### Added

- `package` job：`python -m build` → 在全新 venv 里 `pip install dist/*.whl` →
  依次跑 `agh version`、`agh doctor --json`、`agh quickstart`、`agh audit verify`、
  `agh ui`，并检查产物非空

### Notes

- 之前 CI 只测源码（`pip install -e .`），打包漏文件、entry point 写错都发现不了
- `agh doctor` 在缺可选组件时返回非零是设计使然，CI 里用 `|| true` 后只校验 JSON 合法性
- 本地也验证过：干净 venv 里 `agh quickstart` 正常，`audit verify` 和 `audit-timeline` 都能跑

## [2.23.2] - 2026-11-25

Windows CI 上线，第一次跑就抓到一个真 bug。

### Fixed

- **Windows 控制台输出中文直接崩溃**：CI 的 Windows runner 用 GBK 代码页，
  `python -m agh` 打印中文时抛 `UnicodeEncodeError: 'charmap' codec`。
  `main()` 现在在 Windows 上把 stdout/stderr 切到 UTF-8；终端不支持时最多是乱码，不会崩

### Added

- CI 加 `test-windows` job（windows-latest + Python 3.13）

### Notes

- 这个 bug 在 Ubuntu CI 上永远不会暴露，而 AGH 的开发和主要使用环境都是 Windows
- Windows job 不跑 NATS 集成测试（runner 的 service container 不支持 Windows），
  那一条在 Windows 上保持 skipped

## [2.23.1] - 2026-11-25

覆盖率进 CI，13 条 CLI 冒烟测试。

### Added

- `tests/test_cli_commands.py`：13 个子命令至少跑通一次（version / audit 四个 /
  audit-stats / audit-timeline / audit-diff / ui / feedback / import / doctor / quickstart）
- dev 依赖加 `pytest-cov`，CI 设 `--cov-fail-under=88`

### Measured

- 覆盖率 89% → 90%（5815 行，569 行未覆盖）
- 之前 `cli.py` 只有 62%，大部分子命令没有入口测试

### Notes

- 门槛设 88% 而不是 90%：留一点余量，避免正常的重构（删代码）误伤 CI
- 覆盖率不是目标，只是防回退的护栏。剩下的未覆盖主要在 `supervisor.py`（67%）和
  `bus_nats.py`（77%），这两个都需要外部服务或复杂编排

## [2.23.0] - 2026-11-25

`agh audit-timeline`：按顺序看事件，`--limit` 看最近 N 条。

### Added

- `agh audit-timeline --log run.jsonl [--limit N] [--json]`：序号、事件类型、摘要
- `ledger` 显式导出 `BudgetVector`（此前是隐式转发，mypy strict 会报 attr-defined）

### Notes

- 和 `agh ui` 的时间线视图互补：这个是给脚本和终端用的，`ui` 是给浏览器看的
- 事件摘要规则：llm.call 显示模型和 tokens，llm.flag 显示原因和备注，
  session.start/end 显示 label 和状态，其它取前三个字段

## [2.22.0] - 2026-11-25

可运行的端到端示例：`examples/demo_import.py`。

### Added

- 模拟一份 Langfuse generation 导出 → `agh import` → `audit-stats` → `agh ui`，
  一条命令跑完，产物落在 `examples/out/`
- 示例数据里故意有一条「要求降序但返回升序」的调用，用来说明真实场景里为什么要标记
- `.gitignore` 加 `examples/out/`

### Notes

- 这是给「想先看效果再决定要不要接」的人准备的，和 `agh quickstart` 的区别是：
  quickstart 用内置 mock 演示审计链路，这个演示真实的导入流程

## [2.21.1] - 2026-11-25

英文版接入教程。

### Added

- `docs/import-guide.en.md`：三种接入方式（导入已有日志 / 调用时接入 / 网关签名），
  含 Langfuse、LangSmith 的样例 JSON 与边界说明
- README.en 加链接

### Notes

- 不是逐字翻译：英文版按英文读者的顺序重排了示例，FAQ 也精简过

## [2.21.0] - 2026-11-25

支持 Python 3.11。

### Changed

- `requires-python` 从 `>=3.12` 降到 `>=3.11`
- CI 矩阵加 3.11：三个版本（3.11 / 3.12 / 3.13）全部 380 passed

### Notes

- 代码本身没有用 3.12 专属语法（没有 `type` 语句、没有 PEP 695 泛型），
  限制只是当时随手写的。加上 3.11 后测试全过，说明兼容性本来就在
- 这条对用户的意义：Ubuntu 22.04 默认 Python 3.10、Debian 12 是 3.11，
  之前装不上，现在 3.11 可以

## [2.20.2] - 2026-11-25

日志解析抽成流式迭代器，顺手修掉一次双读。

### Changed

- `eventlog.iter_entries(path)`：模块级流式解析，逐条 yield，解析失败抛 `LogTampered`
- `EventLog.read()` 改为 `list(iter_entries(...))`，解析逻辑只剩一份
- `EventLog.stream()`：给大日志留的流式入口

### Fixed

- 第一次改 `audit-stats` 时用了 `stream()`，但 `EventLog` 构造时已经全量读入，
  等于每条日志读两遍。改回直接用 `entries`——5000 条统计 0.08s

### Notes

- 真正的大日志优化要改 `EventLog` 的构造语义（惰性读），影响面太大，暂不做
- 当前性能：5000 条 0.08s，10 万条约 1.6s，可接受

## [2.20.1] - 2026-11-25

`docs/what-it-proves.md`：项目的自我审计。

### Added

- 一份文档说清楚：证明了什么（治理有效性 100% vs 0%、可复现、执行验证器）、
  没证明什么（进化、搜索、动机理论、不是产品）、可复用的积木、负面结果清单
- README 顶部加链接

### Notes

- 写这份文档的原因是：项目的价值不在「能自我进化」，而在「把治理做成可测的东西，
  并诚实记录哪些假设是错的」。这句话需要一个地方放
- 没有新增代码，只整理已有证据

## [2.20.0] - 2026-11-25

`agh audit-stats`：按模型和小时看一份日志的分布。

### Added

- `agh audit-stats --log run.jsonl [--json]`：总调用/tokens/标记数、按模型聚合、
  按小时聚合、时间范围、token 消耗最多的模型
- 5 条测试：按模型聚合、时间范围、渲染、CLI、缺文件

### Notes

- 和 `audit-diff` 互补：diff 比较两份，stats 看一份的分布
- 按小时聚合用事件时间戳（UTC），跨时区分析要自己换算

## [2.19.1] - 2026-11-25

大日志不再撑爆报告：`agh ui --max-calls`。

### Added

- `--max-calls N`：超过 N 条时只渲染 N 条，页面顶部提示「共 X 条，显示前 N 条」
- 截断时**优先保留被标记的调用**，再按原顺序补足
- 3 条测试：截断生效、标记优先保留、不超限不截断

### Notes

- 几万条调用的 HTML 会有几十 MB，浏览器直接卡死。这是「单文件可分发」的代价，
  截断是折中：报告仍然完整可读，只是不全
- 需要全量分析时用 `agh audit summary` / `audit-diff`，它们不渲染 HTML

## [2.19.0] - 2026-11-25

`agh doctor`：装完先跑这个，看哪一项没准备好。

### Added

- `agh doctor [--json]`：检查 Python 版本、临时目录可写、冻结配置存在、模型 key、
  nats-py、git；全通过返回 0，有问题返回 1
- 不读凭证内容，只报「有没有」
- 4 条测试：检查项齐全、不泄漏 key 值、渲染、CLI

### Notes

- **没有模型 key 不算失败**：审计、校验、重放、报告都不需要它，只有跑模型才需要。
  这条做成 FAIL 会误导用户以为装坏了
- 这是「装完自检」而不是「健康监控」：只查静态条件，不跑网络

## [2.18.1] - 2026-11-25

发布流程进 CI。

### Added

- \.github/workflows/release.yml\：手动触发；只构建校验，输入 \publish\ 才上传
- 用 PyPI Trusted Publishing（OIDC），不需要长期 token
- \docs/release.md\：两种发布方式、一次性配置步骤、发版检查清单

### Notes

- 需要先在 PyPI 添加 pending publisher，并在 GitHub 建 \pypi\ 环境，否则 publish 任务会失败
- 本地路径仍然可用：\python scripts/publish.py --upload --token-file ...
## [2.18.0] - 2026-11-25

`agh audit-diff`：比较两份日志，看哪些调用是新的、哪些消失了。

### Added

- `agh audit-diff --a run1.jsonl --b run2.jsonl`：输出新增/消失的 call_id、共同条数、
  两边统计（调用数 / tokens / 各模型计数）
- 自动提示：b 比 a 多几次调用、tokens 变化、a 的记录是否全部消失
- 5 条测试：相同日志无差异、新增、全部替换、CLI、缺文件报错

### Notes

- 用途：比较「导入前 vs 导入后」、两次运行、或换模型前后的调用分布
- 只比较 `llm.call` 事件，其它事件类型不参与

## [2.17.0] - 2026-11-25

审计报告加筛选：按模型、只看已标记、全文搜索。

### Added

- `agh ui` 的 HTML 增加筛选栏：模型下拉（从数据自动收集）、「只看已标记」复选框、
  搜索框（匹配 call_id / 模型 / 哈希）、实时计数
- 全部前端完成，仍然是一个自包含文件，不联网、不依赖服务器
- 1 条测试：控件与渲染函数存在

### Notes

- 筛选在浏览器端做，日志全文已经内嵌——大日志（几万条）会让 HTML 变大，
  这是「单文件可分发」的代价
## [2.16.0] - 2026-11-25

`agh import` 支持 Langfuse / LangSmith 导出，带格式自动识别。

### Added

- `import_any(..., fmt="auto"|"generic"|"langfuse"|"langsmith")`：按第一行判断来源格式
- Langfuse：读 `type` / `input` / `output` / `model` / `usage`（`usage.input + usage.output` 算 tokens）
- LangSmith：读 `run_type=llm` 的 `inputs.messages` / `outputs.messages`，
  模型名从 `extra.metadata.ls_model_name` 取；`chain`/`tool` 等非 llm run 跳过
- CLI `--format`，默认 auto
- 4 条测试：两种平台往返、非 llm run 跳过、强制格式

### Notes

- 自动识别只看第一行：混合格式的文件需要显式 `--format`
- 仍是事后记录，不改变「导入前无法证明」的边界

## [2.15.2] - 2026-11-25

多 bug 模块也不难：`debug_textstats` 两次尝试都全对，难度路线彻底关闭。

### Added

- `debug_textstats`：一个 20 行的文本统计模块，埋了三个 bug（标点未剥、连续空白未合并、
  并列词频顺序不稳）。prompt 给完整代码 + 问题描述，要求修好
- 两个已知 bug 变体，突变测试通过

### Measured

`command-code / deepseek-v4.1-flash`，两次独立尝试，hidden 均 **1.0**。

### Notes

- 至此五类难度尝试全部失败：纯函数、边界密集、单 bug 调试、多 bug 模块、更大策略空间
- **结论写死**：在「单文件 Python 函数」这个层面，当前模型已经没有难度。
  要制造难度必须换任务抽象：多文件依赖、真实项目 bug、需要运行调试的迭代过程
- 20 题，held-out 划分再次变化

## [2.15.1] - 2026-11-25

调试题也不难：`debug_lru` 一次全对，题库路线到此为止。

### Added

- `debug_lru`：给一段有 bug 的 LRU 实现 + 问题描述，要求修好。
  prompt 里带完整 buggy 代码，考察的是「定位 + 修复」而不是「从零实现」
- 两个已知 bug 变体（不更新顺序 / 全返回 -1），突变测试通过

### Measured

`command-code / deepseek-v4.1-flash` 单次调用：hidden **1.0**。

### Notes

- 至此三类任务都试过：纯函数实现、边界密集、给 bug 代码修复。flash 全部一次通过
- **题库路线到此为止**。继续加同类题是浪费；要制造难度必须换任务抽象
  （多文件改动、真实项目 bug、需要运行调试的任务），而那不是 `Case` 模型能表达的
- 19 题，held-out 划分再次变化，旧结果不可比

## [2.15.0] - 2026-11-25

三道更难的题，真模型仍然全对——题库方向错了。

### Added

- `wildcard_match`：`?` / `*` 通配符匹配（DP）
- `expr_eval`：四则运算解析器（括号、优先级、向零截断）
- `int_to_roman`：1–3999 罗马数字（含 IV/IX/XL/XC/CD/CM 边界）
- 每题带参考解与两个已知 bug 变体，突变测试通过（每个变体都被 hidden 杀死）

### Measured

`command-code / deepseek-v4.1-flash` 单次调用，hidden 得分：

| 题 | hidden |
|---|---|
| wildcard_match | 1.0 |
| expr_eval | 1.0 |
| int_to_roman | 1.0 |

### Notes

- **纯函数型任务已经到极限**：18 道题里 flash 全对。继续加同类题没有意义
- 要制造真难度，需要换任务类型：多文件/需要调试现有代码/需要外部知识/长上下文，
  而不是继续加「给规格写一个纯函数」
- 题库从 15 题变成 18 题，**held-out 划分变了，之前的结果不可直接比较**

## [2.14.1] - 2026-11-25

真模型验证：离线那个「显著」结果不能外推。

### Measured（command-code / deepseek-v4.1-flash，budget 150，270 种策略）

| 方法 | held-out | train fitness |
|---|---|---|
| baseline `n1|first|plain|r1|p0` | 1.0 | — |
| evolution | 1.0 | 0.99 |
| random | 1.0 | 0.90 |

`WARNING_CEILING` 触发：baseline 在 held-out 上全对，差值没有意义。

### Notes

- 离线模拟模型上 evolution 0.9375 vs baseline 0.5 的「显著」，来自模拟模型
  `p_correct=0.4` 人为留下的可学习空间，**不代表真模型**
- 真模型对 15 道题仍然全对，策略空间扩到 270 种也测不出差异
- 结论：要验证策略搜索，必须先有「真模型会做错」的题库。现在没有

## [2.14.0] - 2026-11-25

分级目标（goal ladder）：先过公开用例，再看 hidden。

### Added

- `evaluate_policy(..., ladder=True)`：公开用例通过率低于 0.8 时 hidden 权重为 0，
  分数由 visible 主导；过闸后才把 hidden 算进来（Locke & Latham：具体 + 有难度 + 有反馈）
- `SolveOutcome.chosen_visible`：选中候选在公开用例上的分数
- `scripts/run_code_bench.py --ladder`

### Measured（离线模拟模型，budget 600，15 题）

| 模式 | baseline | evolution | random | evolution − baseline |
|---|---|---|---|---|
| 单一分数 | 0.5 | 0.9375 | 0.75 | 区间不跨零 |
| 分级目标 | 0.5 | 0.9375 | 0.75 | 区间不跨零 |

**没有差异**。原因：模拟模型的公开用例通过率本来就高，闸门几乎总是开着，
分级等于没分。要测出分级的作用，需要一个「公开用例难过、hidden 更难」的任务族。

### Notes

- 分级目标的实现是「闸门 + 加权」，不是「多阶段训练」——后者需要任务族支持
- 这一版把 SDT/SRL/目标设定/实施意图里能直接落地的两项（LP、分级）都做了，
  两项都没测出收益。剩下两项（if-then 策略、自主选择）需要新任务族，暂不做

## [2.13.0] - 2026-11-25

扩大策略空间后，进化第一次显著优于 baseline；同轮否掉 LP 奖励。

### Fixed

- **`mutate` 的 rounds 基因从未被选中**：分支列表写作 `("n_samples", "select", "hint")`，
  但下面有 `rounds` 分支——那个基因等于冻结。加上后修复

### Added

- `SolverPolicy.plan`：两阶段生成（先要实现步骤，再带着步骤写代码），多一次调用但改的是单次质量
- 策略空间从 135 种扩到 270 种

### Measured（离线模拟模型，budget 600，15 题）

| 奖励 | baseline | evolution | random | evolution − baseline |
|---|---|---|---|---|
| absolute | 0.5 | **0.9375** | 0.75 | 区间不跨零（显著） |
| progress | 0.5 | 0.5625 | 0.75 | 跨零 |

**第一次出现「进化显著优于 baseline」**。之前所有实验都是「进化 = 随机 = baseline」。

同一轮也否掉了 LP：progress 模式下进化退化到 0.5625。解释是：学习进步假设针对
「连续学习中的技能获取」，这里是「固定预算下的策略搜索」——没有学习发生的余地，
只有「找到更好的点」，两者的最优搜索策略本来就不同。

### Notes

- 空间大小是关键变量：135 种时随机搜索覆盖得差不多，270 种时锦标赛选择才开始有方向性
- 这是模拟模型的结果，真模型验证另跑

## [2.12.0] - 2026-11-25

动机理论落地：设计文档 + 学习进步（LP）奖励。

### Added

- `docs/motivation.md`：SDT / SRL / 目标设定 / 实施意图 / 计算内在动机五个理论到 AGH 机制的映射，
  标注哪些可测、哪些不该做
- `code_evolution` 支持 `reward="progress"`：父代选择按「相对上一步的进步」而不是绝对分数
  （Oudeyer 的学习进步假设）
- `scripts/run_code_bench.py --reward {absolute,progress}`
- 测试：progress 模式选进步大的做父代，absolute 模式选分数高的

### Measured

离线模拟模型，budget 300，15 题：

| 奖励 | baseline | evolution | random |
|---|---|---|---|
| absolute | 0.5625 | 0.875 | 0.875 |
| progress | 0.5 | 0.9375 | 1.0 |

progress 模式下随机搜索更好——探索变多、利用变少。这不是 LP 无效的证据，是
「策略空间太小（45 种）」的重复；要真测 LP，需要存在明显局部最优、且策略空间足够大的任务。

### Notes

- 五个理论里只落地了一个（LP），因为它是唯一能在现有任务族上直接测的
- 目标分级、if-then 策略、自主选择三项写进了文档，但没实现——它们需要先有合适的任务族，
  否则会和前面七八个负面结果一样，测不出东西

## [2.11.2] - 2026-11-25

第三轮自检：渲染层的边界，最严重的一条会让整份日志读不回来。

### Fixed

- **`splitlines()` 把 U+2028 当换行**：日志内容里出现 U+2028 / U+2029 / VT / FF 时，
  一条 JSON 会被切成两半，整份日志报「格式损坏」。改为只按 `\n` 切（JSONL 的换行就是 `\n`）。
  导入器的源文件读取同样修正
- **feedback 的 note 未清理**：flag 的 note 是自由文本，可能被塞进原文。现在去控制字符并截断到
  120 字符；`--with-payload` 时原文也去控制字符（NUL 会破坏 markdown）
- **feedback 的代码围栏未适配**：内容里含 ``` 时，外层围栏自动加长到 ````，不再撑破结构

### Tests

- U+2028 / VT 写入后能读回
- note 清理与截断
- 围栏长度自适应

## [2.11.1] - 2026-11-25

第二轮自检：四个「静默成功」类问题。

### Fixed

- **不存在的日志返回 `ok: true`**（最严重）：`audit verify/summary/export-failures`、`ui`、`feedback`、`import`
  对不存在的文件静默返回成功。审计工具对空输入说「通过」，等于自己撒谎。现在统一报错退出
- **损坏日志抛 `KeyError: 'seq'`**：坏行/坏 JSON 现在抛 `LogTampered("日志格式损坏（第 N 条）")`，
  CLI 捕获后打印友好消息并返回 2，不再甩 traceback
- **重复导入会追加**：`agh import` 两次得到 4 条而不是 2 条。现在默认覆盖目标文件
- `ui --log` 与 `--from-run` 同时给时行为未定义，现在明确报错

### Tests

- 8 条 CLI 错误路径测试（缺文件、目录当文件、参数冲突、空日志仍合法）
- 坏行 → `LogTampered`、重复导入不追加

## [2.11.0] - 2026-11-25

接入已有日志：不改代码，把别处的调用记录搬进可验证格式。

### Added

- `agh import --from-jsonl my_log.jsonl [--out out.jsonl]`：逐行读源 JSONL，写成审计日志
- `--map model=... prompt=... response=... tokens=...` 支持字段名映射
- 缺字段 / 坏 JSON / 非对象的行跳过并计数，不中断
- 5 条测试：可验证输出、字段映射、未知键报错、坏行跳过、CLI

### Notes

- 导入是事后记录：证明「从导入起没被改」，不证明「导入时那条记录本身真实」。
  要在源头链上，得在调用发生时用 `AuditSession.call()`
- README 补了 `agh ui --from-run` 只认默认目录的限制说明

## [2.10.1] - 2026-11-25

`agh ui --from-run`，以及自检发现的四个问题。

### Added

- `agh ui --from-run`：直接读 `./agh-quickstart/run.jsonl`，不用填路径；
  不给 `--log` 且存在该文件时也会自动用它

### Fixed

- **call_id 冲突**：内容完全相同的两次调用会算出同一个 id，flag 会串到另一条。
  加序号保证唯一（`call-<hash12>-<seq>`）
- `agh ui` 的 `title` 参数此前没有渲染到页面
- `agh quickstart` 产物目录未进 `.gitignore`，会污染工作区
- `.gitignore` 本身不是 UTF-8（被 PowerShell 用系统编码写过），改为按字节追加

### Tests

- 相同内容两次调用必须拿到不同 id
- `--from-run` 默认路径、无日志且无 quickstart 时报错退出

## [2.10.0] - 2026-11-25

可视化报告：一个自包含 HTML，双击就能看。

### Added

- `agh ui --log run.jsonl [--out report.html] [--no-open]`：读审计日志，生成数据内嵌的 HTML
- 页面含调用统计、逐次调用的模型/哈希/tokens、被标记的问题、事件时间线
- 日志内容用 `textContent` 渲染、`</` 转义，不拼接 innerHTML
- 校验不过的日志直接拒绝生成
- 5 条测试：结构、数据内嵌、闭合标签转义、篡改拒绝、CLI 落盘

### Notes

- 不做服务器、不做 WebView：一个文件即可，任何人拿到都能看
- 想放进 DSH 侧边栏，用「在侧边栏打开」指向这个 HTML，不需要写插件

## [2.9.0] - 2026-11-25

低门槛入口：`agh quickstart`，一条命令看完审计链路。

### Added

- `agh quickstart`：内置三次模拟调用（一次故意标错），走完
  记录 → 标记 → 校验 → 重放 → 导出失败样本，并打印下一步怎么接自己的代码
- 不需要 API key、不需要写代码、不消耗 token
- 5 条测试：无 key 可跑、日志可校验、只导出一条失败、可重复执行、输出含下一步

### Notes

- 这是给「想先看看是什么」的人的入口；真正接入还是 `AuditSession` 三行

## [2.8.1] - 2026-11-25

反馈通道：把「提 issue」的成本降到复制粘贴。

### Added

- `agh feedback --log run.jsonl`：输出可直接粘贴的 issue markdown（版本、环境、统计、
  被标记调用表、复现模板）
- 默认脱敏：只带 `prompt_sha256` 前缀，不带输入输出原文；`--with-payload` 显式开启
- 日志校验不过时直接拒绝生成
- 4 条测试：默认脱敏、可带原文、模板存在、无标记时的提示

### Notes

- 开源项目默认收不到反馈。这条命令不能改变反馈率，只能降低单次反馈的成本
- 样本仍然偏斜：只有出问题的人会说话

## [2.8.0] - 2026-11-25

审计会话：产品面的三行接入层，以及「产品反哺实验室」的导出通道。

### Added

- `agh/audit.py`：`AuditSession` —— `call()` 记一次模型调用，`flag()` 标记错误结果，
  `verify()` / `replay()` / `export()` 事后校验与重放
- `store_payload=False`：只存哈希不存原文，适合敏感数据
- `export()` 支持 `redact=True`，导出可直接外发的审计包
- `export_failures()`：把被标记的调用导成失败样本，供实验室消费
- CLI：`agh audit {summary,verify,export-failures} --log ...`
- 7 条测试：篡改检出、脱敏导出、只导出被标记的调用、不存原文时仍能导出

### Notes

- 这层是给「用多个 LLM 搭流水线、出问题要追责」的场景准备的，不需要理解契约/骨架/竞技场
- 产品叙事从这里开始，进化那半仍然存在但不再是入口

## [2.7.0] - 2026-11-25

多轮修正：策略空间里第一个能改变单次生成质量的维度。

### Added

- `SolverPolicy.rounds`（1–3）：生成 → 跑公开用例 → 把失败信息拼回提示 → 重写。
  前三个旋钮（采样数 / 选择 / 提示）都只是生成前或生成后的选择，这是第一个生成中的反馈
- `format_feedback()`：把 visible 失败整理成「输入/期望/实际」。只给 visible，hidden 永不进提示
- `ExecResult.outputs`：子进程回传的原始输出，供反馈使用
- 多轮下 `select="first"` 按 visible 选（否则等于丢掉修正结果）；单轮保持原义
- 5 条测试：多轮带反馈修对、反馈不泄漏 hidden、单轮无反馈、rounds 越界、提示拼接

### Measured

| 模型 | baseline | evolution | random（抽到 r2） | 触顶 |
|---|---|---|---|---|
| command-code / flash | 1.0 | 1.0 | 1.0 | 是 |
| zhipu / glm-4-flash | 0.9375 | 0.9375 | 0.9375 | 否 |

### Notes

- 单元测试证明多轮机制有效：第一轮写错的代码，第二轮带失败信息能改对
- 但基准测不出来：glm-4-flash 的 held-out 只有 16 个样本、baseline 已 15/16，
  差异 1 题 = 0.0625，且 110 次预算只够评估 1–2 个策略。**统计功效不足**，不是机制无效
- 要让这个实验有结论，需要 50+ 道 held-out 题，或 baseline 低到 0.5 左右的题库

## [2.6.1] - 2026-11-24

把 overfit 警告变成治理动作：hidden 决定发布等级，不参与选择。

### Changed

- `CodeArenaReport.release_tier`：visible 冠军的 `visible - hidden > 0.25` 时降级为 `T2`
  （停在 VERIFIED 等人工），否则 `T1` 自动发布
- 仲裁排序只用 visible，平局按 child_id。此前用 hidden 做 tie-break，等于让 hidden
  悄悄参与了选择——测试抓到了这个问题

### Added

- 3 条测试：overfit 候选降 T2、干净候选 T1、hidden 不改变赢家

### Notes

- 这条修的是设计原则：hidden 一旦参与选择就不再是独立度量，会被选择函数优化掉。
  现在它只回答「这个赢家能不能自动发布」，不回答「谁是赢家」

## [2.6.0] - 2026-11-24

代码竞技场：把治理层接到真实测试信号上。

### Added

- `agh/code_arena.py`：`run_code_arena(task, solvers, ...)` —— 候选过网关签名、写入门、
  预算账本、哈希链日志，分数来自子进程真跑测试
- 仲裁只看 visible 分（模拟只公开用例的真实场景），hidden 分只用于报告；
  `visible - hidden > 0.25` 时记 overfit 警告
- `scripts/run_code_arena.py`：`--simulate` 离线跑，或接真模型
- 4 条测试：按 visible 选赢家、求解器异常不中断、overfit 警告触发、日志可校验

### Measured

- 离线（模拟模型，2 个子级）：visible 均 1.0，hidden 均 0.5，差距 0.50，警告触发，
  日志校验通过

### Notes

- 这补上了 AGH 缺的那一环：治理层不再是「给自定规则打分」，而是「给可执行的真信号打分」
- 已知局限仍是题库难度（三个模型 0.94–1.0）与策略空间（只有采样/选择/提示三个旋钮）

## [2.5.0] - 2026-11-24

三个模型通道上的代码基准对照，结论是策略空间本身没有区分度。

### Added

- `providers.PRESETS` 增加 `zhipu`（`glm-4-flash`）
- `run_code_bench.py` 在 baseline 触顶时输出 `WARNING_CEILING`（2.4.1 起，本版实测触发）

### Measured（15 题，budget 80，held-out 4）

| 通道 / 模型 | baseline | evolution | random | 触顶 |
|---|---|---|---|---|
| command-code / deepseek-v4.1-flash | 1.0 | 1.0 | 1.0 | 是 |
| deepseek 官方 / deepseek-chat | 1.0 | 1.0 | 1.0 | 是 |
| zhipu / glm-4-flash | 0.9375 | 0.9375 | 0.9375 | 否 |

### Notes

- glm-4-flash 没触顶，但进化与随机仍然同分。原因不在模型：`SolverPolicy` 只能调
  「采样数 / 选择方式 / 提示」，baseline（n=1、取第一个）已经接近上限，这些旋钮无法提升单次生成质量
- 结论：这个策略空间对这套题没有区分度。要测出「进化 vs 随机」，需要
  1）baseline 明显低于上限的题库，2）能改变单次生成质量的策略维度（多轮修正、更细的提示模板）
- 三个通道都 0 调用失败，链路本身是通的

## [2.4.1] - 2026-11-24

代码任务基准在真模型上触顶，加天花板检测。

### Measured

真模型 `command-code / deepseek-v4.1-flash`，budget 80：

| 题库 | baseline held-out | evolution | random | call_errors |
|---|---|---|---|---|
| 12 题 | 1.0 | 1.0 | 1.0 | 0 |
| 15 题（+编辑距离/parse_int/最长回文子序列） | 1.0 | 1.0 | 1.0 | 0 |

### Changed

- `run_code_bench.py` 在 `baseline.held_out_score >= 1.0` 时输出 `WARNING_CEILING`：
  基准触顶，进化与随机的差值没有意义
- 新增 3 道更难的题（编辑距离、字符串转整数、最长回文子序列），每题带参考解与已知 bug 变体，
  突变测试通过

### Notes

- 结论：这 15 道经典小算法题对 flash 是送分题，**区分不出方法**。不是方法无效，是题库难度低于模型能力
- 要让基准有区分度，需要难度显著高于模型的题（多步推理、非标准算法），或换更弱的模型
- 执行型验证器链路本身已验证：参考解 hidden 全 1.0，bug 变体全部被杀

## [2.4.0] - 2026-11-24

执行型验证器：把评分信号从「AGH 自己定义的规则」换成「真跑测试」。

### Added

- `agh/execverify.py`：`ExecutionVerifier` 满足既有 `Verifier` 协议，在子进程里跑候选代码
  - 期望值只留父进程，子进程只拿入参、只回传输出 → 候选无法伪造通过
  - visible / hidden 两组用例，默认只用 hidden 打分；`overfit_gap()` 量化背可见答案的程度
  - 子进程 + 超时 + rlimit + 清空环境 + 临时目录；固定 `PYTHONHASHSEED`，评分确定性
- `agh/codetasks.py`：12 道题，每题带参考解与「已知 bug 变体」（对测试本身做突变测试）
- `agh/codesolve.py`：`SolverPolicy` 有界基因组（采样数/选择方式/提示）+ 多候选求解，
  选择只能看 visible 用例
- `agh/code_evolution.py`：以 hidden 通过率为适应度的策略进化，与随机搜索同调用预算，
  train / held-out 划分 + 配对 bootstrap 区间
- `agh/simulated.py`：离线模拟模型，只验证流水线
- `scripts/run_code_bench.py`：`--simulate` 离线跑，或接真模型（自动关 JSON 模式）
- 15 条测试（execverify 10 条 + codetasks 断言突变体都被杀死）

### Measured

- 离线（模拟模型，400 次调用预算）：baseline 0.5625，进化 0.875，随机 0.875，
  `evolution - random` 均值差 0，区间跨零 —— 流水线通了，方法未证明有效
- 12 道题的参考解在 hidden 上全部 1.0；每个已知 bug 变体在 hidden 上 < 1.0

### Notes

- 安全边界：子进程只防失控（rlimit / 超时 / 清环境 / 临时目录），**不防恶意**，
  不隔离网络与文件读权限。评估不可信模型输出时请放进容器或无网络沙箱
- 尚未接入 pipeline / arena：原有 evolution 进化的是结构标签基因组，与代码任务不是同一个对象
- 本题族的意义是补上「不由 AGH 定义对错」的信号，不是刷分
- 真模型数字未取得：OpenRouter 余额不足（402）。第一次跑出「held-out 全 0」，
  排查后确认是调用失败被当成空候选——已加 `call_errors` 计数与 `WARNING_CALL_ERRORS`，
  把「模型答错」和「调用没通」分开，避免把 API 故障读成模型能力

## [2.3.0] - 2026-11-24

外部锚定接进发布流程。

### Added

- `agh/release.py`：版本一致性校验、工作区干净检查、跑 M0 并锚定、按版本校验锚点
- `scripts/release.py`：一条命令完成「校验 → 可选上传 PyPI → 跑 M0 → 签名锚定 → 推 tag」
- 锚点同时写本地 JSONL 与 git tag `agh-anchor/<digest>`，tag 可推到远程作为外部位置
- 6 条测试：版本不一致、篡改日志被拒、缺锚点报错、干净工作区检查

### Notes

- 锚定前强制要求 M0 的 L1 重放逐位一致，不一致直接拒绝发布
- 这仍不是第三方时间戳：防「悄悄改日志」，不防「有 push 权限的人同时改日志和 tag」

## [2.2.0] - 2026-11-24

治理有效性对照实验：三组「有治理 vs 无治理」，第一次量化 AGH 的立身之本。

### Added

- `agh/governance_bench.py`：provenance / ledger / hashchain 三组对照，输出结构化报告
- `scripts/run_governance_bench.py`：人读表 + JSON
- `tests/test_governance_bench.py`：5 条测试，断言「有治理全拦、无治理全放、合法输入零误拒」

### Measured

| 场景 | 有治理 | 无治理 |
|---|---|---|
| 伪造出处（改载荷/改签名/未知签发者/重放） | 80/80 = 100% | 0/80 |
| 超预算调用 | 10/10 = 100% | 0/10 |
| 篡改日志一行 | 20/20 = 100% | 0/20 |

合法输入误拒 0。三组都是 100% vs 0%。

### Notes

- 实验设计上踩过一个坑：重放检测需要先让合法信封通过一次以登记 nonce/seq，
  否则「重放」那一项拦不住，拦截率只有 75%——修的是实验，不是治理代码
- 蜂巢/子级间通信写进「暂不做」：预实验显示同一份降质池分片后合并 ≤ 单体（0.5534 vs 0.5563），
  信息论上并集不产生新信息

## [2.1.2] - 2026-11-24

更强模型的对照：结论是没有实质差别。

### Measured

hard 族（`--seed-drop 0.4 --hide-gold`，2 代 × 1 群体）上三种变异器：

| 变异器 | 曲线 | tokens |
|---|---|---|
| 规则 | 恒 0.55289 | 0 |
| `deepseek-v4.1-flash`（command-code） | 0.58086 → 0.58222 | 20794 |
| `deepseek-v4-pro-0813`（OpenRouter） | 0.55289 → 0.58751 | 22081 |
| 同上，更大预算重跑 | 0.57248 → 0.58141 → 0.58367 | 49757 |

- pro 两次 0.58751 / 0.58367，flash 0.58222，差距 ≤0.006，在单次运行噪声内
- 两次 pro 的起点就不同（0.55289 vs 0.57248），说明首轮变异本身有随机性
- 结论：换更强模型不改变天花板。当前瓶颈是候选生成的信息量，不是模型智力

### Notes

- command-code 通道实测只放行 `deepseek/deepseek-v4.1-flash`，其余模型名返回
  `400 unsupported_model`；`/models` 端点 403
- OpenRouter 通道可用；`anthropic/claude-sonnet-5.5` 返回 403（账号未获授权）

## [2.1.1] - 2026-11-24

NATS 适配器与真实客户端对齐，集成测试进 CI。

### Fixed

- `NatsBus.publish/fetch` 假设同步客户端，但 nats-py 的 `JetStream.publish/fetch`
  是 async：同步调用拿到 coroutine，`seq` 恒为 0。新增 `publish_async` / `fetch_async`，
  同步接口遇到 awaitable 时抛明确错误而不是静默返回 0
- 集成测试改用 `publish_async`

### Added

- `[project.optional-dependencies] nats = ["nats-py>=2.6"]`
- CI 起 `nats:2.10` service 并设 `NATS_URL`，集成测试不再 skipped

### Verified

- 本地 `nats-server -js` + `NATS_URL=nats://127.0.0.1:4222`：roundtrip 通过

## [2.1.0] - 2026-11-24

骨架难度、搜索旋钮、打包发布。

### Added

- `--family {default,hard,wide,deep}`：更难的骨架族（更多节点、更密边、更严垂直约束）
- `EvolutionConfig(tournament=, elite_only=)`：父代选择的锦标赛宽度与「只从已接受变体里选」
- `scripts/publish.py`：构建 + `twine check`，`--upload` 才真正上传
- 发行名改为 `agh-gestalt`（PyPI 的 `agh` 已被 Agent Guidance Hub 占用）；import 名与 CLI 仍是 `agh`

### Measured

- hard 族（--seed-drop 0.4 --hide-gold）：规则 4 轮恒 0.55289；LLM 4 轮 0.58086 → 0.58222
  （20794 tokens），首轮后就平
- 搜索旋钮对照（hard 族 6 基准）：tournament 3 → 6、elite_only 开启，分数完全不变
- 结论：规则变异器在信息不足时没有梯度，调父代选择不是瓶颈；LLM 的增益也只有首轮

### Notes

- `agh` / `agh-gestalt` 的 PyPI 上传需要 `TWINE_PASSWORD`，CI 不持有该 token，
  因此只做到「可构建、可校验」
- 本地无 docker，NATS 集成测试保持 skipped

### Fixed

- `scripts/publish.py`：Windows 下 `dist/*` 不被 subprocess 展开，改为显式文件列表；
  控制台 GBK 会让 twine 的进度条崩掉，上传时强制 `PYTHONIOENCODING=utf-8`
- 2.1.0 已发布到 PyPI：<https://pypi.org/project/agh-gestalt/2.1.0/>

## [2.0.1] - 2026-11-24

两处工程卫生，都是长跑才会暴露的问题。

### Fixed

- `_SHARD_CACHE` 加上限（256，FIFO 淘汰）：daemon 长跑时缓存键随参数与种子变化，
  此前无界增长
- `--failures` 与 `--seed-drop` 同时给时语义明确：失败样本自带种子，`--seed-drop`
  被忽略并在 notes 里说明，不再静默失效

### Tests

- 缓存上限单测；失败样本忽略 seed-drop 单测

## [2.0.0] - 2026-11-24

2.0 不是新增功能的分界线，而是承认：1.x 承诺「公开 API 冻结」，字段层面做到了，
分数语义没有。这一版把语义变更集中声明，并把版本规则改成能容纳研究演进的样子。

### Semantics（字段不变，数字口径变了）

- **覆盖率 = 召回 × 精确率**（1.22）：全塞 `covered` 不再免费。凡引用旧口径
  `0.57681` 的数字必须标注口径，不能与新数字并列比较
- **`--hide-gold` 信息降质**（1.19）：变异器只看降质后保留的边；`--seed-drop`
  同时影响起点与可见池。旧「只降起点」的曲线与现在不可比
- **LLM 变异进日志**（1.20）：`llm.mutation` 记录会让事件日志变大，换来 LLM 路径
  可 L1 重放
- `AutonomousReport` 新增 `strategy_curve`：策略进化与参数搜索分开报告，
  此前两者的贡献混在一个 `curve` 里

### Added

- 真实失败样本任务族：`agh/failures.py`、`scripts/collect_failures.py`、
  `agh daemon --failures PATH`；样本以 JSON fixture 提交，CI 不调模型
- `GitTagStore`：用 git tag 存锚点，远程仓库即外部位置；`agh anchor --store-git REPO`
- `tests/fixtures/real_failures.json`：8 条真实模型失败重构

### Measured

- 真实失败样本（8 条，种子均值 0.37887）：规则与 LLM 都爬到 0.42151 后停滞；
  LLM 花 20107 tokens 没有换来更好的结果
- `GitTagStore`：写 tag 后读回 head/size/label 一致
- 覆盖口径：精确覆盖 1.0，全塞 0.5，总分确实更低（单测）

### 迁移

- 2.x 规则：字段/签名兼容走 minor；分数语义变更走 minor 但必须在 CHANGELOG 标
  `Semantics`；删字段或改签名走 major
- 旧报告与旧数字保留原样，不重算；新数字在 CHANGELOG 里带口径标签

## [1.22.0] - 2026-11-24

覆盖口径修复：多余覆盖不再免费。

### Changed

- `arena.score_candidate` 的覆盖率从「必需项召回」改为 `recall × precision`：
  多余覆盖拉低精确率，全塞 `covered` 不再能刷分
- 新增 `over-coverage penalty: precision ...` 说明，分数来源可追

### Measured（`--seed-drop 0.4 --hide-gold`，4 轮）

| 口径 | 规则变异 | LLM 变异 |
|---|---|---|
| 旧：只数必需项交集 | 0.41109 平 | 0.47501 → **0.57681** |
| 新：召回 × 精确率 | 0.41109 平 | 0.47973 → **0.48069** |

结论：旧口径下 LLM 的「持续改进」约 +0.096 来自全塞覆盖，不是推断能力。堵上后
LLM 相对规则仍有 +0.07，但曲线不再增长。

### 兼容

- M0 数字不变（`child-faithful` 0.802325、`child-dissent` 0.45975），因为两者的 covered
  本来就等于必需项子集
- 冻结层权重未改；锚点无需重建。凡引用旧口径 0.57681 的地方必须标注口径

## [1.21.0] - 2026-11-24

事件日志的外部锚定：让「整链替换」可被发现。

### Added

- `agh/anchoring.py`：`Anchor` / `AnchorStore` / `anchor_log` / `check_log` / `verify_anchor`
- `agh anchor --events ... --store ... [--verify]`：写链头与长度，或校验日志是否被替换
- `agh run --anchor-store PATH`：跑完 M0 自动写锚点
- 锚点用 Ed25519 签名；签名覆盖 head / size / log_path / label / created_at
- 校验时从磁盘重新读日志（内存里的 entries 不参与），否则篡改不可能被发现

### Measured

- 未篡改：`{"ok": true, "signature_verified": true}`
- 改一条 payload：`LogTampered: 数据被改动于 seq=6`
- 截断日志：长度不符；换密钥验签：签名失败；锚点被改：签名失败

### 边界

- 本地锚点文件仍可被删：真正的「外部」需要把 AnchorStore 换成第三方时间戳或另一台机器，
  接口已预留，未接真实服务
- 开发密钥确定性派生，签名只证明「改动需要密钥」，不证明「密钥属于谁」

## [1.20.0] - 2026-11-24

LLM 路径的 L1 重放，以及对外部评估的诚实校准。

### Added

- `LlmStrategyMutator(recorder=...)`：每次模型提议都落一条 `llm.mutation` 记录
  （提示、原始输出、解析后的策略、是否退回规则）
- `ReplayStrategyMutator`：按记录顺序吐出策略，不调用模型；记录耗尽直接抛错，
  不会悄悄退回规则
- `agh daemon --replay-mutations EVENTS.jsonl`：用记录逐位复现 LLM 进化轨迹
- `CombinedReport` 之外无需改动：重放走同一条 `mutator_factory` 通道

### Measured

- 端到端重放：原始 2 轮 LLM 进化曲线 `[0.66079, 0.66168]`；重放同一份记录，
  曲线与最优策略逐位一致，0 token

### Docs

- README 增加「在 AGI 治理光谱里的位置」：个体安全壳 / 团队章程（AGH 所在层）/
  社会模拟器（SWARM）三层分工，只认领自己那一层
- README「边界」重写：本地哈希链不防整链替换、开发密钥可伪造、验证器不是独立第三方、
  L1 只覆盖 M0 管线与 LLM 变异，LLM 子级重构仍是 L2
- 移除过时表述（「子级是规则函数，不接 LLM」「G1 未做」）

## [1.19.0] - 2026-11-24

真难度任务族、显著性证据、缓存与回写卫生。

### Added

- `agh daemon --hide-gold`：信息降质。变异器只看得到降质后保留的边，缺的边必须靠推断，
  堵住「特征池泄漏正确答案」这条路（此前 `--seed-drop` 只降起点、不降信息）
- `visible_pool_for(bench, degrade=, seed=)`：信息降质后的可见边池
- `sharded_evolve/combined_evolve(hide_gold=, mutator_factory=)`：按基准构造变异器，
  让 LLM 变异器也吃同一份受限池
- `evolve(feature_pool=, node_pool=)`：显式覆盖变异池
- `_params_changed`：参数与冻结层一致时跳过回写，只留说明，不再「写回同值 + 重建锚点」

### Changed

- `_SHARD_CACHE` 不再要求 `verifier is None`：验证器是确定性的，缓存键补上可见池与验证器类型
- 缓存键含 `bench_seed.features/covered`，跨轮精英延续不会串味

### Measured

- `--seed-drop 0.4 --hide-gold` 规则变异 4 轮：恒 0.41109（无梯度）
- 同设置 LLM 变异 4 轮（22222 tokens）：0.47501 → 0.54593 → 0.57593 → 0.57681
- 跨 seed 配对（3 个基准 seed × 6 基准 = 18 对，17720 tokens）：LLM - 规则均值 +0.0950，
  95% CI [0.0496, 0.1402]，不跨 0

### 结论

- 信息不足时 LLM 仍能改进：它补不了缺的边，但能把覆盖补满、把深度校准到位；规则变异完全爬不动
- 覆盖项不惩罚多余节点（over-cover 免费）仍是打分口径的漏洞，下一版要么加惩罚，要么把必需项藏起来

## [1.18.1] - 2026-11-24

修掉降质模式下单基因组基线的信息优势。

### Fixed

- `combined_evolve` 的单基因组基线在 `--seed-drop > 0` 时仍拿全集特征池，而分片只拿到降质子集，
  `per_benchmark_delta` 比的不是「分片 vs 单基因组」而是「信息少 vs 信息多」
- 新增 `single_seed_features(benchmarks, degrade=, seed=)`：降质时基线取各分片降质种子的并集，保持同等信息预算

### Measured

- 6 基准、`seed_degrade=0.4`、2 代 × 1 个体：分片 0.42113 vs 单基因组 0.61556（delta -0.19444）
- 无降质同设置：分片 0.66079 vs 单基因组 0.60059（与 1.16 的 +0.0689 一致）

## [1.18.0] - 2026-11-24

让自主迭代在「更难的任务族」上有真实梯度。

### Added

- `seed_for(bench, degrade=..., rng=...)`：可确定地抽掉种子策略的部分边与必需项
- `agh daemon --seed-drop FRAC`：种子降质比例（0–0.9），把适应度从「种子即上界」解放出来
- `sharded_evolve(carry=...)` / `combined_evolve(carry=...)`：跨轮精英延续，每轮从上一轮各基准最优策略继续
- `CombinedReport.carry`：把本轮各分片精英交回调用方

### Measured

- 完美种子（无降质）：曲线仍水平，种子即上界，和 1.17.0 结论一致
- `--seed-drop 0.4` + 规则变异：种子均值 0.40822，5 轮 0.51575 → 0.52391 后停
- 同设置 + LLM 变异（30271 tokens，5 轮）：0.47869 → 0.51453 → 0.55220 → 0.56176 → 0.56534，单调上升
- 同设置规则变异对照 4 轮：恒 0.42113
- 单基准对照（2 代 × 1 个体，6 基准共 6556 tokens）：LLM 均值 0.5696 vs 规则 0.4211 vs 种子 0.4082
- 参数权重在参照打分下不再漂移（3 轮恒为冻结值），写回版本因此没有可写的东西

### 结论

- LLM 变异在降质任务族上确实持续改进，且显著优于规则变异；但在完美种子上无梯度可爬
- 回写暂缓：本轮改进来自策略而非冻结参数，写回只会写回同值并重建锚点

## [1.17.0] - 2026-11-24

杩涘寲閫傚簲搴︽帴涓婇獙璇佸櫒锛屽苟淇帀 daemon 瑙傚療妯″紡鐨勪袱澶勫け鐪熴€?
### Added

- `evaluate_strategy` / `evolve` / `sharded_evolve` / `combined_evolve` 鏀寔 `verifier`锛氬瀭鐩翠竴鑷存€т笌缃俊鍒嗙粡鐙珛楠岃瘉鍣ㄦ牳瀵瑰悗鎵嶈鍒?- `combined_evolve(reference_cfg=...)`锛氬弬鏁板€欓€夋敼鐢ㄥ浐瀹氬弬鐓ф潈閲嶉噸鎵撳垎锛岄伩鍏嶃€岃鎼滅储鐨勬潈閲嶅悓鏃跺厖褰撴墦鍒嗗嚱鏁般€?- `agh daemon` 鍙傛暟璺ㄨ疆鍦ㄥ唴瀛樺欢缁紙`--no-write-back` 涔熻兘鐪嬪埌绱Н锛夛紱鍐呭眰鎸?`generations` 杞€€鐏€佹瘡杞?3 涓弬鏁板€欓€?
### Fixed

- 鏃犻獙璇佸櫒鏃惰繘鍖栭€傚簲搴﹂《鍦?`coverage` 鏉冮噸锛?.422锛夛紝鑰岀瀛愮瓥鐣ュ氨鏄笂鐣岋紝浠讳綍鍙樺紓鍙兘鏇村樊鈥斺€旀悳绱㈢┖闂存病鏈夋搴?- `tests/conftest.py` 鏂板 `frozen_copy`锛氬洖鍐欐祴璇曚笉鍐嶇洿鎺ユ敼浠撳簱 `config/frozen/thresholds.json`锛堟鍓嶈窇鍏ㄩ噺娴嬭瘯浼氭薄鏌撲粨搴撳苟閲嶅缓閿氱偣锛?
### Measured

- 6 鍩哄噯銆佸喕缁撴潈閲嶏細绉嶅瓙 0.65792锛堟棤楠岃瘉鍣ㄥ彛寰?0.422锛夛紝鍗曡疆杩涘寲 0.66625锛岀瓥鐣ョ┖闂寸悊璁轰笂鐣?0.68212
- 鍚屼竴鎵圭瀛愮瓥鐣ュ彧鎹㈡潈閲嶅嵆鍙粠 0.65792 鍒峰埌 0.75488锛氭鍓?daemon 鐨勩€屾敼杩涖€嶄富瑕佹槸鎹㈠昂瀛愶紱鍥哄畾鍙傜収鎵撳垎鍚庝笉鍐嶅崟璋冧笂鍗?- LLM 鍙樺紓鍣ㄤ笌瑙勫垯鍙樺紓鍣ㄥ崟杞悓鍒嗭紙0.66625锛夛紝鏈瀵熷埌浼樹簬瑙勫垯鎼滅储

### 缁撹

- 璇ュ熀鍑嗘棌 + 绉嶅瓙绛栫暐宸叉帴杩戜笂鐣岋紝daemon 娌℃湁鍙寔缁敼杩涚┖闂达紱鍥炲啓鐗堟湰鏆傜紦锛岄渶瑕佹洿闅剧殑鍩哄噯鎴栫湡瀹炲け璐ユ牱鏈?
## [1.16.0] - 2026-11-24

daemon 支持 LLM 变异器与 token 硬预算。

### Added

- `agh daemon --llm-mutator --provider --model --api-key-env --daily-budget`
- 预算用尽自动停止并写进报告 `tokens_used`；预算内退化回规则变异
- `combined_evolve` 透传 `mutator`

### Measured

- 冒烟（2 基准、1 代、population 1）：tokens_used 1607，未触顶

## [1.15.0] - 2026-11-24

自主迭代闭环。

### Added

- `agh/autonomous.py` + `agh daemon`：多轮进化 → 校准门禁 → 回写冻结层 → 失败回滚；plateau 自动停
- 默认零 token（规则变异 + 本地打分）；`--no-write-back` 只观察不落盘
- 测试 238 → 241

## [1.14.0] - 2026-11-24

工程化收尾：类型检查、文档站、构建产物。

### Added

- mypy 渐进接入（`check_untyped_defs`，5 个动态模块先忽略，其余 32 个文件检查通过）
- `mkdocs.yml` + `docs/index.md` + `docs/api.md`，可本地构建站点
- `python -m build` 产出 sdist/wheel；`docker-compose.yml` 可起 NATS 做联调

## [1.13.1] - 2026-11-24

### Added

- `run_llm_experiment.py --parallel N`：样本级并发，每个任务独立客户端，usage 汇总

## [1.13.0] - 2026-11-24

性能与回归兜底。

### Added

- `run_llm_bench.py --parallel N`：真模型跨基准并发跑（每任务独立客户端）
- `evolution_sharded` 分片评估记忆化：同骨架同策略同参数直接复用，进化重复轮次不再重算
- 监督者进程端到端测试：真实子进程启动/停止

### Note

- `EventLog` 原本就在内存缓存 entries，`verify()` 不重复读盘，无需改动

### Tests

- 237 → 238

## [1.12.0] - 2026-11-24

校准进 CI：验证器改动不能悄悄回退。

### Added

- `tests/fixtures/calibration.json`：19 题人工分级标注固化
- `tests/test_calibration_regression.py`：ECE ≤ 0.05、二值 kappa ≥ 0.9、正负样本下限
- 测试 234 → 237（CI 自动执行）

## [1.11.4] - 2026-11-24

分级校准累计 19 题。

### Added

- `make_graded_packet.py --exclude`：按内容排除已标注候选

### Measured

- 新增 7 题：ECE 0.0
- 合并 19 题：ECE 0.009、MAE 0.009；四轮 0.024 → 0.019 → 0.014 → 0.009

## [1.11.3] - 2026-11-24

分级校准扩到 12 题。

### Measured

- 12 题：ECE 0.014、MAE 0.014；验证器均值 0.806 vs 人工 0.792
- 三轮 ECE：0.024 → 0.019 → 0.014，稳定

## [1.11.2] - 2026-11-24

分级校准扩到 9 题。

### Measured

- 9 题分级标注：ECE 0.019、MAE 0.019；验证器均值 0.796 vs 人工 0.778
- 与上一轮 7 题（ECE 0.024）一致，概率校准结论稳定

## [1.11.1] - 2026-11-24

分级标注：概率校准初步成立。

### Added

- `scripts/make_graded_packet.py`：0/0.5/1 分级标注包
- `score_labels.py` 支持分级标签（ECE + MAE）；`calibration.ece` 支持浮点标签

### Measured

- 7 题分级标注：ECE 0.024、MAE 0.024，验证器均值 0.738 vs 人工 0.714
- 样本小，需扩大

## [1.11.0] - 2026-11-24

### Added

- `agh/report`：汇总 `runs/` 下各实验（M0、实验、消融、真模型、校准）成一张表
- 测试 230 → 234

## [1.10.2] - 2026-11-24

### Added

- `docs/STATUS.md`：交接文档，按可信度列出证据、限制与下一步优先级

## [1.10.1] - 2026-11-24

真实失败样本校准。

### Added

- `scripts/make_real_packet.py`：从真实模型输出里挑失败样本与正例
- `score_labels.py --threshold`：验证器判为支持的阈值（默认 0.99）

### Measured

- 50 次难基准：45 满分、5 个部分失败（其中 1 个骨架无垂直移动，排除）
- 9 题人工标注：二值一致率 1.0、kappa 1.0；ECE 0.241（验证器分级分 vs 人工二值，粒度不同）

## [1.10.0] - 2026-11-24

加难基准：差距扩大，真实失败样本开始出现。

### Added

- `run_llm_bench.py` 支持 `--min-nodes/--max-nodes/--extra-edges/--required-ratio`，报告记录每个骨架的验证器分数

### Measured

- 难基准 12 个（7–8 节点、必需项 0.6）：真模型 0.6744 vs 规则 0.76478，差 -0.09038（CI -0.11809–-0.05952）
- 验证器分布：11 个 1.0、1 个 0.5（真实部分失败，8%）

## [1.9.2] - 2026-11-24

人工标注 · 平衡集：验证器与人工完全一致。

### Added

- `scripts/make_balanced_packet.py`：5 正 5 负标注包，题间粗分隔；负例由删边/删节点构造

### Measured

- 平衡集 10 题：一致率 1.0、Cohen's kappa 1.0、ECE 0.0
- 首批全正例 8 题：一致率 0.875、kappa 0.0（无负例）
- 注意：负例按同一条规则构造，属「规则实现正确 + 人机理解一致」，非语义正确性

## [1.9.1] - 2026-11-24

人工标注首轮结果：验证器仍未校准。

### Added

- `scripts/make_label_packet.py` / `scripts/score_labels.py`：是非题标注包与打分脚本；无垂直移动的题自动排除

### Measured

- 10 题人工标注：2 题因骨架无垂直移动排除；剩 8 题一致率 0.875、kappa 0.0、ECE 0.125
- 原因：候选集几乎全为正例（验证器全给 1），缺少负例，kappa 无法区分
- 结论：需要平衡的正负例集合才能校准

## [1.9.0] - 2026-11-24

计费、NATS 适配、SQLite 日志。

### Added

- `agh/costs.py`：usage → BudgetVector（单价可配），接 `Ledger`
- `agh/bus_nats.py`：JetStream 适配器（去重头、期望序号、ack/nak），客户端注入可测
- `agh/sqlite_log.py`：SQLite 事件日志，与 JSONL 同语义
- 测试 224 → 230

## [1.8.0] - 2026-11-24

红队演练 + 真实 token 用量。

### Added

- `agh/redteam.py` + `scripts/red_team.py`：7 类本地攻击，全部拦住
- `EventLog.verify_against(head, size)`、`head()`、`size()`：外部锚点才能发现日志尾部截断
- 实验报告带 `usage`（prompt/completion/total tokens）
- 测试 222 → 224

### Found

- 本地哈希链无法发现日志截断（剩余链自洽），必须靠外部链头+长度；红队里单列这一条并验证锚点方案

## [1.7.1] - 2026-11-24

### Added

- 验证器「已知答案」测试：5 个正反例全部符合声明规则（证明实现正确，不证明规则正确）

## [1.7.0] - 2026-11-24

盲裁判校准，结果是否定的。

### Added

- `LlmJudgeVerifier(blind=True)`：裁判不给规则，自行判断
- `run_verifier_calibration.py --blind`
- 测试 219 → 221

### Measured

- 盲裁判（10 候选）：一致率 0.8、Cohen's kappa 0.0、ECE 0.2；盲裁判对所有候选都给 1.0
- 结论：结构验证器尚未被独立校准；模型裁判不可靠，需要人工标注

## [1.6.0] - 2026-11-24

三件补齐：Ed25519 主链路、跨基准真模型实验、验证器校准。

### Added

- `agh run --sign ed25519`：主链路可用 Ed25519（开发密钥确定性派生）
- `scripts/run_llm_bench.py`：真模型在 10 个生成骨架上一一重构，与同骨架规则子级对比，候选落盘
- `agh/verifier.py`：`LlmJudgeVerifier`（模型裁判）
- `agh/calibration.py`：一致率、Cohen's kappa、ECE；`scripts/run_verifier_calibration.py`
- 测试 213 → 219

### Measured

- 跨 10 骨架：真模型 0.62229 vs 规则 0.69081，差 -0.06851（CI -0.11277–-0.02372）
- 校准 10 个候选：一致率 1.0、kappa 1.0、ECE 0.0（裁判提示复述同一规则，属不冲突而非独立佐证）

## [1.5.0] - 2026-11-24

独立验证器：自报指标改成可核对的结构证据。

### Added

- `agh/verifier.py`：`StructuralVerifier`（parts + edges 证据核对垂直移动）、`CoverageVerifier`、`make_verifier`
- `run_llm_experiment.py --verifier structural|coverage`；规则基线与被测模型使用同一个验证器

### Fixed

- `faithful_child` 现在上报 `content.vertical_moves` 的保留深度（之前没报，接验证器后基线被自己扣分）

### Measured

- 无结构提示 12 次：0.79396 vs 规则 0.80795（差 -0.014）
- 加结构提示 12 次：0.76546（差 -0.043），提示仍有害
- M0：胜者 `child-faithful` 0.80233
- 测试 208 → 213

## [1.4.0] - 2026-11-24

门控自报垂直一致性，并修正由此暴露的假高分。

### Fixed

- `score_candidate`：没有验证器信号时垂直一致性不计分（此前候选自报 `vertical_moves` 即可拿满 0.3182 权重，属于自报刷分）
- `build_prompt`：写清 `content.vertical_moves` 的元素格式（`{"node": ..., "preserved_depth": ...}`），此前未定义导致模型写成字符串数组
- `vertical_consistency` 接受字符串条目（深度未报按声明深度计，不因格式差异惩罚）
- `ablation._winner_score`：仲裁因全 0 分不选人时按 0 分处理

### Measured（修正后）

- 无提示 12 次：均分 0.40187，规则基线 0.422，差 -0.02013（CI -0.02935–-0.01024）
- 加结构提示 12 次：0.379（差 -0.043），提示反而有害
- 1.4.0 之前的真模型分数（0.49–0.51）包含自报加分，作废
- 测试 206 → 208

## [1.3.0] - 2026-11-24

温度消融，并修脚本参数未生效。

### Fixed

- `run_llm_experiment.py` 的 `--max-tokens` / `--temperature` 之前没有真正赋给客户端（消融跑出来两组都是默认温度）

### Measured

- temperature 0.2（40 次）：均分约 0.498，配对差 -0.012，CI 不含 0
- temperature 0.9（12 次）：均分 0.50554，差 -0.005，CI 含 0
- command-code 端点只支持 deepseek-v4.1-flash；另外四个模型名均 400

## [1.2.0] - 2026-11-24

提示消融：验证「给骨架不给答案」的代价。

### Added

- `build_prompt` / `LlmChild` 支持可选 `reference`；`run_llm_experiment.py --include-reference`
- 测试 204 → 206

### Measured

- 不给参考（12 次）：均分 0.50315（0.474–0.511）
- 给参考（12 次）：12/12 精确复刻基线 0.511
- 结论：不给答案压低约 0.8 个点，模型无法自行发现 `pred:hierarchical` 这类结构标签

## [1.1.0] - 2026-11-24

真模型契约通过率实验，并修掉截断导致的假失败。

### Added

- `scripts/run_llm_experiment.py`：真模型重复重构，统计通过率、分数分布与对规则基线的配对差
- CLI `--max-tokens`

### Fixed

- `providers`：`finish_reason=length` 时按截断处理并放大预算重试（此前 reasoning token 吃满输出，表现为 JSON 括号不闭合）

### Measured

- deepseek-v4.1-flash，8 次：8/8 通过契约，均分 0.48899，规则基线 0.511，配对差 -0.02201（CI -0.03225–-0.00921）

## [1.0.0] - 2026-11-24

第一个稳定版本：公开 API 冻结，自我改写闭环补齐。

### Added

- `agh/supervisor.py`：独立监督者进程，持有指针、跑 gate、管理子进程；`request.json` 投递切换请求，启动失败自动回滚
- `python -m agh.supervisor` 入口
- 测试 198 → 204

### Compatibility

- 1.x 冻结公开 API（见 README「版本与兼容」）；破坏性改动走 2.0

## [0.17.0] - 2026-11-24

自我改写的安全底座，回答「能不能让 AGH 改自己代码」。

### Added

- `agh/selfmod.py`：不可变制品（tar.gz + manifest + sha256）、原子指针切换、门禁 promote、回滚、显式 gc
- `CallableGate` / `CommandGate`
- 测试 190 → 198

### Design note

- 不做「跑通就删旧代码」；旧版本永久保留，回收只按保留期与最近 N 个
- 门禁失败或异常时现网不动；监督者必须在被改代码之外，否则门禁无效

## [0.16.0] - 2026-11-24

元进化：学会怎么改自己，并自己加难度。

### Added

- `agh/meta.py`：5 种参数算子 + UCB1 老虎机；连续两轮无改进自动升级课程（节点/边/必需项）
- CLI `agh evolve --mode meta`
- 权重钳制非负（修 `weight_down` 可能把权重压成负数）
- 测试 184 → 190

### Measured

- 8 轮：难度 1 → 4，参数收敛 `confidence 0.049 / structural 0.169 / update 0 / vertical 0.369 / coverage 0.414`

## [0.15.0] - 2026-11-24

第二轮进化结果写回冻结层。

### Changed

- `config/frozen/thresholds.json`：权重 `confidence 0.05 / structural 0.172 / update 0 / vertical 0.356 / coverage 0.422`，`dissent_tau 0.18`
- 锚点重建；M0 胜者不变，分数 0.55092 → 0.55313，异议 0.43320 → 0.45975
- 归一化后的进化曲线：0.54253 → 0.67324（6 轮）

## [0.14.2] - 2026-11-24

修一个让「进步」变假的缺陷：参数变异后权重和不再为 1。

### Fixed

- `mutate_params` 与 `ParamGenome.config` 对权重做归一化；此前变异后总和可到 1.1，分数被整体抬高，看上去的改进有一部分只是缩放
- 归一化后重跑（10 基准，6 轮）：曲线 0.54253 → 0.67324，参数收敛 `confidence 0.05 / structural 0.172 / update 0 / vertical 0.356 / coverage 0.422`，`dissent_tau 0.18`
- 测试 182 → 184

## [0.14.1] - 2026-11-24

修垂直一致性只由骨架决定的缺陷。

### Fixed

- `vertical_consistency` 现在按候选实际上报的 `content.vertical_moves` 计算；缺报按 0 计，不再让所有候选吃同一份骨架加分
- 冻结权重写回后重跑：M0 胜者仍为 `child-faithful`，分数 0.55092，异议 0.43320
- 测试 181 → 182

## [0.14.0] - 2026-11-24

把进化收敛出的权重写回冻结层。

### Changed

- `config/frozen/thresholds.json` 的 arena 权重改为进化结果（归一化后）：confidence 0.1818、structural 0.1818、update 0.0、vertical 0.3182、coverage 0.3182
- 锚点已重建；M0 胜者不变（`child-faithful`），分数 0.62025 → 0.77366，异议 0.476 → 0.65594

### Found

- `vertical_consistency` 目前只由骨架决定、与候选无关，高权重下会把所有候选的分数一起抬高。这是下一处要修的评分缺陷。

## [0.13.0] - 2026-11-23

参数层退火步长 + 多参数变异，combined 模式开始真正爬坡。

### Changed

- `mutate_params` 支持 `scale`，并可一次改 1–2 个权重
- `combined_evolve` 前半程步长 0.1、后半程 0.02（`anneal_scale`）
- 实测 10 基准 4 轮：均值 0.29863 → 0.55807，权重收敛到 `update=0, vertical=0.35, coverage=0.35`
- 测试 179 → 181

## [0.12.0] - 2026-11-23

结合两条路线：分片精英 + 全局参数进化。

### Added

- `agh/evolution_sharded.py`：`sharded_evolve`（每基准独立档案）与 `combined_evolve`（外层进化评分参数，内层分片）
- CLI `agh evolve --mode single|sharded|combined`、`--rounds`
- 测试 174 → 179
- 实测 10 基准：分片 0.29863 vs 单基因组 0.22972，配对差 +0.0689（CI 0.0167–0.1162）

## [0.11.0] - 2026-11-23

可配置基准生成器，让对照有区分度。

### Added

- `agh/benchmarks.py`：按固定节点词汇生成随机骨架（边、必需项随机），参照签名取自各自骨架
- CLI `agh evolve --benchmarks N --bench-seed S`
- 测试 170 → 174

## [0.10.3] - 2026-11-23

修一个让进化无法发生的适应度缺陷。

### Fixed

- `default_benchmarks` 的参照签名改为取自骨架本身（边），不再用种子策略。此前任何变异都会拉大与父代的结构距离、被评分惩罚，进化在数学上不可能赢；改后补全缺失边会加分
- 实测（LLM 变异器，5 代 × 3 个体）：曲线 0.33167 → 0.36306，11 个变异被接受，最优策略补上了缺失的 `P1-C3`

### Tests

- 169 → 170：补全缺失边应比缺边得分高

## [0.10.2] - 2026-11-23

跑通真实模型（command-code / deepseek-v4.1-flash）。

### Fixed

- `providers`：请求带浏览器 User-Agent（command-code 的 Cloudflare 会拦默认 UA）；`content` 为 null 时抛明确错误并带 `finish_reason`
- `llm.build_prompt`：`signature.abstraction` 示例改成布尔（模型照抄字符串会导致校验失败）
- CLI `--llm-mutator` 的特征池扩到节点、边与 `pred:*`，此前只能从父代特征里选，变异几乎没有空间

### Added

- `command-code` 提供商预设
- 测试 167 → 169

## [0.10.1] - 2026-11-23

### Fixed

- `compare_search` 透传 `mutator`：此前对照里的进化用的是规则变异器，与主循环不一致；CLI 现在会把 `--llm-mutator` 带进对照

## [0.10.0] - 2026-11-23

接入真模型。

### Added

- `agh/providers.py`：OpenAI 兼容 chat completions 适配器（DeepSeek / OpenAI / OpenRouter / Ollama 预设），密钥只从环境变量读，JSON 模式 + 重试
- `evolve(..., mutator=...)`：变异器可注入；CLI `--llm-mutator --provider --model --api-key-env`
- `scripts/run_llm_child.py`：用真模型跑一次子级重构
- 测试 162 → 166

## [0.9.0] - 2026-11-23

对照实验降方差、基线加强。

### Added

- `hill_climb` 支持 `restarts`，默认对照用 3 次重启
- `compare_search` 支持 `seeds_per_run`：每轮多种子取均值再配对
- CLI `agh evolve --seeds-per-run N`
- 报告输出每轮进化与基线的逐项分数
- 测试 160 → 162

## [0.8.0] - 2026-11-23

让进化过程可审计，让对照更严格。

### Added

- `evolve(..., log=EventLog)`：变异、接受、结束写入哈希链日志，报告带 `log_entries` / `log_ok`
- `hill_climb` 基线：贪心爬山，不留档案
- `compare_search` 支持多基线（random / hill），Holm 校正多重比较
- CLI `agh evolve` 默认写 `runs/evolve/events.jsonl`
- 测试 158 → 160

## [0.7.0] - 2026-11-23

让自我迭代可被真模型驱动，也让它可被证伪。

### Added

- `agh/evolution_llm.py`：`LlmStrategyMutator`（模型提议变异，池子过滤 + 边界钳制 + 失败退回规则变异）
- `random_search` 基线：同评估预算的随机搜索
- `compare_search`：进化 vs 随机搜索的配对 bootstrap 比较
- CLI `agh evolve --compare-runs N`
- 测试 152 → 158

## [0.6.0] - 2026-11-23

加入档案式自我迭代，参考 DGM（2505.22954）、AlphaEvolve（2506.13131）、自进化智能体综述（2507.21046），并针对 misevolve 风险（2509.26354）设边界。

### Added

- `agh/evolution.py`：受限基因组（特征/覆盖/置信/深度）、有界变异、档案保留全部变体、分数+新颖度锦标赛、血统记录、预算租约、治理门
- `agh evolve` 子命令；`scripts/` 无新增，CLI 直接可用
- 测试 144 → 152

### Notes

- 适应度来自规则子级在多个骨架基准上的竞技场分数，只验证机制
- 接 `LlmChild` 后可进化提示词策略，接口不变

## [0.5.0] - 2026-11-23

补齐生产化与跨组织能力。

### Added

- `agh/timestamp.py`：外部可信时间戳（HMAC 本地 TSA / HTTP TSA），链头锚点落盘与验证
- `agh/billing.py`：外部计费接入，结算后按 ref 幂等扣款，收据可核对
- `agh/forgetting.py`：可验证遗忘，签名墓碑 + 残留扫描
- `agh/claims.py`：跨组织声明与 Merkle 透明日志（包含证明、签名树头）
- `agh/sdk.py`：Python SDK；CLI 增加 verify / replay / experiment / ablation / version 子命令
- 测试 122 → 144

## [0.4.0] - 2026-11-23

按对比报告补齐消融、度量与生产签名。

### Added

- `agh/ablation.py`：9 组消融（完整链路 + 8 个单点关闭），配对 bootstrap + Holm；`scripts/run_ablation.py`
- `agh/experiment.py`：新增 `best_of_n` 基线；报告增加三个度量——关键事实保留率、立场熵、误拦率
- `agh/crypto.py`：Ed25519 签名后端（`KeyRing.with_ed25519` / `register_ed25519`），密钥轮换 `rotate(overlap_ms=...)`，HMAC 与 Ed25519 按 kid 自动分派
- 依赖 `cryptography>=42`
- 测试 114 → 122

### Changed

- README 增加「消融与度量」「签名后端」两节

## [0.3.0] - 2026-11-23

补上「M0 只有规则子级」和「没有竞技场实验」两个最大缺口。

### Added

- \gh/llm.py\：LLM 子级适配器。\LlmChild\ 接收任意 \complete(prompt) -> str\ 传输函数，负责拼提示、抽 JSON、按 econstruction_schema\ 校验；失败抛 \ChildOutputError\（带原始文本与逐条错误）
- \gh/experiment.py\：G1 竞技场实验。多子级 × 多种子跑完整链路，输出胜率、均分、contested 比例，并和 \single\ / \majority\ 基线做配对比较
- \gh/evalstats.py\：新增 \ootstrap_pvalue- \scripts/run_experiment.py\：一键跑实验并写 uns/g1/experiment.json- 测试 102 → 114

### Changed

- README 增加「接真 LLM」「G1 实验」两节，模块表补 \llm.py\、\experiment.py
## [0.2.0] - 2026-11-23

项目改名 AGH，补齐命令行与 lint。

### Added

- `python -m agh` 入口与 `agh` 控制台脚本；`--refresh-anchor` 重建冻结层锚点
- ruff 配置（line-length 120，忽略中文全角标点的 RUF001-003）；CI 加 lint 步骤
- `py.typed` 标记；`SECURITY.md`；版本号一致性测试

### Fixed

- `bus.publish_batch`：批次大于去重窗口时 KeyError
- `governance.observe`：停车不幂等，`from_state` 记错
- `ledger.settle`：超预留未比较 `wall_ms`
- `arena.diversity_precheck`：两两距离重复计算，O(n³) → O(n²)

### Changed

- 包名 `agh-framework` → `AGH`；仓库与文档统一为 AGH
- 清理 55 处 lint 问题（未用导入、导入排序、可合并判断等）
- 测试 95 → 102

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
