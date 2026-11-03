# Security policy / 安全策略

## Reporting a vulnerability / 报告漏洞

Please report security problems privately through GitHub: **Security →
Report a vulnerability** on this repository. Do not open a public issue.

请通过 GitHub 私下报告安全问题：在本仓库点击 **Security → Report a
vulnerability**。请不要公开提交 issue。

Include the veil version (`veil --version`), what you did and what happened.
Only the latest release is supported.

请附上 veil 版本（`veil --version`）、你的操作以及发生的情况。只支持最新发布版。

## Never share secrets / 切勿分享密钥

Before posting any output, log or screenshot anywhere (including issues),
remove:

在任何地方（包括 issue）贴出输出、日志或截图之前，请删除：

- server IP addresses and domain names / 服务器 IP 和域名
- subscription URLs and share links (`vless://`, `hysteria2://`) / 订阅链接和分享链接
- UUIDs, passwords, keys, certificates / UUID、密码、密钥、证书
- ntfy topics and Bark keys / ntfy 主题和 Bark key
- backup files (`veil-backup-*.tar.gz`) / 备份文件

If a secret was exposed, see the table in
[docs/en/security.md](docs/en/security.md#secrets-and-where-they-live) /
[docs/zh/security.md](docs/zh/security.md#密钥及其存放位置) for how to replace it.

如果密钥已经泄露，请参照上面链接中的表格进行更换。

## Repository hygiene / 仓库卫生

This repository must never contain real credentials, keys, IPs, domains,
subscription links or logs. `tools/check_sanitized.py` checks every file and the
whole git history in CI. See [docs/en/development.md](docs/en/development.md).

本仓库绝不能包含真实的凭据、密钥、IP、域名、订阅链接或日志。
`tools/check_sanitized.py` 会在 CI 中检查所有文件和完整的 git 历史。
