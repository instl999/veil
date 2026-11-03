# 客户端配置

每台设备都有 **自己的订阅链接**，因为每台设备模仿的是它自己浏览器的 TLS 指纹
（Mac 上的 Safari、Windows 上的 Chrome、iPhone 上的 iOS）。应用由你自己安装，
veil 提供链接。在服务器上：`veil` → **1**（链接）或 **2**（二维码），或者：

```bash
veil links              # 所有订阅链接和分享链接
veil links --qr mac     # 某台设备的二维码：mac、windows、iphone、router、shadowrocket
```

设置了 CDN 线路后，订阅链接经过 Cloudflare，即使服务器 IP 被封也能继续更新。
请妥善保管——任何拿到链接的人都能使用你的服务器。应用每 12 小时更新一次订阅，
凭据轮换和配置调整就是这样同步到设备上的。

默认设备：`mac`（Safari）、`windows`（Chrome）、`iphone`（iOS）、`router`（Chrome），
以及给 Shadowrocket 用的 `shadowrocket` 链接。

## 应用中会看到的分组

| 分组 | 用途 | 默认 |
|---|---|---|
| `PROXY` | 所有境外流量 | `AUTO` |
| `AUTO` | 浏览用的自动切换链 | REALITY → CDN → HY2 |
| `MEDIA` | YouTube | HY2 → REALITY → CDN（可由画像工具个性化） |
| `GAMES` | Steam 内容服务器 | 直连 |

自动切换分组会在某条线路失效时自动切换。国内网站和应用始终直连。

## Windows 和 macOS —— Clash Verge Rev

1. 从 [GitHub Releases](https://github.com/clash-verge-rev/clash-verge-rev/releases)
   安装 Clash Verge Rev。
2. **订阅** → 粘贴 `windows`（或 `mac`）链接 → **导入** → 点击该订阅使其生效。
3. **设置 → 系统代理：开启**（仅浏览器），或 **TUN 模式：开启**（所有应用，推荐；
   允许安装它提示的服务）。
4. 首次启动会下载规则数据库，请稍等一分钟。

不要修改下载的配置——每次更新都会被覆盖。本地增改请使用 Clash Verge 自带的
合并/规则编辑器。

## 安卓、Windows、macOS、Linux —— FlClash

[FlClash](https://github.com/chen08209/FlClash) 使用相同的 mihomo 内核和相同的配置，
是安卓上最简单的选择。

1. 从 GitHub Releases 页面安装 FlClash。
2. 在服务器上：`veil` → **3. 添加设备**，指纹选 `android`（手机）或
   `chrome`/`safari`（电脑），客户端选 `flclash`。
3. 用手机相机扫描显示的二维码——FlClash 会打开并一步导入。或在 FlClash 中：
   **配置 → + → URL** 并粘贴。
4. 在仪表盘中启动；安卓上允许 VPN 授权。

## iPhone 和 iPad —— Shadowrocket（小火箭）

Shadowrocket 是非中国大陆区 App Store 的付费应用（需要非国区 Apple ID）。

1. 在服务器上：`veil` → **2** → `shadowrocket`（或 `veil links --qr shadowrocket`）。
2. 在 Shadowrocket 中点击左上角的扫码图标扫描，或 **+ → 类型：Subscribe** 并粘贴
   `shadowrocket.txt` 链接。
3. **设置 → 订阅 → 自动更新：开启。** 必须开启：凭据每 30 天轮换，旧凭据 7 天后
   失效。
4. 使用 **配置 → 规则** 分流模式，让国内应用保持直连。

说明：Shadowrocket 的延迟测试不会为 `veil-HY2` 显示数字——这是正常的；选中它并
打开网页即可测试。Shadowrocket 在节点之间没有自动切换：如果 REALITY 不通，请
选择 `veil-CDN`。

替代方案：**Stash**（同样在非国区 App Store）可以直接使用 `iphone` 链接，分组、
规则和自动切换都相同。

## OpenWrt —— OpenClash

1. **插件设置 → 版本更新：** 安装 **Meta (mihomo)** 内核。
2. **配置订阅 → 添加：** `router` 链接，开启自动更新。
3. **插件设置 → 运行模式：** Fake-IP（TUN 或混合）。保留配置中的 DNS 设置。
4. 启动 OpenClash；应能看到 `PROXY`、`AUTO`、`MEDIA` 和 `GAMES`。

这样家里 Wi-Fi 下的设备都由路由器代理；在家时请关闭设备上的应用，避免重复代理。

## 添加或修改设备

`veil` → **3. 添加设备** / **4. 删除设备**，或者：

```bash
veil device add ipad --fingerprint ios --client shadowrocket
veil device rm windows
veil device list
```

客户端：clash-verge、flclash、openclash、shadowrocket、stash、other。
指纹：chrome、safari、ios、firefox、edge、android、360、qq、random。
[画像工具](profiling.md) 可以告诉你每台设备实际匹配的是哪一个。
