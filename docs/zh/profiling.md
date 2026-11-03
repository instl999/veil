# 使用画像工具进行个性化

画像工具会学习**你自己**正常上网时的流量特征，并据此调整 veil。它只在你自己的电脑上运行，从不在服务器上运行。

## 隐私

每个连接记录的内容：协议、服务器端口、服务器是否为你的 VPS、开始时间（精确到分钟）、持续时间、
字节数/包数、包大小与间隔的直方图、前 16 个包的大小，以及 TLS ClientHello 的 JA4 指纹（即密码套件和扩展的编号列表）。

**从不记录：** IP 地址、主机名/SNI、DNS 域名、URL、Cookie、任何载荷内容。发往局域网的连接会被完全跳过。
文件只保存在你的电脑上；只有很小的 `profile.json` 会上传到服务器。用完后请删除 `.jsonl` 采集文件。

## 调整的内容

| 设置 | 依据 |
|---|---|
| 每台设备的 TLS 指纹 | 浏览器的 JA4 与 REALITY 连接的 JA4 是否一致 |
| Hysteria2 端口跳跃间隔 | 你平时 QUIC 连接的存活时长（25%–75% 分位） |
| 视频线路顺序 | QUIC 在你正常流量中的占比：≥ 15% → HY2 优先，否则 REALITY 优先 |

它还会报告你最活跃的时段，以及有多少比例的流量发往 VPS。

## 环境要求

- Python 3.9+
- Wireshark 4.2 或更新版本（用于 JA4）。Windows 安装时勾选 Npcap，并以**管理员身份**运行终端；
  macOS 用 `sudo` 运行，或安装 Wireshark 的 ChmodBPF 组件。
- 可选：`pip install scikit-learn`，用于自检的综合评分。

## 第 1 步 —— 基线采集（关闭代理），约一周

关闭代理，正常使用设备（抖音、B 站、国内网站）。在每台电脑上运行：

```bash
python veil_profiler.py interfaces                  # 找到你的 Wi-Fi/有线网卡
python veil_profiler.py capture --device mac --mode baseline --hours 24 -i en0
```

在不同日子、不同时段（早上、晚上、周末）多采集几次。每次都会生成一个 `flows-<设备>-baseline-<时间>.jsonl` 文件。

**iPhone：** 用数据线连接到 Mac，用苹果的 `rvictl -s <UDID>`（Xcode 命令行工具自带）创建镜像网卡，
然后在 `rvi0` 上采集，参数用 `--device iphone`。
**路由器：** 在 OpenWrt 上运行 `tcpdump -i br-lan -w /tmp/lan.pcap` 一段时间，把文件拷出来后运行
`python veil_profiler.py capture --device router --mode baseline --read lan.pcap`，然后删除该 pcap（它包含完整数据包）。

## 第 2 步 —— 代理样本（开启代理），1–2 小时

开启代理，按平时习惯使用（浏览网页、看 YouTube）：

```bash
python veil_profiler.py capture --device mac --mode proxied --server www.example.com --hours 2 -i en0
```

## 第 3 步 —— 生成画像

先从服务器取回当前配置，确保设备名一致：

```bash
ssh root@你的VPS veil profile show > current.json
python veil_fit.py --baseline "flows-*-baseline-*.jsonl" --proxied "flows-*-proxied-*.jsonl" \
                   --current current.json --out profile.json --report profile-report.md
```

阅读 `profile-report.md`：每项改动都附有原因。

## 第 4 步 —— 应用画像

```bash
scp profile.json root@你的VPS:/root/
ssh root@你的VPS veil profile apply /root/profile.json
```

也可以在服务器上输入 `veil`，选择 **应用个性化画像**，然后粘贴 `profile.json` 的内容。

客户端会在下次订阅更新时自动获取，也可以手动刷新订阅。

## 第 5 步 —— 自检

```bash
python veil_selftest.py --baseline "flows-*-baseline-*.jsonl" --proxied "flows-*-proxied-*.jsonl"
```

每个特征会得到一个 AUC 值：约 0.5 表示与你平时的 HTTPS 流量无法区分，接近 1.0 表示非常显眼。
连接时长和单连接流量必然显眼——这是所有隧道的固有特征。你可以改进的是：

- **first_packets_mean / mean_pkt_up 显眼：** TLS 指纹不匹配；重复第 2–4 步（生成工具每次会尝试下一个预设）。
- **bytes_down 非常显眼：** 走代理的流量太多；检查国内流量和游戏下载是否保持直连。

每次改动后、以及每隔几个月，都重复第 2–5 步，因为浏览器版本和你的使用习惯都会变化。
自检只与你自己的流量比较；而防火墙看到的是全国的流量，所以自检分数好只是必要条件，不是充分条件。
