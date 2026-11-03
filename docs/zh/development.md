# 开发与发布

## 仓库结构

```
install.sh              git 安装的入口（运行 server/install.sh）
server/
  install.sh            安装脚本和设置向导（bash）
  veil/                 `veil` 工具（Python 3.9+，仅标准库）
    core.py             路径、状态、密钥、轮换、画像验证
    render_server.py    生成 sing-box、Caddyfile 和 nftables 配置
    render_client.py    mihomo 配置、分享链接、订阅链接
    system.py           应用配置、健康检查、维护、升级、提醒、备份
    doctor.py           `veil doctor`：带解释和修复方法的检查
    net.py              HTTP、DNS-over-HTTPS 和 WebSocket 探测
    cli.py, menu.py     命令行和交互菜单
  systemd/              服务和定时器单元
  decoy/                伪装网站
profiler/               在你自己的电脑上运行：抓包、拟合、自检
tests/                  离线单元测试
tools/
  build.py              构建 dist/veil-install.sh（单文件安装脚本）
  validate_configs.sh   用真实的 sing-box/Caddy/nft 检查生成的配置
  check_sanitized.py    拒绝密钥和个人信息（文件和历史）
  setup-ssh-key.*       可选：在 Windows 上设置 SSH 密钥
docs/en, docs/zh        文档（两种语言保持同步）
.github/workflows/      CI 和发布
```

## 常用命令

```bash
python -m unittest discover -s tests -v    # 单元测试（任何系统）
python tools/build.py                      # dist/veil-install.sh + .sha256
shellcheck -S warning server/install.sh install.sh tools/validate_configs.sh
sudo bash tools/validate_configs.sh        # 在装有 sing-box、caddy、nft 的 Debian 上
python tools/check_sanitized.py --history  # 每次推送前
```

CI（`.github/workflows/ci.yml`）会在每次推送时运行以上所有检查，包括用真实的
sing-box/Caddy/nft 验证配置。

## 保持仓库干净

绝不提交真实的 IP、域名、密钥、证书、订阅链接、日志或抓包文件。使用以下占位符：

| 类型 | 占位符 |
|---|---|
| 服务器 IP | `203.0.113.10`（以及 `198.51.100.x`、`192.0.2.x`） |
| 站点域名 / CDN 域名 | `www.example.com` / `static.example.net` |
| 邮箱 | `you@example.com` |
| 令牌、UUID | `<token>`、`<uuid>` |

`tools/check_sanitized.py` 会拦截通用情况。对于你自己的信息，在仓库根目录创建
`.sanitize-denylist`，每行一项（服务器 IP、域名、邮箱、主机名）。它已在
`.gitignore` 中，只保存在你的电脑上；如果它被跟踪，检查也会失败。在每次提交前
运行检查：

```bash
printf '#!/bin/sh\nexec python tools/check_sanitized.py\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

如果敏感信息曾经被提交过，仅在新提交中删除是不够的：需要改写历史（如
`git filter-repo`）、强制推送，并更换泄露的密钥。

## 发布

1. 更新 `server/veil/__init__.py` 中的 `__version__`，并在 `CHANGELOG.md` 中添加
   一节。
2. 提交，然后打标签并推送：

   ```bash
   git tag v0.3.0 && git push origin main v0.3.0
   ```

3. 发布工作流会检查标签与版本是否一致，运行测试和泄露检查，构建
   `veil-install.sh` 及其 `.sha256`，并以 CHANGELOG 中对应的一节作为发布说明发布。

服务器会在下一次每晚检查时得知新版本，由你运行 `veil update` 更新。

## 使用你自己的 fork

修改 `server/veil/__init__.py` 中的 `REPO`（或在环境变量中设置
`VEIL_REPO=owner/name`），以及文档中的发布地址。其他部分与仓库无关。

## 约定

- 用户看到的每条消息都有中英文。
- 生成的文件从不手动修改；修改生成器和状态。
- 新设置在 `core.py` 中设置默认值，并由 `load_state` 补全，这样旧安装在
  `veil update` 后仍能正常工作。
- 安装脚本中的函数不能以失败的测试或 `a && b` 结尾（在 `set -e` 下会中止调用者）；
  请使用 `if`。
