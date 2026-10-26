#!/bin/bash
# Copyright (c) 2026 AWA <https://www.akkdiy.cn>. All rights reserved.
source /pkgscripts-ng/include/pkg_util.sh

package="DBBackup"
version="0.2.0-0002"
os_min_ver="7.0-40000"
displayname="数据库自动备份"
description="自动检测 MariaDB 数据库和数据表，支持备份本机与内网其他服务器的 MySQL / MariaDB，可定时、开机后备份并设置保留份数。"
arch="$(pkg_get_platform_family)"
maintainer="AWA (www.akkdiy.cn)"
maintainer_url="https://www.akkdiy.cn"
dsmuidir="ui"
dsmappname="SYNO.SDS.App.DBBackup.Instance"
startable="yes"

[ "$(caller)" != "0 NULL" ] && return 0
pkg_dump_info

