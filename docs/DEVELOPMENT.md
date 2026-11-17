## 2.18.5 Windows 终端直接输入修复 / Direct terminal typing

- 修复 Num Lock 开启时普通字符被误当成 Alt 快捷键的问题；Windows 使用 Tk 原生 Alt 掩码，Num Lock 不再改变字符、回车、方向键和功能键。
- 新建会话在终端显示后获取输入焦点；点击终端或“启用终端输入”可切回直接输入，并显示键盘焦点状态。后台会话不会抢占当前输入。
- 命令行页面继续暂停监控自动刷新，SSH 输出按实际收到的数据更新。
- Fixed Windows Num Lock being mistaken for Alt. Shell and Python terminals preserve plain typing and navigation with Num Lock enabled. A focus indicator and explicit activation button make direct input visible and recoverable.

- Root cause: Tk on Windows uses state bit 8 for Num Lock and 0x20000 for Alt; X11 keeps Mod1 (8) for Alt. See [Tk keyboard mapping](https://github.com/tcltk/tk/blob/core-8-6-branch/win/tkWinX.c) and [modifier constants](https://github.com/tcltk/tk/blob/core-8-6-branch/generic/tkInt.h).
- Regression coverage includes Windows native WM_CHAR messages with thread-local Num Lock state restored afterward, mapped notebook focus, modifier/navigation encoding, and a real local encrypted SSH channel executing pwd with Num Lock enabled. No target-server or full Xshell compatibility claim.

## 2.18.4 命令输入与刷新 / Command input and refresh

- `ServerPage.tick` 在命令行页面跳过监控 snapshot，其余页面维持原周期，手动刷新和已有请求的收尾不受影响；`CommandPanel.poll` 只消费 SSH 事件，收到输出才重绘终端。
- Shell 输入栏使用同一会话的发送队列；只有成功入队后才清空。连接中、结束、只读、队列满均显示原因，避免静默丢弃按键。Ctrl+Q 按钮发送标准 XON，不修改远端配置。
- `test_command_usability.py` 验证映射后的 Tk 按键、输入栏回车和自动刷新策略；`test_terminal_ssh_input.py` 使用本地 Paramiko 加密 SSH 通道与测试 Shell，验证 Tk 输入→队列→SSH→回显→终端、执行、中断和关闭。它不替代用户实际 Linux 服务器或原生 vim 的验收。
- Monitoring snapshots pause on the command page. SSH event consumption continues without periodic terminal redraws. Tests cover mapped Tk events and a real encrypted local SSH channel with a test shell; this does not claim validation against the user's Linux server or native vim.

## 2.18.3 命令行图形编辑 / Graphical editing from the shell

- 新建命令行后，输入 `vim 文件名` 或 `vi 文件名`，直接打开与文件浏览相同的独立文本编辑窗口；按命令行当前目录解析路径，支持空格与中文文件名。Ctrl+S 保存、Ctrl+Z 撤销，未保存关闭时询问保存/放弃/取消。
- 采用图形编辑替代启动 Vim，不会留下等待退出的 Vim 进程；终端立即返回提示符，关闭窗口后继续使用。重复打开同一文件会唤起已有窗口。
- 适用于支持 POSIX 函数的当前 SSH shell，远端需有 python3；只处理单个非选项文件参数。不改远端配置文件；Python 会话、sudo、docker exec、嵌套 SSH 及多文件/带参数命令保持原执行方式。仅替换当前会话的 vi/vim 别名，不修改持久配置。
- 需要原生 Vim 时使用 `command vim 文件名`。新文件、可执行文件、二进制及超过 4 MiB 的文件不在图形编辑范围；沿用编辑器的只读、断连、外部修改与编码保护。
- 补齐应用方向键、F1–F12、修饰键、括号粘贴、备用屏幕恢复与中文光标位置。类似兼容性问题后续优先复用合适的图形窗口；当前并未自动重写其他终端程序。
- In a new POSIX SSH shell with python3, `vim FILE` / `vi FILE` opens the existing graphical editor relative to the shell's current directory. Ctrl+S saves, Ctrl+Z undoes, and closing unsaved edits asks Save/Discard/Cancel. No Vim process starts; the prompt returns immediately. `command vim FILE` runs native Vim. Options, multiple files, sudo, containers, nested SSH and Python sessions retain normal execution. vi/vim aliases are replaced only in this shell session; persistent profiles remain unchanged. Existing text files only, up to 4 MiB, with the editor's existing permission, conflict and encoding checks. Application keys, function keys, bracketed paste, alternate-screen restoration and wide-character cursor positions have regression coverage; this does not assert full Xshell parity or target-server verification.

# 开发与维护说明

## 2.18.2 连接与终端修复 / Connection and terminal fixes

- Native OpenSSH reads both known-host files using quoted paths; detected key pairs are explicitly passed to OpenSSH and Paramiko terminal connections. Strict checking remains enabled.
- `transport/terminal_screen.py` handles xterm private cursor position reports unsupported by the base pyte handler. `CommandPanel` isolates failed sessions so one parser exception cannot stop every tab's refresh loop.
- Server-page Close delegates to the existing application tab lifecycle, including busy checks, unsaved editor confirmation and terminal cleanup.
- Regression coverage: native loopback SSH with app-only trust and a custom-named key under a path containing spaces; private cursor replies and continued output; parser failure isolation; closing the correct server page and cancelling for unsaved files.
- 本地真实 Vim 临时文件编辑、保存、退出及输出重放通过。用户实际服务器上的 Vim 与公钥登录尚需现场验证；不自动接受未知或变化的服务器指纹。
- 回归入口为每个模块使用临时 APPDATA，避免读取或改写个人设置。多 Tk 根窗口测试在主线程回收旧解释器，防止后续文件工作线程触发 Tcl 跨线程析构。
- Tests use temporary APPDATA per module. GUI fixtures collect retired Tcl interpreters on the owning thread before another file worker starts.

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
