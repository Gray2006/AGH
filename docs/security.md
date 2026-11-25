# 安全边界与扫描

这份文档说清楚 AGH 防什么、不防什么，以及怎么复查。

## 威胁模型

### 防的

| 威胁 | 机制 |
|---|---|
| 子级伪造出处（改载荷 / 改签名 / 未知签发者 / 重放） | `ProvenanceGateway` 签名 + `EnvelopeVerifier` 验签，写入门拒收 |
| 超预算调用 | `Ledger` 先预授权后调用，超预留直接拒绝 |
| 日志被篡改 | 哈希链，`verify` 检出；`replay` 逐位重放 |
| 整链替换 | `anchor` 把链头签进本地 JSONL 或 git tag |
| 候选伪造测试通过 | 执行验证器的期望值只留父进程，子进程只回传输出 |
| URL 诱导读本地文件 | `netutil.ensure_http_url` 只允许 http/https |

### 不防的

- **恶意代码执行**：`ExecutionVerifier` 的子进程只防失控（超时、rlimit、清环境、临时目录），
  不隔离网络和文件读权限。评估不可信输出时必须放进容器或无网络沙箱
- **有 push 权限的人**：同时改日志和改 tag 的人，外部锚定也拦不住
- **密钥泄露**：本地 keyring 的密钥如果泄漏，签名就失去意义
- **拒绝服务**：没有速率限制

## 运行时依赖

AGH 只依赖四个包，全部是主流库：

| 包 | 用途 |
|---|---|
| `pydantic>=2.7` | 数据模型校验 |
| `numpy>=1.26` | 统计与 bootstrap |
| `jsonschema>=4.20` | 配置校验 |
| `cryptography>=42` | Ed25519 签名 |

`nats-py` 是可选依赖（`[nats]`），只在联调时用。

## 怎么复查

### 静态扫描

```bash
pip install bandit
python -m bandit -r agh
```

当前结果：**High 0 / Medium 0**。33 个 Low 是 subprocess 调用和 `random.Random(seed)`
（确定性用途，不是加密随机）。

### 依赖漏洞

```bash
pip install pip-audit
python -m pip_audit --skip-editable
```

在开发环境里跑会报 `soupsieve` 的 CVE——它来自 `beautifulsoup4`，而 `beautifulsoup4`
是文档/开发工具的间接依赖，**不在 AGH 的运行时依赖里**，不影响用户。

验证方法：在只装了 wheel 的干净 venv 里跑 `pip-audit`，应该只剩上面四个包。

### 测试里的安全用例

```bash
python -m pytest tests/test_crypto.py tests/test_gate.py tests/test_governance_bench.py -q
```

覆盖：伪造被拒、篡改检出、重放被拒、超预算拒绝、URL scheme 拒绝。

## 报告问题

见仓库根目录的 `SECURITY.md`。
