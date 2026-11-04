# 服务端跨平台验证记录

验证日期：2026-11-04。范围为服务端；本地烧录代理没有修改。

实现采用宿主机 Python API/Worker，以及 Linux Docker 编译容器。正式服务没有
被本次测试替换；远端测试使用临时目录、临时数据库和独立的测试容器。

| 环境 | Python | 服务端测试 | 真实 Docker 测试 |
| --- | --- | --- | --- |
| Windows AMD64 | 3.14.4 | 38 通过 | 2 跳过：本机没有 Docker |
| macOS，Apple M5 ARM64 | 3.14.6 | 38 通过 | 2 通过 |
| Ubuntu 24.04 ARM64 容器 | 3.12.3 | 38 通过 | 2 跳过：容器内没有 Docker 引擎 |

macOS 首轮完整测试包含 38 项服务端测试及 1 项 Docker 测试，39 项全部通过。
随后新增的 Docker 网关连通性测试单独执行通过；Ubuntu 的最终完整测试已经
包含这两项可选 Docker 测试。Windows 对新增 Docker 测试文件执行确认了跳过行为。

已覆盖：

- 实际 API/Worker 子进程启动、正常停止与再次启动，数据库迁移和 Worker 恢复逻辑。
- Worker 文件锁对第二个进程的排斥；取消/超时后清理子进程，包括父进程已退出的场景。
- 使用模拟 Docker 编译进程验证 ESP/LVGL 构建编排、真实 Python ZIP 打包及 API 契约。
- 数据目录迁移后读取日志、下载产物、发布和下载 OTA 固件。
- 旧 Windows/Linux 绝对路径转换的预览、备份、提交和重复执行。
- 中文、空格、逗号目录的真实 Docker bind mount；超时后确认容器已被移除。
- Docker 容器经 host-gateway 访问宿主机 HTTP 服务，验证 Caddy 上游连接方案。
- macOS Docker 环境诊断、Compose 配置解析以及 Caddy 2.11.4 实际配置验证。
- Ruff 检查、现有 JavaScript 契约/界面测试及语法检查、Python 3.10 语法检查。

Mac Docker 引擎为 Linux aarch64；测试中发现并修复了后台 PATH 缺少 Docker
凭据助手目录的问题。Ubuntu 验证安装通过可达的 Docker Desktop 内部代理完成，
没有修改用户的代理配置。容器访问宿主机回环代理端口的尝试失败，说明镜像拉取
与编译容器联网需要分别验证。

尚未覆盖：真实 ESP-IDF 固件/LVGL 工程编译、Windows 实际 Docker 引擎、三个
系统的后台服务注册/开机验收、公开域名 HTTPS 签发。systemd/launchd/任务计划
程序配置已生成并经过格式测试；没有在用户系统注册这些启动项。

CI 已配置 Ubuntu/macOS/Windows 与 Python 3.10/3.14 矩阵，并在 Ubuntu 增加
真实 Docker 检查。本地未触发远端 GitHub Actions，不将矩阵定义视作已通过记录。
当前测试依赖发出一条 Starlette 关于 TestClient/httpx 的弃用提示，测试结果通过。

安装、启动、代理、后台运行和旧数据迁移步骤见 [部署说明](server_deploy.md)。
