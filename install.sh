#!/usr/bin/env bash
# veil installer, for a git checkout:  sudo bash install.sh   (same options as veil-install.sh)
# veil 安装脚本（git 克隆方式）：sudo bash install.sh（参数与 veil-install.sh 相同）
exec bash "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/server/install.sh" "$@"
