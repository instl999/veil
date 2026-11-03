# 备份与恢复

## 备份包含什么

`/etc/veil/state.json`（所有密钥、密码和设置）、Cloudflare 源服务器证书和私钥，
以及伪装网站。有了这些就能以 **相同** 的订阅链接重建服务器，设备无需任何改动。
请像对待密码一样对待备份。

## 自动备份（在服务器上）

veil 每晚写入 `/var/lib/veil/backups/veil-YYYYMMDD.tar.gz`（仅 root 可读），保留
最近 14 份。它们可以用来撤销错误的修改，但服务器没了它们也就没了，所以还要在
你的电脑上保存一份。

```bash
veil backup --list
```

## 在电脑上保存一份

在服务器上：`veil` → **11. 备份 → 生成备份**（或 `veil backup`）。它会打印需要
**在你的电脑上** 运行的命令，例如：

```bash
scp root@203.0.113.10:/root/veil-backup-20260101-120000.tar.gz .
```

请私密保存（密码管理器附件、加密盘）。更换 CDN 域名、重置链接或轮换 `all` 后
重新备份。然后删除服务器上的副本：`rm /root/veil-backup-*.tar.gz`。

## 在同一台服务器上撤销修改

```bash
veil backup --list
veil restore /var/lib/veil/backups/veil-20260101.tar.gz
veil apply --restart
```

## 迁移到新服务器（或新 IP）

当服务器 IP 被封、商家出问题或你更换商家时使用。迁移期间，应用会通过 CDN 线路
继续工作。

1. 租一台新的 VPS（Debian 12）并登录。
2. 在你的电脑上把备份复制过去：

   ```bash
   scp veil-backup-20260101-120000.tar.gz root@198.51.100.20:/root/
   ```

3. 在新服务器上：

   ```bash
   curl -fsSLO https://github.com/instl999/veil/releases/latest/download/veil-install.sh
   bash veil-install.sh --restore veil-backup-20260101-120000.tar.gz
   ```

4. 在 Cloudflare 中把 **两条** A 记录都改成新 IP（站点域名保持灰色云朵，CDN 域名
   保持橙色云朵）。Cloudflare 中的其他设置不变。
5. 等几分钟，然后在新服务器上运行 `veil doctor`。应用会自动重新连接：所有配置都
   使用域名而不是 IP。
6. 可选：`veil rotate all`，然后退订旧 VPS。

## 没有备份？

重新安装（`bash veil-install.sh`），使用相同或新的域名，然后在每台设备上导入新的
订阅链接。不会丢失其他东西：veil 不保存其他数据。
