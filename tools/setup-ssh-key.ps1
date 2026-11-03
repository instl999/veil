<#
.SYNOPSIS
  One-time SSH key setup for your veil VPS (Windows).
  一次性为 veil VPS 配置 SSH 密钥登录（Windows）。

.DESCRIPTION
  1. Asks for the server address, SSH port and user name.
  2. Creates a dedicated key (~/.ssh/veil_vps) if it does not exist yet.
  3. Copies the PUBLIC key to the server. You type the VPS password once,
     directly into ssh's own prompt - this script never reads, stores or
     prints the password.
  4. Adds a "veil-vps" entry to ~/.ssh/config and checks that key login works.

  1. 询问服务器地址、SSH 端口和用户名。
  2. 如果还没有，则创建专用密钥（~/.ssh/veil_vps）。
  3. 把公钥复制到服务器。你只需在 ssh 自己的提示中输入一次 VPS 密码——
     本脚本不会读取、保存或显示密码。
  4. 在 ~/.ssh/config 中添加 "veil-vps" 条目，并检查密钥登录是否成功。

.EXAMPLE
  Double-click tools\setup-ssh-key.cmd, or:
  powershell -ExecutionPolicy Bypass -File .\tools\setup-ssh-key.ps1
#>
param(
    [string]$HostName,
    [int]$Port = 0,
    [string]$User,
    [string]$Alias = 'veil-vps',
    [string]$KeyPath = (Join-Path $env:USERPROFILE '.ssh\veil_vps'),
    [string]$ConfigPath = (Join-Path $env:USERPROFILE '.ssh\config')
)
$ErrorActionPreference = 'Stop'

function Say([string]$En, [string]$Zh) {
    Write-Host "==> $En" -ForegroundColor Green
    if ($Zh) { Write-Host "    $Zh" -ForegroundColor DarkGray }
}

function Fail([string]$En, [string]$Zh) {
    Write-Host "xx  $En" -ForegroundColor Red
    if ($Zh) { Write-Host "    $Zh" -ForegroundColor Red }
    exit 1
}

function Test-ServerAddress([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $false }
    $ip = $null
    if ($Value -match ':') { return [System.Net.IPAddress]::TryParse($Value, [ref]$ip) }
    if ($Value -match '^\d{1,3}(\.\d{1,3}){3}$') { return [System.Net.IPAddress]::TryParse($Value, [ref]$ip) }
    return $Value -match '^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$'
}

function Read-Value([string]$En, [string]$Zh, [string]$Default, [scriptblock]$Valid) {
    while ($true) {
        $suffix = if ($Default) { " [$Default]" } else { '' }
        $value = Read-Host "$En / $Zh$suffix"
        if (-not $value) { $value = $Default }
        if ($value) { $value = $value.Trim() }
        if ($value -and (& $Valid $value)) { return $value }
        Write-Host '    Invalid input, please try again / 输入无效，请重试' -ForegroundColor Yellow
    }
}

function New-VeilKey([string]$Path) {
    if (Test-Path "$Path.pub") {
        Say "Reusing existing key $Path" "使用已有密钥 $Path"
        return
    }
    $dir = Split-Path $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    Say "Creating SSH key $Path" "正在创建 SSH 密钥 $Path"
    $v = $PSVersionTable.PSVersion
    # Windows PowerShell 5.1 drops empty arguments to native programs; '""' arrives as "".
    if ($v.Major -gt 7 -or ($v.Major -eq 7 -and $v.Minor -ge 3)) {
        & ssh-keygen -q -t ed25519 -C veil-vps -N '' -f $Path
    } else {
        & ssh-keygen -q -t ed25519 -C veil-vps -N '""' -f $Path
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path "$Path.pub")) {
        Fail 'ssh-keygen failed.' 'ssh-keygen 执行失败。'
    }
}

function Install-PublicKey([string]$Server, [int]$SshPort, [string]$LoginUser, [string]$PublicKey) {
    # Only the public key travels in the command; it is not secret.
    $remote = "umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && " +
              "(grep -qxF '$PublicKey' ~/.ssh/authorized_keys || echo '$PublicKey' >> ~/.ssh/authorized_keys) && " +
              "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo VEIL_KEY_OK"
    $out = & ssh -p $SshPort `
        -o StrictHostKeyChecking=accept-new `
        -o PubkeyAuthentication=no `
        -o PreferredAuthentications=keyboard-interactive,password `
        -o NumberOfPasswordPrompts=3 `
        -o ConnectTimeout=20 `
        "$LoginUser@$Server" $remote
    return ($out -match 'VEIL_KEY_OK')
}

