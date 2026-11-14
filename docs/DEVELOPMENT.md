# 开发与维护说明

## 目录与职责

```text
server_look/          产品源码
  app/                主窗口、服务器页面、应用常量
  ui/                 主题、表格、设置、帮助和通用界面
  transport/          SSH、认证、连接历史、目录长连接
  files/              本地文件、传输、拖拽、搜索、目录选择
  mapping/            映射配置、目录浏览、直传和中转
  localization/       中英文词条、界面翻译
  remote/             远程采集和搜索脚本（标准库）
  config/             界面偏好持久化
  paths.py            源码及打包环境的资源定位
tests/                自动回归测试
tools/                测试入口、人工冒烟脚本、图标生成
docs/                 中英文帮助及维护说明
assets/               图标资源
npu_client.pyw        Windows 客户端入口
npu_top.py            终端监控兼容入口
install.* / start.cmd 安装与启动入口
build_client.ps1      EXE 构建入口
```

## 依赖与运行边界

从项目根目录运行，使用 `server_look` 的绝对导入，不修改 `sys.path`。应用入口组装页面；界面调用连接和文件服务；后台线程不得操作 Tk 控件，结果通过队列交回主线程。远程脚本由客户端读取源码后送入服务器执行，不得依赖客户端包或第三方库。目录浏览继续复用每台服务器的长连接和缓存。

`paths.resource_root()` 统一处理源码与 PyInstaller 环境。新增远程脚本或静态资源时同步修改构建脚本的资源列表，不能按调用模块所在目录猜测资源路径。

## 常见维护入口

| 修改内容 | 入口 |
| --- | --- |
| 主导航、窗口复用 | `server_look/app/desktop_app.py` |
| 页面连接状态与任务刷新 | `server_look/app/server_page.py` |
| CPU、GPU/NPU、磁盘采集 | `server_look/remote/server_resources.py`、`npu_top.py` |
| 文件浏览与排序 | `server_look/ui/resource_views.py`、`table_sort.py` |
| 文件传输、拖拽及搜索 | `server_look/files/` |
| 映射配置与执行 | `server_look/mapping/` |
| 设置与实际按键录入 | `server_look/ui/settings_dialog.py`、`shortcut_capture.py` |
| 翻译与帮助 | `server_look/localization/`、`docs/HELP*.md` |

新增界面文字同步维护英文词条。路径、命令和服务器原始输出不应翻译。设置框禁用滚轮更改，快捷键通过实际按键录入。同一身份的已打开窗口应复用，关闭后允许重建。

## 验证与构建

在已安装依赖的环境中，从项目根目录执行：

```powershell
python -m tools.run_tests
python -m compileall -q server_look tests tools
.\build_client.ps1
# 正在使用旧 EXE 时，可指定独立输出目录
.\build_client.ps1 -OutputDirectory build/verification
```

测试入口将每个测试模块放到独立进程，避免 Tk 全局状态相互影响。Windows 跳过依赖 Linux `pwd` 的 `test_npu_top`；该模块需在 Linux 上验证。人工冒烟工具使用 `python -m tools.smoke_runtime` 等形式运行；涉及 SSH 的脚本需要自行提供测试环境，不连接个人服务器作为默认验证步骤。

启动源码仍使用 `start.cmd` 或 `python npu_client.pyw`。Linux 终端工具可使用整个项目的 `python npu_top.py`；单文件部署应复制 `server_look/remote/npu_top.py`。

发布只包含源码、测试、文档和资源。不要提交 `.venv`、缓存、构建输出、日志、连接历史、口令或密钥。整理目录不改变版本及用户配置位置；保留用户指定的历史 EXE 和 Release。
