# 开发与维护说明

## 2.18.1 SSH 脚本换行修复 / SSH line-ending fix

- OpenSSH 子进程的 shell 脚本必须使用 UTF-8 字节输入，再手动解码输出，避免 Windows 文本管道将 LF 转为 CRLF；Paramiko 字节传输不受此问题影响。
- `test_openssh_receives_lf_script_despite_windows_text_translation` 用真实子进程读取原始 stdin，拒绝 CR，并验证 stderr 登录横幅不影响成功的状态结果。
- Send shell scripts to OpenSSH as UTF-8 bytes and decode responses explicitly. Windows text-mode pipes otherwise convert LF to CRLF. The regression uses a real subprocess to reject CR bytes and tolerate a login banner on stderr.

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

### 文件浏览布局与进度
`ui/resource_views.py` 管理服务器侧列表及双栏容器；`files/local_files.py` 管理本地导航、元数据列和紧凑工具栏。两侧复用滚动列表创建和三态排序；不再重复显示服务器目录树。
`Transfer(progress=callback)` 发出完成顶层项数和总项数；SFTP 回调另含当前文件的字节数。回调只写队列，`LocalFiles.poll` 在主线程更新界面与耗时。系统 SFTP 不提供字节百分比，不推测该值。`tests/test_file_browser.py` 覆盖元数据、根目录及项数进度。

## 2.17.0 维护补充

- `ui/command_panel.py` 管理终端视图、pyte 屏幕与 Python 编辑区；`transport/terminal.py` 在线程内收发 SSH 通道，使用有界队列向 Tk 主线程传递事件。断线/只读切换关闭通道。
- `transport/ssh_keys.py` 管理本地密钥和追加公钥；不上传私钥，拒绝覆盖和远端密钥路径符号链接。
- `ui/scaling.py` 缓存原始布局尺寸，避免多次缩放累积；主题使用 Tk 全局缩放处理字体。
- `task_details` 是按需只读查询；`kill_npu` 仅接收确认的 PID/启动时间集合，服务端再次核验实时 NPU 占用，通过 pidfd 发送信号。
- 新增终端、缩放、密钥和 NPU 批量终止回归测试。真实 SSH/PTTY、权限及 NPU 驱动行为需在目标 Linux 服务器补充验收。


## 2.18.0 文本编辑

- `ui/text_editor.py`：独立窗口、编辑快捷键、未保存确认；后台线程通过队列返回结果，Tk 主线程轮询。EditorManager 纳入页面/程序关闭流程。
- `remote/file_editor.py`：本地与远端复用的文件验证、编码/换行、摘要冲突检查；通过既有 Connection.request 的 edit_file 分派在服务器执行，PyInstaller 必须包含此源文件。
- `ui/theme.py`：自定义勾形指示器复用 ttk Checkbutton 的 selected/disabled 状态与键盘行为。
- `tests/test_file_editor.py` 验证编码往返、拒绝执行文件/二进制/超限文件、SSH 请求脚本、保存冲突、关闭确认和勾选布尔状态；`test_terminal.py` 验证关闭 Python 标签。

English: Text editing runs I/O in workers and UI changes on Tk's main thread. Local and SSH edits share bounded text validation and digest-based conflict protection. All page/application close paths consult open editors. Release builds must bundle remote/file_editor.py. Windows tests exercise file safety, editor lifecycle, checkbox semantics and Python session closure; Linux executable-bit checks also run on Linux.

密钥流程：`check_key` 只读查询，Tk 主线程确认后 `configure_key` 加锁追加；队列携带连接对象及 generation，连接变化/只读阻止后续写入。`tests/test_ssh_keys.py` 覆盖已配对、否/是、路径报告、连接失效、带选项条目和注释误匹配。

English: Key detection never changes remote files. Installation needs UI confirmation and rechecks duplicates under a lock. Worker results retain connection identity and generation; stale results cannot install keys. Key tests cover consent, reuse, key locations and authorized_keys parsing.