function Set-SshConfigEntry([string]$Path, [string]$Name, [string]$Server, [int]$SshPort,
                            [string]$LoginUser, [string]$Key) {
    $keyForConfig = $Key -replace '\\', '/'
    $block = @(
        "Host $Name",
        "    HostName $Server",
        "    Port $SshPort",
        "    User $LoginUser",
        "    IdentityFile `"$keyForConfig`"",
        '    IdentitiesOnly yes',
        '    ServerAliveInterval 30'
    )
    $lines = @()
    if (Test-Path $Path) { $lines = [System.IO.File]::ReadAllLines($Path) }
    # Drop an earlier block for this alias: from its Host line to the next Host/Match line.
    $out = New-Object System.Collections.Generic.List[string]
    $skip = $false
    $hostLine = '^\s*Host\s+' + [regex]::Escape($Name) + '\s*$'
    foreach ($line in $lines) {
        if ($line -match '^\s*(Host|Match)\s') { $skip = ($line -match $hostLine) }
        if (-not $skip) { $out.Add($line) }
    }
    while ($out.Count -gt 0 -and $out[$out.Count - 1].Trim() -eq '') { $out.RemoveAt($out.Count - 1) }
    if ($out.Count -gt 0) { $out.Add('') }
    $out.AddRange([string[]]$block)
    $dir = Split-Path $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    # OpenSSH cannot parse a config file that starts with a UTF-8 BOM.
    [System.IO.File]::WriteAllText($Path, (($out -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}

# Allow dot-sourcing the functions (for tests) without running the setup.
if ($MyInvocation.InvocationName -eq '.') { return }

# ---------------------------------------------------------------- main
Write-Host ''
Write-Host '  veil - SSH key setup / SSH 密钥配置' -ForegroundColor Cyan
Write-Host '  Your password is only ever typed into ssh itself.' -ForegroundColor Cyan
Write-Host '  密码只会输入到 ssh 程序本身，本脚本不会接触密码。' -ForegroundColor Cyan
Write-Host ''

foreach ($tool in 'ssh', 'ssh-keygen') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Fail "$tool not found. Install it: Settings > Apps > Optional features > Add 'OpenSSH Client'." `
             "找不到 $tool。请安装：设置 > 应用 > 可选功能 > 添加“OpenSSH 客户端”。"
    }
}

if (-not $HostName) {
    $HostName = Read-Value 'Server IP address' '服务器 IP 地址' '' { param($v) Test-ServerAddress $v }
} elseif (-not (Test-ServerAddress $HostName)) {
    Fail "Invalid server address: $HostName" "服务器地址无效：$HostName"
}
if ($Port -eq 0) {
    $Port = [int](Read-Value 'SSH port' 'SSH 端口' '22' {
        param($v) ($v -match '^\d{1,5}$') -and ([int]$v -ge 1) -and ([int]$v -le 65535) })
}
if (-not $User) {
    $User = Read-Value 'Login user' '登录用户名' 'root' { param($v) $v -match '^[a-z_][a-z0-9_.-]{0,31}$' }
}

New-VeilKey $KeyPath
$publicKey = ([System.IO.File]::ReadAllText("$KeyPath.pub")).Trim()

Write-Host ''
Say "Connecting to $User@${HostName}:$Port to install the public key." "正在连接 $User@${HostName}:$Port 安装公钥。"
Say 'When asked, type the VPS password (nothing appears while typing) and press Enter.' `
    '出现提示时输入 VPS 密码（输入时屏幕不显示任何字符），然后按回车。'
Write-Host ''
if (-not (Install-PublicKey $HostName $Port $User $publicKey)) {
    Write-Host ''
    Write-Host '  Common causes / 常见原因：' -ForegroundColor Yellow
    Write-Host '  - Wrong password, IP or port / 密码、IP 或端口错误'
    Write-Host '  - The provider blocks password login for root: re-run and use the user name from'
    Write-Host '    the provider''s welcome email / 商家禁止 root 密码登录：重新运行并使用商家邮件中的用户名'
    Write-Host "  - The VPS was reinstalled: run  ssh-keygen -R $HostName  then try again"
    Write-Host "    VPS 重装过：先运行  ssh-keygen -R $HostName  再重试"
    Fail 'Could not install the key.' '公钥安装失败。'
}

Set-SshConfigEntry $ConfigPath $Alias $HostName $Port $User $KeyPath
Say "Added '$Alias' to $ConfigPath" "已将 '$Alias' 添加到 $ConfigPath"

$check = & ssh -o BatchMode=yes -o ConnectTimeout=20 $Alias 'echo VEIL_OK; . /etc/os-release 2>/dev/null; echo "$PRETTY_NAME"; uname -r'
if (-not ($check -match 'VEIL_OK')) {
    Fail "Key login test failed. Try: ssh -v $Alias" "密钥登录测试失败。可运行：ssh -v $Alias 查看详情"
}

Write-Host ''
Say 'Key login works. Server:' '密钥登录成功。服务器信息：'
$check | Where-Object { $_ -ne 'VEIL_OK' } | ForEach-Object { Write-Host "    $_" }
Write-Host ''
Write-Host "  Now tell Claude: ssh $Alias works" -ForegroundColor Cyan
Write-Host "  现在告诉 Claude：ssh $Alias 已可用" -ForegroundColor Cyan
Write-Host ''
Write-Host '  Password login stays ON for now; it will be turned off after veil is installed.' -ForegroundColor DarkGray
Write-Host '  密码登录暂时保持开启，安装 veil 之后再关闭。' -ForegroundColor DarkGray
