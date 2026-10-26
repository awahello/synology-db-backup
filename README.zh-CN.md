# 群晖数据库自动备份套件（开发版）

Copyright © 2026 AWA · [www.akkdiy.cn](https://www.akkdiy.cn)。源码保留所有权利，使用条款见 [LICENSE](LICENSE)，免责声明见 [DISCLAIMER.md](DISCLAIMER.md)。

本项目是 DSM 7 的套件源码起点，目标是把 NAS 本机 MariaDB 10、以及内网其他服务器上的 MySQL / MariaDB 数据库定时备份到用户在 File Station 风格目录选择器中选定的位置。

## 安装和使用

当前构建版本为 `0.2.0-0002`，目标设备为 DS723+（R1000）和 DSM 7.4.1。安装前，在套件中心安装 Synology Python 3 和 MariaDB 10。下载仓库中的 [`DBBackup-x86_64-0.2.0-0002.spk`](dist/DBBackup-x86_64-0.2.0-0002.spk)，然后在 DSM「套件中心 → 手动安装」中选择该文件。

安装并启动后，以 DSM administrators 群组成员登录 DSM，打开「数据库自动备份」。在「数据库数据源」里新增一个数据源：服务器地址留空即备份 NAS 本机 MariaDB；填写 IP/域名与端口即可备份内网其他服务器上的 MySQL / MariaDB。填好只读账号密码点「保存并连接」，连接成功后才保存，页面随即自动检测数据库和数据表；勾选要备份的数据库或表，选择备份目录，新增计划或立即备份。每个计划绑定一个数据源，可以建多个数据源、多个计划。计划任务以套件系统账号 `DBBackup` 执行，因此还需要在共享文件夹权限中授予 `DBBackup` 对目标目录的写入权限。DSM 登录身份验证与数据库账号是两套独立认证。

此构建包的 SHA-256：

```text
89e6e70dbcb434ec8756bcdebbb77457ce4604c5c0e53cdb9896bff7e1077a7f  DBBackup-x86_64-0.2.0-0002.spk
```

当前没有配置离线发布签名私钥，因此该 SPK 是未签名的开发构建。安装前请核对 SHA-256；正式发布时应另附维护者签名及校验清单。

## 源码公开声明和许可

本仓库公开项目源码，版权归 AWA 所有。当前 [LICENSE](LICENSE) 仅允许审阅和个人评估，并未授予复制、修改、再发布、再授权或商业使用权。因此目前属于源码公开项目，不代表采用了 OSI 批准的开源许可证，也不应宣称可以自由分发或修改。需要按开源许可证发布时，维护者必须先明确选择许可证并更新授权文本。

使用前请阅读[免责声明](DISCLAIMER.md)。

正式发布时可用 `release/sign-spk.sh` 从离线 Ed25519 私钥生成 SPK 签名和 SHA-256 清单；用户可用 `release/verify-spk.sh` 检查。私钥不应放入本仓库或 GitHub。

## 已实现的设计

- 数据库连接使用 MariaDB 命令行客户端。可保存多个「数据源」：服务器地址留空表示 NAS 本机（自动探测 3307/3306 端口与 socket），填写 IP 或域名与端口表示通过 TCP 直连内网其他服务器上的 MySQL / MariaDB。数据库名与表名仍由 `SHOW DATABASES`、`SHOW TABLES` 自动发现，不要求手动填写。
- 每个备份计划绑定一个数据源，任务记录里会显示该计划属于哪个数据源。删除仍被计划引用的数据源会被拒绝，避免计划指向已不存在的连接。从 0.1.0 升级时，旧的单连接配置会自动迁移成一条名为「本机 MariaDB」的数据源，旧计划随之绑定，无需重建。
- 每个 DSM 登录用户单独保存数据库连接账号、备份任务和运行记录。数据库与表通过 `SHOW DATABASES`、`SHOW TABLES` 自动发现。
- 目录选择器通过 DSM File Station Web API 浏览当前登录用户可写的共享目录和子目录。
- 页面和每个 CGI API 请求都调用 DSM `authenticate.cgi` 校验会话；未登录时返回 401。创建、删除、立即运行等更改操作只接受同源 POST，任务操作校验任务所有者。
- Python 配置和状态文件放在套件私有 `var/` 目录；数据库密码不进入命令行参数或日志。备份先写临时文件，成功后原子改名。
- 每日自定义时间、每周自定义星期和时间、分钟/小时自定义间隔、开机后延迟分钟数、立即运行、启用/停用任务均包含在界面中。可立即备份临时选择的一项或多项数据库/数据表，不必先建立计划。
- MariaDB 密码用 OpenSSL AES-256-CBC 与 PBKDF2 加密，另用 HMAC-SHA256 校验密文；密钥和状态文件仅套件账号可读（0600/0700）。这属于 NAS 本机文件权限下的静态加密，不抵御 root、套件账号失陷或拥有 NAS 管理权的人。

## 当前支持范围与限制

- 目标为 DSM 7.0 及以上、Python 3 套件和 Synology MariaDB 10。远程数据库通过 TCP 直连，不提供 SSH 隧道、PostgreSQL 或容器内数据库支持。
- 备份远程数据库同样调用 NAS 本地的 `mariadb-dump`/`mysqldump`，因此即使只备份远程库，也必须安装 MariaDB 10 或 11 套件（只需要它的客户端二进制，不必运行本机数据库实例）。远程账号需要 SELECT、SHOW VIEW、TRIGGER、EVENT、LOCK TABLES 权限；若因缺少 PROCESS/EVENT 等权限无法导出存储过程或事件，套件会自动降级为仅备份表结构与数据，并在任务结果中写明。远程是 MySQL 8 且账号使用 `caching_sha2_password` 时 MariaDB 客户端可能无法登录，需改为 `mysql_native_password`。
- 定时进程以低权限套件账号 `DBBackup` 运行。目录选择器使用当前 DSM 登录会话列出可写目录并检查写权限；后台任务另以 `DBBackup` 身份再次确认目录可写，所以目标共享目录也必须授予 `DBBackup` 写权限。DSM Web 登录用户与 POSIX 服务账号不是同一身份，后台任务不会自动切换成 DSM 用户身份。
- 备份文件默认仅 `DBBackup` 可读写（0600）。若要让登录用户在 File Station 中读取备份，目标目录的 NAS ACL 需要通过继承明确授予该用户读取权；不要用宽泛的共享组权限代替个人授权。
- 目录选择器在浏览器端使用 File Station 的登录会话；服务端仍会把目标限制为真实存在的 `/volumeX/共享目录/...` 目录。不同 DSM 版本和反向代理设置会影响 File Station API 和 CGI 环境，必须在目标 NAS 上验证。
- 数据库连接密码以加密密文保存在仅套件账号可读的 SQLite 文件中（目录权限 0700、文件权限 0600）。这保护它免受未授权 DSM/HTTP 用户读取，但不能防御 NAS root、套件账号失陷或 NAS 本机恶意管理员。
- 页面入口和 JSON API 用 setuid 小型 C 启动器切换到套件用户运行；敏感 CGI 不以 Web Station 的 `http` 账号直接操作套件数据。请用 Synology Package Toolkit 为目标 DSM/CPU 架构编译和打包。当前环境没有 Toolkit 或 NAS，不能在此产出可安装 SPK，也不能验证 NAS 侧 CGI/文件 ACL 行为。
- DSM 应用入口默认仅对 `administrators` 群组开放，后端 CGI 也会复核该群组成员身份；每个计划仍按 DSM 用户名隔离。它尚未提供可授权普通用户的自定义角色。

## 构建

针对 DS723+（R1000）与 DSM 7.4.1，使用 Synology 的 `pkgscripts-ng` `DSM7.4` 分支部署 R1000 构建环境，并将 `package/` 放入 Toolkit 的 `source/DBBackup/`。构建命令：

```sh
cd /toolkit
chmod +x source/DBBackup/SynoBuildConf/build source/DBBackup/SynoBuildConf/install source/DBBackup/INFO.sh source/DBBackup/scripts/start-stop-status
pkgscripts-ng/PkgCreate.py -p r1000 -c DBBackup
```

安装前请安装 Synology Python 3、MariaDB 10，并确认 NAS 上有 `mariadb`/`mysql`、`mariadb-dump`/`mysqldump` 与 `openssl`（备份远程库时这些客户端同样需要，只是不必启动本机数据库实例）。首次使用时以 DSM administrators 成员身份打开套件，并给套件系统账号 `DBBackup` 授予目标共享目录的写权限。

## 安全核查重点

在 NAS 完成验证前，不应把本开发版暴露到公网或作为已验证安全的备份产品使用。至少要在目标 DSM 版本检查：CGI 是否由 DSM 正确执行、`conf/privilege` 是否将 CGI 启动器设置为 `DBBackup` 所有且仅可执行、`authenticate.cgi` 是否能读取原始请求会话、File Station 返回的 `real_path` 是否与用户可写权限一致、共享目录 ACL 是否阻止套件账号写入未授权目录，以及 MariaDB 客户端对所用账号授权的实际行为。

源码会保留版权标记。源码公开后，技术上无法阻止别人修改他们自己的副本；请勿把“加密源码”当成防修改方案。正式发布到 GitHub 前，应由维护者用离线私钥签署 SPK，并在发布页附带签名和 SHA-256 校验值。本仓库目前未配置发布私钥或 SPK 验签流程。

## 更新日志

### 0.2.0-0002

- 新增「数据源」概念：除 NAS 本机 MariaDB 外，可备份内网其他服务器上的 MySQL / MariaDB，备份文件统一落在本 NAS 的共享目录。
- 数据源按 DSM 用户隔离，可新增、修改、删除；删除仍被计划引用的数据源会被拒绝。
- 从 0.1.0 升级自动迁移：旧的单连接配置变成「本机 MariaDB」数据源，旧计划自动绑定。
- 修复：`--connect-timeout` 是 `mysql`/`mariadb` 客户端专有选项，`mariadb-dump` 会报 `unknown variable 'connect-timeout'`，导致备份直接失败。现在该选项只用于连接探测与查询，dump 命令行不再携带。
- 远程账号缺少 PROCESS/EVENT 权限时，自动降级为不导出存储过程/事件的备份，而不是整次任务失败。

### 0.1.0-0025

- 首个公开版本：本机 MariaDB 数据库/数据表自动检测、定时与开机后备份、保留份数、目录选择器、DSM 会话校验与密码加密存储。
