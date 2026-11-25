# 发布到 PyPI

两种方式，推荐第二种（Trusted Publishing，不用管 token）。

## 方式一：本地发布（有 token）

```bash
# 1. 把 token 放进文件（别贴聊天、别进 shell 历史）
#    ~/.pypi_token 内容一行 pypi-...
python scripts/publish.py --upload --token-file ~/.pypi_token
```

`scripts/publish.py` 会构建 → `twine check` → 上传。Windows 下它已经处理了
控制台编码和 `dist/*` 展开两个坑。

## 方式二：GitHub Actions（推荐）

仓库里已配好 `.github/workflows/release.yml`，用
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/)：
PyPI 信任这个 workflow 的 OIDC 身份，不需要长期 token。

**一次性配置**：

1. 打开 <https://pypi.org/manage/account/publishing/> → Add a new pending publisher
2. 填：
   - PyPI Project Name：`agh-gestalt`
   - Owner：`Gray2006`
   - Repository name：`AGH`
   - Workflow name：`release.yml`
   - Environment name：`pypi`
3. 在 GitHub 仓库 Settings → Environments 里建一个叫 `pypi` 的环境

**每次发版**：

```
Actions → release → Run workflow → confirm 填 publish → 运行
```

不填 `publish` 就只构建和校验，不上传。

## 版本号规则

AGH 用 SemVer，但比常见约定多一条（见 README「版本策略」）：

- 字段/签名兼容 → patch
- **分数语义变更** → minor，且 CHANGELOG 必须标 `Semantics`
- 删字段 / 改签名 → major

`tests/test_version.py` 会检查 pyproject、`__init__.py`、CHANGELOG、README 四处版本一致，
不一致 CI 直接红。

## 发版检查清单

```bash
ruff check agh tests scripts
mypy agh
python -m pytest -q          # 不打印汇总行，用 --collect-only 数 '^tests/' 行
python scripts/publish.py --check
```

然后更新 CHANGELOG / README 版本行 / docs/STATUS.md / memory，提交并打 tag。
