# 群晖数据库自动备份套件（开发版）

Copyright © 2026 AWA · [www.akkdiy.cn](https://www.akkdiy.cn)。源码保留所有权利，使用条款见 [LICENSE](LICENSE)，免责声明见 [DISCLAIMER.md](DISCLAIMER.md)。

本项目是 DSM 7 的套件源码起点，目标是把 NAS 本机 MariaDB 10 的数据库定时备份到用户在 File Station 风格目录选择器中选定的位置。

## 安装和使用

当前构建版本为 `0.1.0-0025`，目标设备为 DS723+（R1000）和 DSM 7.4.1。安装前，在套件中心安装 Synology Python 3 和 MariaDB 10。下载仓库中的 [`DBBackup-x86_64-0.1.0-0025.spk`](dist/DBBackup-x86_64-0.1.0-0025.spk)，然后在 DSM「套件中心 → 手动安装」中选择该文件。

安装并启动后，以 DSM administrators 群组成员登录 DSM，打开「数据库自动备份」。首次设置 MariaDB 只读账号及密码并保存连接，页面会自动检测数据库和数据表；勾选要备份的数据库或表，选择备份目录，新增计划或立即备份。计划任务以套件系统账号 `DBBackup` 执行，因此还需要在共享文件夹权限中授予 `DBBackup` 对目标目录的写入权限。DSM 登录身份验证与数据库账号是两套独立认证。

此构建包的 SHA-256：

```text
a825cb23b2c51484e86e10bc38a7d7319c331ad41b8f2f0f6a10501616df5c28  DBBackup-x86_64-0.1.0-0025.spk
```

当前没有配置离线发布签名私钥，因此该 SPK 是未签名的开发构建。安装前请核对 SHA-256；正式发布时应另附维护者签名及校验清单。

## 源码公开声明和许可

本仓库公开项目源码，版权归 AWA 所有。当前 [LICENSE](LICENSE) 仅允许审阅和个人评估，并未授予复制、修改、再发布、再授权或商业使用权。因此目前属于源码公开项目，不代表采用了 OSI 批准的开源许可证，也不应宣称可以自由分发或修改。需要按开源许可证发布时，维护者必须先明确选择许可证并更新授权文本。

使用前请阅读[免责声明](DISCLAIMER.md)。

正式发布时可用 `release/sign-spk.sh` 从离线 Ed25519 私钥生成 SPK 签名和 SHA-256 清单；用户可用 `release/verify-spk.sh` 检查。私钥不应放入本仓库或 GitHub。

## 已实现的设计

- 数据库连接使用 MariaDB 命令行客户端；主机、端口和 socket 自动探测，不要求手动填写数据库名或表名。
- 每个 DSM 登录用户单独保存数据库连接账号、备份任务和运行记录。数据库与表通过 `SHOW DATABASES`、`SHOW TABLES` 自动发现。
- 目录选择器通过 DSM File Station Web API 浏览当前登录用户可写的共享目录和子目录。
- 页面和每个 CGI API 请求都调用 DSM `authenticate.cgi` 校验会话；未登录时返回 401。创建、删除、立即运行等更改操作只接受同源 POST，任务操作校验任务所有者。
- Python 配置和状态文件放在套件私有 `var/` 目录；数据库密码不进入命令行参数或日志。备份先写临时文件，成功后原子改名。
- 每日自定义时间、每周自定义星期和时间、分钟/小时自定义间隔、开机后延迟分钟数、立即运行、启用/停用任务均包含在界面中。可立即备份临时选择的一项或多项数据库/数据表，不必先建立计划。
- MariaDB 密码用 OpenSSL AES-256-CBC 与 PBKDF2 加密，另用 HMAC-SHA256 校验密文；密钥和状态文件仅套件账号可读（0600/0700）。这属于 NAS 本机文件权限下的静态加密，不抵御 root、套件账号失陷或拥有 NAS 管理权的人。

## 当前支持范围与限制

- 目标为 DSM 7.0 及以上、Python 3 套件和 Synology MariaDB 10。当前代码不提供 PostgreSQL、容器内数据库或远程数据库连接器。
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

安装前请安装 Synology Python 3、MariaDB 10，并确认 NAS 上有 `mariadb`/`mysql`、`mariadb-dump`/`mysqldump` 与 `openssl`。首次使用时以 DSM administrators 成员身份打开套件，并给套件系统账号 `DBBackup` 授予目标共享目录的写权限。

## 安全核查重点

在 NAS 完成验证前，不应把本开发版暴露到公网或作为已验证安全的备份产品使用。至少要在目标 DSM 版本检查：CGI 是否由 DSM 正确执行、`conf/privilege` 是否将 CGI 启动器设置为 `DBBackup` 所有且仅可执行、`authenticate.cgi` 是否能读取原始请求会话、File Station 返回的 `real_path` 是否与用户可写权限一致、共享目录 ACL 是否阻止套件账号写入未授权目录，以及 MariaDB 客户端对所用账号授权的实际行为。

源码会保留版权标记。源码公开后，技术上无法阻止别人修改他们自己的副本；请勿把“加密源码”当成防修改方案。正式发布到 GitHub 前，应由维护者用离线私钥签署 SPK，并在发布页附带签名和 SHA-256 校验值。本仓库目前未配置发布私钥或 SPK 验签流程。
