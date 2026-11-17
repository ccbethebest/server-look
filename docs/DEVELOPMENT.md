## 2.19.0 统一 Python 脚本编辑器

`ui/context_python.py` 同时承载独立 Python 会话与 Shell 桥接的脚本编辑窗口：原生可撤销 Text 与只读 pyte 输出分离，Panedwindow 支持调整比例；本地文件、搜索与 stdin 单独处理。`command_panel.py` 为独立入口创建同一窗口并将输出路由过去，兼容原 execute_cell API。执行前校验只读、连接对象及 generation，避免向旧环境发送代码。

`transport/terminal.py:python_command` 短脚本保留原协议；长脚本使用随机变量暂存 Base64，每行约 600 字符，最后一次编译执行并清理暂存变量，避免 PTY canonical 输入行截断。解释器全局变量继续保留，不模拟完整 IDE 的进程重启语义。

回归覆盖两入口一致、结果不干扰光标/正文、多行与选区执行、本地保存/搜索/取消关闭、连接替换拒绝执行、大脚本 Unicode 与暂存清理。真实远端 Docker 仍需现场验证。

## 2.18.9 容器提示符下的 Vim 弹窗修复

- 修复终端直接输入 `vim 文件名` / `vi 文件名` 时，因为 Bash/Readline 的应用光标键模式被误认为全屏程序而跳过图形编辑桥接的问题。Docker 新 Shell 未继承桥接函数时也会恢复桥接。
- 使用文件浏览双击文本文件的同一个编辑器：多行编辑、搜索、复制粘贴、撤销、Ctrl+S 保存及未保存关闭确认均一致。容器文件继续按容器身份读取和保存。
- 同时修复该提示符模式下单独输入 `python` / `python3` 没有打开 Python 窗口的问题。原生全屏程序中的回车保持原样；`command vim` 仍可使用原生 Vim。
- 验证覆盖应用光标模式的真实 Tk 按键路径、图形编辑器调用及全屏程序保护。升级后新建 Shell 会话；当前机器没有可运行 Docker，尚未在用户实际容器中验证。

## 2.18.8 Docker 内文件编辑与 Python 窗口

- 在当前 Shell（含已进入的 Docker）输入单独的 `python` 或 `python3`，弹出独立多行 Python 窗口。直接在当前 Shell 启动解释器，继承其工作目录、环境变量和当前虚拟环境，连续执行保留变量；Ctrl+Enter 执行，支持原生撤销、复制、粘贴、删除。
- Python 输出区可输入 `input()` 的内容；“中断 Ctrl+C”中断执行，“退出 Python”或关闭窗口先中断再请求退出，收到退出确认后关闭窗口并返回原 Shell。程序若不响应中断，可关闭原 Shell 会话；该会话的 Python 窗口随之关闭。Python 运行期间，原 Shell 的输入转由弹窗接管。
- `python 脚本.py`、`python -m ...`、`python -c ...` 保持正常执行；`command python` 可使用原生终端 Python。命令输入栏和可视终端的单行输入都会恢复桥接。升级后新建 Shell 会话；工具栏“新建 Python”仍是初始服务器上的独立 Python 会话。

- 修复在 Docker 内执行 `vim 文件` 时，图形编辑器误去宿主机读取相同路径的问题。
- Shell 请求携带内核启动标识、挂载命名空间及 UID/GID；后台按命名空间唯一定位运行中容器，通过 `docker exec -i --user UID:GID` 在容器内读取和保存。每次保存再次核对身份，保留编码、换行及外部修改冲突检查。
- 编辑器状态栏显示 Docker 容器名称及 ID；宿主机和容器的同名文件可分别打开。容器退出、重启、身份改变或无法定位时中止操作，不回退到宿主机文件。
- 要求连接用户有 Docker 和 `/proc` 身份读取权限，容器内提供 `sh`、`readlink`、`id`、`cat` 和 Python 3（`python3` 或 `python`）。无法核对身份、切换用户或嵌套 SSH 不匹配时提示错误。不会创建不存在的文件。
- 验证包含容器协议分片、UID/GID 传递、实际 Python 编辑后台读写、保存冲突及图形编辑器上下文保留；当前 Windows 环境没有可用 Docker，尚未在用户服务器的真实容器内验证。

## 2.18.7 会话关闭与 vim 弹窗修复 / Session close and graphical editing

- 文本编辑窗口新增“查找 (Ctrl+F)”，按文字精确匹配，支持中文、上一个/下一个、Enter/Shift+Enter、F3/Shift+F3 和循环查找；Esc 关闭查找。搜索不修改文件内容。
- “关闭当前会话”立即移除当前 Shell/Python 标签，SSH 通道在后台释放，避免网络关闭阻塞整个界面；其他会话继续可用。
- `vim 文件名` / `vi 文件名` 从命令输入栏执行，或在终端直接输入单行后回车，自动恢复图形编辑桥接，打开与文件浏览相同的独立文本编辑器。Ctrl+S 保存、Ctrl+Z 撤销，未保存关闭仍询问保存/放弃/取消。
- 桥接使用 Shell 内置命令，不再要求远端 python3；初始化为单行，兼容已有 vi/vim 别名，按服务器当前目录解析中文、空格文件名。升级后请新建 Shell 会话。`command vim 文件名` 仍使用原生 Vim；sudo、容器和嵌套 SSH 不在当前服务器编辑桥接范围。
- Closing a session removes its tab immediately and releases SSH resources in a worker. Simple vi/vim commands restore the graphical editor bridge without remote Python. Existing text-file safety and unsaved-change prompts remain in effect. Open a new shell after upgrading.

- 关闭通道可能等待 Paramiko 写锁，`TerminalSession.close` 先设置 stop，再由后台线程释放资源；Tk 先忘记标签并销毁控件，停止消费该会话事件。
- `terminal_editor.editor_setup` 用单行 eval 避免已有别名干扰函数定义，printf 内置命令输出带会话令牌的 OSC 请求；解析器兼容旧 JSON 和新绝对路径消息。直接输入的命令仅在 ShellLine 与当前屏幕匹配时重建桥接，先 Ctrl+E/Ctrl+U 替换整行，避免光标位于中间时留下后缀。
- `test_session_editor_fix` 覆盖按钮关闭 Python、其他 Shell 保持可用、中文路径分片请求、光标居中回车、真实 Bash 重建失效函数和原生命令保留；`test_terminal_recovery` 覆盖 SSH 关闭阻塞时 UI 调用及时返回。另以真实 Bash 对比桥接前后的 cd、变量、管道、重定向、退出码及中文输出；真实目标 Linux 服务器仍需实际使用验收。

## 2.18.6 传输进度与右键操作 / Transfer progress and text actions

- 上传、下载、本地复制及拖拽传输先统计整批大小，显示“已传输 / 总计 / 百分比”和完成项数；文件夹包含子目录，多文件不再重置百分比。统计期间显示提示，仍可取消。仅旧版 OpenSSH 回退通道不提供实时字节数，会明确说明。
- Shell 无选区时单击右键直接粘贴；有选区时显示“复制 / 粘贴 / 删除选中文字”。Ctrl+C/V 继续可用；无选区的 Ctrl+C 仍中断远端命令。
- 终端当前新输入、尚未执行且没有换行的单行命令，可选中文字后按 Delete/Backspace 或右键删除，删除同步到远端。提示符和历史输出仅可复制；历史召回、自动补全后的未确认内容、全屏程序和跨行选区不开放选区删除。独立命令输入栏与 Python 多行编辑框支持右键复制、粘贴和删除。
- Batch transfers show cumulative bytes, total size and percentage. Right click pastes when no text is selected, otherwise opens a text menu. Selected deletion is sent to the remote shell only for verified, newly typed single-line input; output and prompts remain copyable. Command entries and Python editors support native local text actions.

- Verification: recursive SFTP upload/download and local-copy byte accounting, empty files, Tk clipboard/menu and selected deletion, read-only/history guards, Num Lock keyboard regressions and selected suffix deletion over a real local encrypted SSH channel. No target-server validation claim.

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
- 适用于支持 POSIX 函数的当前 SSH shell，无需远端 python3（2.18.7 起）；只处理单个非选项文件参数。不改远端配置文件；Python 会话、sudo、docker exec 命令本身、嵌套 SSH 及多文件/带参数命令保持原执行方式；进入 Docker 后的单文件 vi/vim 支持见 2.18.8。仅替换当前会话的 vi/vim 别名，不修改持久配置。
- 需要原生 Vim 时使用 `command vim 文件名`。新文件、可执行文件、二进制及超过 4 MiB 的文件不在图形编辑范围；沿用编辑器的只读、断连、外部修改与编码保护。
- 补齐应用方向键、F1–F12、修饰键、括号粘贴、备用屏幕恢复与中文光标位置。类似兼容性问题后续优先复用合适的图形窗口；当前并未自动重写其他终端程序。
- In a new POSIX SSH shell, `vim FILE` / `vi FILE` opens the existing graphical editor relative to the shell's current directory. Ctrl+S saves, Ctrl+Z undoes, and closing unsaved edits asks Save/Discard/Cancel. No Vim process starts; the prompt returns immediately. `command vim FILE` runs native Vim. Options, multiple files, sudo, containers, nested SSH and Python sessions retain normal execution. vi/vim aliases are replaced only in this shell session; persistent profiles remain unchanged. Existing text files only, up to 4 MiB, with the editor's existing permission, conflict and encoding checks. Application keys, function keys, bracketed paste, alternate-screen restoration and wide-character cursor positions have regression coverage; this does not assert full Xshell parity or target-server verification.

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
