# 开发与维护说明

## 源码快速安装入口

`install.cmd` 调用 `install.ps1`，检查 Python 3.12 与 Tk，创建项目内 `.venv`，按 `requirements.txt` 安装并验证依赖。`start.cmd` 只使用这个环境启动 GUI；依赖安装失败立即停止，不隐式修改全局 Python。`install.ps1 -Launch` 可安装后启动。EXE 构建继续复用 `build_client.ps1`，具体命令见 README。

发布源码时排除 `.venv`、`.build-deps`、构建输出、日志及所有本机连接配置；发布地址未确定前不要在安装脚本中写入假定的 GitHub 用户或仓库。

## 2.0 维护入口

项目根目录：`Tools-服务器看看`；产品名：`服务器看看`；发布程序：`dist/服务器看看-2.2.1.exe`。保留 `npu_client.pyw` 与 `npu_top.py` 文件名，兼容现有启动方式与服务器终端工具。

| 新增模块 | 职责 |
| --- | --- |
| `theme.py` | 统一颜色、字体、间距及 ttk 样式 |
| `server_resources.py` | Linux 硬件、挂载容量及单层目录读取；标准库实现 |
| `resource_views.py` | 硬件、磁盘、文件浏览页；目录树与缓存 |
| `directory_channel.py` | 每服务器独立 SSH 长连接、JSONL 请求、响应队列及超时清理 |
| `create_icon.py` | 通过 Pillow 重建机柜图标，仅开发时需要 Pillow |
| `assets/server.ico` | EXE、窗口及任务栏图标，多尺寸 16～256 像素 |
| `assets/server.png` | 图标源预览文件 |

监控快照仍经 `client_core.Connection.request` 发起一次性 SSH 请求，并将两个采集模块源码送入远程内存执行。文件浏览请求单独分流到 `DirectoryChannel`：首次启动 `python3 -u`，第一行传入资源模块源码，随后每行传路径 JSON，返回结果或错误 JSON。路径不拼接到 shell 命令，服务器不落盘、不安装代理。登录提示行不参与 JSON 协议解析。

每个 `ServerPage` 使用两个后台线程，目录读取不占用监控的 busy 状态。目录请求串行使用长连接，UI 读取结果队列；页面 generation 阻止断线前的结果回写。快速连续导航保留最新待处理路径，读取期间不阻塞 Tk 主线程。`ResourceViews` 使用 15 秒、32 项的 LRU 目录缓存，强制刷新绕过缓存；按需读取单层目录，最多 3000 项。增加文件浏览功能时沿用该通道，避免每次点击重新 SSH。

新增硬件字段：修改 `server_resources.hardware()`；新增存储字段：修改 `disks()` 及 `ResourceViews.render()`；新增界面样式：修改 `theme.py`。`server_resources.py` 作为源码资源打包，修改后必须重新构建 EXE。

验证与打包：

```powershell
python -m unittest test_client test_resources -v
python smoke_multiserver.py
python smoke_resources.py
python create_icon.py  # 仅重新绘制图标时需要 Pillow
.\build_client.ps1
```

`smoke_resources.py` 只读连接默认服务器，验证硬件/磁盘字段、目录连接进程复用，并输出热连接目录读取耗时。构建脚本包含两个远程源码和 assets 图标目录。源代码交付时包含 assets，排除私钥、构建依赖、缓存和旧 EXE。

## 1. 快速开始

项目包含 Windows Tkinter 桌面客户端和 Linux 昇腾服务器监控程序。运行时只使用 Python 标准库；Windows 打包额外使用 PyInstaller。桌面端调用系统 OpenSSH，沿用用户已有公钥和 known_hosts。

在本目录运行：

```powershell
python npu_client.pyw
python -m unittest test_client -v
python smoke_multiserver.py
.\build_client.ps1
```

前两项不需要访问服务器，第三项会只读连接默认的两台服务器，要求 SSH 已配置好。打包前需有 `.build-deps` 中的 PyInstaller 6.22.0；干净环境安装命令：

```powershell
python -m pip install --target .build-deps pyinstaller==6.22.0
```

服务器端使用 Python 3.9+，在 Linux 下运行：

```bash
python3 npu_top.py --once
python3 -m unittest test_npu_top -v
python3 smoke_runtime.py
```

Linux 单元测试包含创建临时测试进程并结束它们的验证，不针对业务任务。Windows 测试的任务操作均使用 mock。不要在 Windows 上直接执行 `unittest discover`：Linux 测试依赖 `pwd`、`/proc` 和 pidfd；无桌面的 Linux 环境也不适合运行 Tk 测试。

## 2. 文件职责

| 文件 | 职责 | 修改时机 |
| --- | --- | --- |
| `npu_client.pyw` | Windows 无控制台启动入口，只调用 `main()` | 更换启动方式 |
| `desktop_app.py` | `MultiServerApp` 主窗口；添加、切换、关闭服务器页面及连接全部页面 | 增加窗口级操作或服务器管理 |
| `server_page.py` | `ServerPage` 单服务器视图、后台请求调度、快照渲染、选择及操作确认 | 修改页面、显示字段或页面交互 |
| `client_core.py` | SSH 参数校验、远程请求协议、打包资源读取、任务身份匹配 | 修改连接、通信或远程动作 |
| `settings.py` | 版本、默认服务器、刷新和请求超时 | 修改客户端默认值 |
| `npu_top.py` | Linux 采集、进程身份校验、安全发送信号、终端交互与 CLI | 修改采集、NPU 解析或进程控制 |
| `test_client.py` | 无网络客户端回归测试 | 桌面或通信改动 |
| `test_npu_top.py` | Linux 解析和进程安全测试 | 采集或信号逻辑改动 |
| `smoke_client.py` | 单服务器只读桌面验证，可传服务器地址 | 单机连接排错 |
| `smoke_multiserver.py` | 默认两台服务器同时只读验证 | 页面隔离和真实通信验证 |
| `smoke_runtime.py` | Linux 真实采集和伪终端只读交互验证 | 终端界面改动 |
| `build_client.ps1` | 从 `settings.APP_VERSION` 读取版本并打包 EXE | 修改构建资源或打包方式 |
| `启动客户端.cmd` | 使用本机 Python 启动源码 | 本地调试 |
| `README.md` | 使用说明 | 用户可见操作变化 |

`build/`、`dist/`、`.build-deps/`、`.pyinstaller-cache/`、`__pycache__/` 和 `*.spec` 是构建产物、依赖或缓存，已在 `.gitignore` 排除，不是需要维护的业务源码。旧版 EXE 保留用于回退。

保留 `npu_top.py` 单文件是有意设计：可直接复制到 Linux 运行，也可作为源码通过 SSH 在服务器内存中执行。若以后拆分此文件，必须同时修改远程加载和 PyInstaller 资源收集方式。

## 3. 调用链与线程规则

启动链：`npu_client.pyw → desktop_app.main → MultiServerApp → 每页一个 ServerPage`。

采集链：`ServerPage.refresh → submit → 工作线程 Connection.request('snapshot') → SSH → REMOTE → npu_top.collect → JSON → results 队列 → poll → render`。

操作链：`页面按钮或快捷键 → act → 检查只读/新鲜度/选择 → 显示含目标服务器的确认框 → submit → REMOTE → signal_tree 或 docker stop → 重新采集`。

每页独立拥有连接、线程池、结果队列、快照和任务选择。禁止将它们放进全局变量。工作线程只做 SSH 和队列写入，不能调用 Tk；`poll()` 在 Tk 主线程读取队列并更新界面。

| 页面状态 | 含义与约束 |
| --- | --- |
| `connection` | 当前 SSH 目标；断开后为 `None` |
| `data` | 最近成功的服务器快照 |
| `identity` | 选中任务的 `(pid, ticks)`，不能只保存 PID |
| `generation` | 每次断开/重连递增；旧代请求结果直接丢弃 |
| `busy` | 当前代存在未完成请求；避免重复刷新并禁用操作 |
| `fresh` | 当前快照有效；失败后即使旧数据仍可见，也禁用操作 |
| `readonly` | 本页只读开关；按钮状态和动作入口均检查 |
| `closed` | 页面销毁标记；停止注册后续定时回调 |

页面关闭会取消 Tk 的 poll/tick 定时器并关闭线程池；已运行的 SSH 请求可能持续到完成或超时。关闭页面不会向服务器发送结束任务或停止 Docker 的命令。

## 4. 通信协议与数据结构

`Connection.request(action, **values)` 每次建立短时 SSH 请求，把 `source`（随客户端携带的 `npu_top.py` 源码）、`action` 和参数以 JSON 写入远端 Python 标准输入。`REMOTE` 在内存模块中执行源码，再分派动作。远程标准输出必须是一个 JSON 值；调试输出应写标准错误，避免破坏解析。

| 动作 | 参数 | 返回 |
| --- | --- | --- |
| `snapshot` | 无 | 快照对象 |
| `term` | `pid`、`ticks` | `{ "message": "..." }`；SIGTERM |
| `kill` | `pid`、`ticks` | `{ "message": "..." }`；SIGKILL |
| `stop` | `cid`，完整 64 位十六进制容器 ID | `{ "message": "..." }`；Docker 停止输出 |

非零 SSH 退出码转为 `RuntimeError`，页面显示错误；请求超时由 `SSH_REQUEST_TIMEOUT_SECONDS` 控制。没有长期驻留的远端服务，也不把采集代码安装到服务器磁盘。

| 快照字段 | 类型/内容 |
| --- | --- |
| `host`、`time` | 主机名、服务器本地时区时间字符串 |
| `npu` | `npu-smi info` 原始输出 |
| `errors` | 采集警告字符串列表；部分采集失败时其他数据仍可返回 |
| `containers` | 完整容器 ID → 容器对象 |
| `processes` | 进程 ID → 进程对象；JSON 后键为字符串 |

进程对象：`pid`、`ppid`、`ticks`（Linux 启动时钟计数）、`user`、`command`、`cgroup`、`container`（完整 ID 或 `None`）、`started`；使用 NPU 时另有 `npu` 字典，例如 `{ "0:0": 2048 }`，键为卡/芯片，值为 MB。

容器对象：`id`、`name`、`image`、`started`、`created`、`pid`（入口 PID）、`command`、`restart`、`mounts`（挂载说明字符串列表）。

注意：`collect()` 在 Linux 返回全部宿主进程，进程字典键为整数；SSH 的 snapshot 分支仅保留占用 NPU 或属于已识别容器的进程，然后 JSON 序列化。桌面端再按 `all_tasks` 决定是否仅显示 NPU 任务。不要把“未占用 NPU”误判成“没有容器任务”。

## 5. 常见扩展怎么做

### 修改默认服务器、刷新或版本

修改 `settings.py`。版本同时用于窗口标题和 EXE 文件名，避免多处手动修改。刷新间隔是尝试间隔，不保证每 3 秒完成一次采集；本页已有请求时会跳过。默认服务器当前不持久化，用户新增页面仅在本次运行中有效。

### 添加显示字段

1. 在 `npu_top.collect()` 或 `read_process()` 增加数据来源，明确单位和缺失值。
2. 在 `server_page._build_views()` 增加列，在 `render()` 填入值；详情 JSON 会展示新增字段。
3. 若字段来自 NPU 输出，先补充不同输出格式的解析样例测试，再改解析函数。
4. 运行对应平台测试和只读 smoke，检查空闲 NPU、空容器以及部分采集失败。

### 添加一个服务器状态子页面

在 `ServerPage._build_views()` 中向 `self.tabs` 增加页面，在 `render()` 更新控件。当前运行任务和 Docker 分别使用索引 0、1，`buttons()`、`act()`、`show_details()` 依赖它们；在尾部添加页面可避免改变既有索引。若需要重排，先把这些判断一起改为具名页面引用并补测试。

### 添加一个远程操作

1. 为动作定义独立名称、参数、结果和权限影响。
2. 在 `client_core.REMOTE` 添加白名单分支并验证参数；调用参数列表形式的进程命令。
3. 在页面中添加按钮和 `act()` 分支；保留只读、busy、fresh、目标服务器确认和对象身份校验。
4. 增加参数非法、只读拦截、旧快照和页面隔离测试。不要通过真实业务任务验证破坏性动作。

### 支持新的 NPU 输出格式

先改 `parse_npu_processes()` 的样例测试；桌面“NPU 状态”展示原始输出，终端概览由 `telemetry_lines()` 压缩。分别验证两条展示路径，不要只根据单台服务器输出修改正则。

## 6. 必须保留的约束

- SSH 使用参数列表、BatchMode 和 StrictHostKeyChecking；不能为连接方便关闭主机密钥检查。
- 任务身份必须同时匹配 PID 与 ticks。进程发送信号通过 pidfd，保护 PID 1、监控自身和祖先进程；不退化为普通 `kill(pid)`。
- 结束任务仅影响操作瞬间的子树，不自动扩大到父任务、整个进程组或容器。
- 选中任务消失或身份改变后不能自动改选其他任务并允许操作。
- 页面失败、采集中或只读时禁用操作；动作入口仍须再次检查，不能只依赖按钮灰色。
- 不读取私钥内容、不打包凭据、不保存监控快照。命令行参数本身可能含敏感信息，日志和共享截图需注意。

## 7. 排错入口

| 现象 | 先检查 |
| --- | --- |
| 连接失败 | 用同一 Windows 用户执行 `ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@地址`；检查公钥、known_hosts、路由及端口 |
| SSH 成功但无快照 | 远端 `python3`、`npu-smi info`、`docker ps`；查看页面错误；远端 stdout 是否混入登录脚本输出 |
| NPU 任务为 0 但容器有进程 | 查看顶部数量，勾选“显示容器内全部进程”；可能是正常空闲 |
| 列表保留但按钮灰色 | 检查 busy、fresh、readonly 和选中 PID/ticks；查看最后采集是否失败 |
| 一个页面异常 | 检查该页连接和 generation；另一页的状态不应被修改 |
| 源码正常但 EXE 异常 | 检查 `build_client.ps1` 的 `--add-data npu_top.py:.` 与 `sys._MEIPASS` 资源路径；重新打包，不只复制单个改过的 `.py` |

## 8. 本次整理的验证

1.3 的单文件 GUI 已拆成主窗口与独立服务器页面；源码入口和启动脚本继续可用。1.4 集中配置与版本、移除测试对 `.pyw` 动态加载的依赖，真实连接脚本直接导入业务模块。Linux 单文件采集及信号实现仅增加职责注释。

交付验证包括 8 项 Windows 单元测试、双服务器只读连接验证及 PyInstaller 打包。后续每次改动按涉及平台运行上面的对应检查；构建成功不等于真实 SSH 功能已验证。

## 2.1 深蓝主题维护

配色集中在 `theme.py`，经典 Tk Text 使用 option database 单独设色。不要使用全局 `*Font` 覆盖字体；使用 Tk 命名字体作为默认值，再由 ttk 样式设定标题和导航字体。服务器外层 notebook 使用 `Server.TNotebook`，功能页沿用 `TNotebook`。显式固定 Tab 各状态的 font、padding、expand，避免 clam 默认选中扩展引起标签跳动。磁盘警告色位于 `resource_views.py`，危险操作使用 `Danger.TButton`。测试 `test_server_tab_dimensions_stay_fixed_when_selected` 实测两张服务器标签切换前后的像素边界。

## 2.2 文件管理维护入口

- `local_files.py`：本地列表、双击在 App 内进入目录、“打开窗口”按钮调用 Windows 文件资源管理器、新建目录、操作确认、后台线程事件队列与状态展示。
- `file_transfer.py`：SFTP 参数适配、路径引号、递归上传下载、子进程取消。使用现有 SSH 公钥与主机密钥检查，禁止将路径拼为 shell 命令；SFTP 批处理路径拒绝换行和空字符。
- `directory_channel.py`：同一 JSON 行协议增加 `action=mkdir,name=…`，只允许单层名称，由远程系统拒绝重复文件夹或权限不足。
- `ServerPage.poll()` 在 Tk 主线程消费文件管理事件；断开与关闭时取消传输，使用 generation 忽略旧连接结果。目录数据更新后清空缓存并重新读取。

验证：`python -m unittest test_file_transfer test_client test_resources`；`python smoke_transfer.py` 在两台默认服务器创建唯一命名的 `/tmp/server-kankan-test-…`，验证新建目录、递归双向传输、中文/空格/方括号和连接复用，然后仅删除该测试目录中的已知文件。传输是 SFTP 原生覆盖/合并，取消可能留下不完整文件；后续如增加原子覆盖或断点续传，应在 `file_transfer.py` 独立实现。

## 2.3 认证与多厂商设备维护

`password_transport.py` 管理严格 known_hosts 校验、密码认证、连接复用和独立 exec 通道；`DirectoryChannel` 通过可选 opener 共用现有 JSON 行协议。`Connection` 根据 auth_mode 选择传输。认证失败会在本连接中锁定错误，避免自动刷新反复尝试密码；用户重新连接才会重试。
`Transfer.run_connection` 在密码模式使用该 SSH transport 的独立 SFTP 通道，取消只关闭本次传输。不要将密码放入子进程参数或磁盘文件。
`npu_top.collect_accelerators` 分别探测两个厂商，返回原始/格式化状态、PID 到设备显存映射、硬件配置和错误。兼容字段 `npu` 代表加速卡状态/进程映射，不应因名称改动破坏协议。GPU 计算进程通过 UUID 关联设备；MIG 无法映射时保留 UUID。
新增依赖见 requirements.txt。构建环境安装到 `.build-deps`：`python -m pip install --target .build-deps -r requirements.txt`，再执行 build_client.ps1。源码启动也可通过 PYTHONPATH 指向该目录。
验证：`python -m unittest test_password test_gpu test_file_transfer test_client test_resources`。NVIDIA CSV 解析有模拟测试；实卡表现需在 NVIDIA Linux 服务器验证。不可把模拟测试写成真实 GPU 验证。

## 2.4 批量传输与 Windows 拖拽维护

- `ResourceViews.files` 和 `LocalFiles.files` 使用 extended 多选；`LocalFiles.start` 一次快照所有来源和目标，统一确认后交给 `Transfer.run_many_connection` 顺序执行。密码模式复用现有 SSH transport；公钥模式逐项使用系统 SFTP 子进程。取消/错误停止剩余项，已完成的项不回滚。
- `file_drag.RemoteDrag` 管理 TkDND 注册、多选鼠标绑定、首次下载等待窗口和临时文件缓存。TkDND 的 bindtag 必须排在自定义 ButtonPress 之前，以记录按下位置，同时保留原有多选。
- 主入口使用 `TkinterDnD.Tk`。源列表 `DragInitCmd` 返回仅 copy 的 DND_Files 本地路径列表；首次下载由工作线程执行，Tk 等待窗口通过 after 消费专用队列，完成后才能导出。等待中松开鼠标需再次拖动，缓存避免重复下载。无准备按钮。
- 本地 Drop 通过 Tcl splitlist 解析路径，按悬停目录选择目标，经确认使用可取消的 `Transfer.copy_local` 后台复制，拒绝符号链接/目录联接及复制到自身。Explorer 的复制由 Windows 接管，App 的取消按钮不能取消其复制。
- 拖拽临时文件必须保留到 Windows 完成复制之后；当前不自动删除，位置为 `%TEMP%\server-look-drag-*`。不要在 DragEnd 或 App 退出时直接删除，OLE 返回不代表 Explorer 已读完文件。失败/取消的缓存不会被导出。
- 新依赖 `tkinterdnd2==0.4.3`，构建必须带 `--collect-all tkinterdnd2`，包含 Tcl 与 Windows DLL。普通 Tk 测试可以跳过原生注册，`test_file_drag` 使用真实 TkinterDnD 根窗口检查加载和绑定。

验证命令：`python -m unittest test_file_drag test_batch_transfer test_file_transfer test_password_integration test_password test_gpu test_client test_resources`，共 39 项通过。覆盖首次下载、多项导出、缓存复用、中文/空格路径、本地落地和真实本地 SFTP 多项下载；跨进程鼠标拖到 Explorer 需手动验收。

平台说明：Windows 上直接执行 unittest discover 会因 Linux 专用 test_npu_top 导入 pwd 失败；该模块应在 Linux 运行。本次 Windows 相关 39 项测试通过，新版 EXE 也已成功启动并正常关闭；未把这些检查视为 Explorer 实际鼠标拖拽验收。

### 2.4.1 拖拽上传

`file_drag.RemoteDrag.begin_local` 导出本地多选路径，服务器列表注册 DND_Files 接收资源管理器或本地列表拖入。`upload` 校验连接、只读状态及源路径，按悬停目录行选择目标，再经确认调用 `Transfer.run_many_connection`；复用 LocalFiles.launch 的异步传输、取消与刷新机制。本地列表同步保留多选并优先运行 TkDND_Drag1 绑定。test_file_drag 覆盖本地多选导出、目标目录及只读拒绝；跨进程鼠标拖拽仍需 Windows 人工验收。

### 2.4.2 文件删除

LocalFiles.delete_selected 统一按钮、Delete 与上下文菜单入口，快照当前父目录和选中路径，默认拒绝确认，远程检查连接和只读状态。server_resources.delete_entries 接受父目录与单层名称列表，先验证整批名称再删除，不拼接 shell 命令。目录递归删除，选中的符号链接和 Windows junction 仅移除链接。DirectoryChannel 常驻代理新增 delete 动作，复用公钥/密码连接；完成或失败后由原事件队列刷新目录。删除不可取消，失败可能留下部分已完成项。test_file_delete 覆盖目录递归、整批路径校验、代理协议、UI取消和只读保护。

## 2.5 文件操作维护入口

`LocalFiles.operate(remote, action)` 统一路由右键与快捷键，先检查忙状态、连接、只读，再捕获源目录、选择和连接；剪贴板保存在本页，并用连接对象隔离重连。删除仍经过原有确认流程。新建保留原有路径。

`server_resources.file_operation(path, action, names, **options)` 为本地和远程共用的标准库实现，支持 copy/rename/compress/extract。新增动作需同步 `directory_channel.DIRECTORY_AGENT` 白名单、UI 菜单、只读门禁及测试。远程通过现有常驻 Python 进程执行，不为每次操作重新 SSH；耗时动作超时上限为 24 小时，并与浏览共用串行请求锁。

归档解压先写独立临时子目录，成功后改名为用户给定目录；错误清理临时目录。拒绝路径穿越、链接及已有目标。目录复制不追随链接。操作期间不要关闭连接，取消按钮只作用于上传下载。

`test_file_operations.py` 覆盖复制/重命名/归档往返、同名拒绝、递归复制拒绝、恶意归档、UI 粘贴导航、只读门禁、常驻代理协议；Windows 回归使用 README 对应测试模块，`test_npu_top` 为 Linux 端测试。


## 2.6.0 连接历史维护

`connection_history.py` 封装连接记录读写与 Windows DPAPI。配置使用用户级 APPDATA/ServerLook/connections.json，写入采用同目录临时文件与原子替换；损坏的配置报错，不静默覆盖。仅密码字段加密，使用当前用户 DPAPI，不能作为跨机器凭据备份。

`server_page.py` 在发起连接时捕获该次连接参数；收到当前连接代次的首个成功 snapshot 后保存。断开、关闭页面清除待保存引用，失败连接不写入记录。下拉菜单展开时重读配置，让不同服务器页共享历史。删除记录不影响当前连接，取消记住密码在下一次成功连接时移除旧密文。

`test_connection_history.py` 验证真实 DPAPI 往返和密文篡改、去重、密码移除、配置损坏保护、下拉填充，以及仅保存成功连接的原始参数。测试使用临时文件，不修改用户历史。


## 2.6.1 连接状态

连接栏显示尚未连接、连接中、连接成功、连接失败、连接异常、已断开。首次数据成功返回才视为连接成功；已成功连接后采集失败显示连接异常。失败原因在状态说明中显示摘要，点击“查看失败原因”显示完整 SSH/认证/超时等原始错误。自动刷新不把成功状态改成连接中，断开会清除旧错误。主机指纹确认及连接历史的成功保存规则保持有效。


## 2.7.0 外观维护

`theme.py` 的 PALETTES 集中维护黑、蓝、白三种配色。apply_theme 更新 ttk 样式、已有 Text/Menu/Treeview 和按钮图标，新建服务器页面后重用当前主题。appearance.json 独立保存界面偏好，损坏或未知主题回退至深海蓝；保存失败提示用户且保留本次界面选择。

`ui_icons.py` 提供 18px 网格折线图标和 button 工厂，使用 Tk PhotoImage 绘制，不依赖额外字体、图片文件或网络。按钮保留文字和键盘焦点，图像引用保存在控件上；切换主题时重新着色。新增按钮可通过 icon_for 映射到已有图标，或扩展 SHAPES。

`test_theme.py` 验证偏好存取、损坏配置回退、三种主题即时切换、已有文本和图标重绘，以及新服务器页继承当前主题。发布保留 2.6.1 EXE。

## 2.8.0 连接弹窗

`ServerPage._build_connection_dialog` 创建每页独立的非模态 Toplevel；隐藏而不销毁以保留表单，关闭服务器页时销毁弹窗。`show_connection_dialog` 复用并定位窗口；有效连接发起后自动隐藏。主工具栏继续显示连接状态、失败原因和远程只读开关。主题递归更新包含已隐藏弹窗，仅保留 PALETTES 中黑蓝白三套配置。test_theme 验证弹窗显示、隐藏、填写保留和三主题切换。
发布时保留 2.6.1 EXE。


## 2.9.0 导航、设置、搜索与帮助

`desktop_app.py` 管理四个全局入口、服务器菜单、主窗口布局和快捷键。`current_action` 只作用于当前服务器页；`configure_page` 把统一只读设置应用到既有与新增页面。快捷键只绑定主窗口，弹窗不继承执行。

`ui_preferences.py` 集中定义默认值、白名单校验及原子保存，路径为 `%APPDATA%/ServerLook/ui-settings.json`；配色继续复用 `theme.py` 的 appearance.json，兼容旧版。`settings_dialog.py` 只负责表单与提交，保存失败不关闭对话框。`theme.apply_theme` 从 root._serverlook_options 读取字号和按键尺寸，递归重绘既有控件与图标。新增设置需同步 DEFAULTS、validate、表单及测试。

`file_search.py` 使用标准库完成名称匹配，独立进程隔离正则运算。Windows 使用 spawn，入口 npu_client.pyw 必须保留 freeze_support；Linux 远程使用 fork。通过单向管道分批返回结果，父进程负责取消、15 秒期限及终止回收。上限为 1,000 结果和 100,000 条目，不跟随符号链接或目录联接。超时只保留已发送批次，部分统计为 None；跳过数代表读取失败，不代表结果完整。

`search_dialog.py` 用单线程执行器和 Queue 桥接 Tk，不在后台线程操作控件。远程通过 Connection.search 发送 JSON 参数并读取批次，client_core 把 file_search.py 附加到资源源码，由服务器独立进程执行；不把用户搜索条件拼接进 shell。远程停止关闭搜索通道，关闭窗口忽略后续结果；重新连接后不允许用旧搜索结果定位新服务器。搜索不占用持久目录通道。新增远程依赖需同步 build_client.ps1 的 add-data。

`help_dialog.py` 从打包资源读取 HELP.md，在文末附当前快捷键，离线可用。修改功能须同步 HELP.md 和 README。`test_search_settings.py` 覆盖匹配模式、大小写、递归、类别、上限、取消、超时、Windows junction 不追随、偏好保存／冲突校验、实时布局与只读和弹窗创建。

Windows 回归命令（先把 .build-deps 加入 PYTHONPATH）：
`python -m unittest test_search_settings test_theme test_connection_history test_file_operations test_file_delete test_file_drag test_batch_transfer test_file_transfer test_password_integration test_password test_gpu test_client test_resources`

打包：`powershell -ExecutionPolicy Bypass -File build_client.ps1`。发布时保留 2.8.0、2.6.1 和新版 exe；源码包不包含本机 APPDATA 或任何服务器凭据。


## 2.9.1 布局维护

主入口由 ui_icons.navigation_button 绘制彩色图标；Tooltip 管理悬停和键盘聚焦提示，并在离开、点击及销毁时清理。theme.py 统一定义胶囊按钮、内容切换按钮与隐藏标签样式。desktop_app.update_server_tabs 根据页面数量切换服务器标签样式。

ServerPage 保留 Notebook 管理页面，通过同一工具栏的 Radiobutton 切换；show_details 同步选中状态，只在任务或容器选中时显示详情，其他视图隐藏任务操作栏。不要恢复固定高度的空白详情区。

## 2.10.0 模块与扩展约定

代码优先可读性：一个模块承担一个职责，函数使用明确命名，避免嵌套条件表达式、重复分支和仅转存一次的无意义变量。新增能力先复用现有连接、后台执行和传输入口，不把网络操作放在 Tk 主线程。

| 模块 | 职责与扩展位置 |
| --- | --- |
| table_sort.py | 通用三态表头排序与数值／容量／自然文本排序；刷新填充后调用 refreshed |
| server_tabs.py | 固定选中尺寸的自绘服务器标签，空闲高亮；不管理 SSH |
| file_search.py | 标准库目录扫描、匹配、分批结果与上限；新增模式集中修改 MODES、matches_name 和说明 |
| remote_search.py | SSH 流式搜索生命周期、取消、超时与批次回调；不操作 GUI |
| search_dialog.py | 搜索表单和 Queue 到 Tk 的结果展示 |
| directory_mapping.py | 配置存取、SFTP 通道、缺失文件复制、安全路径与取消；不操作 GUI |
| mapping_dialog.py | 映射配置和启动，复用 LocalFiles 后台任务与状态 |
| file_drag.py | 识别 App 内落点直接传输，App 外保留原生拖拽导出 |
| ui_preferences.py / local_files.py | 文件快捷键定义与焦点内绑定 |
| desktop_app.py / server_page.py | 跨服务器入口与单页面状态，generation 丢弃旧连接结果 |

映射使用独占创建（本地 xb、远程 wx），已有文件不覆盖；新文件中断时尝试清理，已完成文件保留。拒绝符号链接、Windows junction、越界选择和远程大小写重名。公钥通过系统 OpenSSH SFTP 子系统，密码复用已验证的 Paramiko 会话；不降低主机密钥校验。
搜索是名称扫描，尚无全盘索引，因此速度仍取决于目录大小、磁盘和权限；结果上限与超时需在界面和帮助中保持一致。

回归：Windows 设置 PYTHONPATH=.build-deps 后运行上方回归命令，并加入 test_mapping_sort；test_npu_top 依赖 Linux 的 pwd、/proc 和信号接口，需在 Linux 单独运行。test_mapping_sort.py 覆盖排序刷新、映射不覆盖／越界／链接／取消及搜索流；test_file_drag.py 验证 App 内直接目标路径；test_password_integration.py 使用本地 SSH/SFTP 服务验证真实协议。Windows 资源管理器实际鼠标拖放另需人工验收。
发布 2.10.0 时保留 2.6.1、2.8.0 和新版 exe，移除其余旧 exe；不打包本机连接记录或凭据。


## 2.11.0 更新

- 映射的服务器目录支持“选择”：双击进入、上一级、路径输入和刷新；复用服务器已有持久目录连接，窗口内缓存目录。
- 修复系统 OpenSSH 映射适配器缺少 get_name 导致的 SFTP 初始化错误。
- 搜索显示文件大小（字节）和修改时间；点击名称、大小或时间表头依次升序、降序、重置。结果分批到达时保留排序。
- 搜索默认不递归统计文件夹大小，显示“未统计”；勾选“统计文件夹总大小（较慢）”后计算内部普通文件字节合计，不跟随链接与 junction。权限受限或超过单目录 10 万项时标记“不完整”，整个搜索仍受 15 秒限制，超时返回已发送批次。此数值不含文件系统元数据，也不等于磁盘实际占用。
- “查空闲”提示未识别加速卡，表示无法确认设备和空闲状态，不表示服务器繁忙。修复昇腾服务器因 NVIDIA 硬件字典为空被误报的问题；仍无法识别时检查驱动、权限和 SSH 命令路径中的 npu-smi / nvidia-smi。当前识别昇腾 NPU 与 NVIDIA GPU。
- 运行任务增加父 PID、直接子 PID 和“任务关系”入口：展开祖先及后代树，双击定位任务；快照保留启动器祖先和任务后代，不扩展共享祖先的无关子进程。系统父子关系不代表程序内部业务依赖，权限不足或进程退出可能造成关系缺失。
- 新模块 remote_directory_dialog.py 负责异步目录选择；task_relations.py 负责关系快照和树展示。相关回归见 test_latest_updates.py。
- 发布保留 2.6.1、2.8.0 与 2.11.0 exe，不包含个人连接记录或密码。


## 2.11.1 映射覆盖选项

映射窗口新增“覆盖已有文件”，可随配置保存；旧配置默认关闭。关闭时递归补充目标中缺少的文件；开启时递归复制源目录所有文件，覆盖同路径普通文件。两种方式均合并文件夹、保留目标独有文件，适用于本地上传、服务器下载及右键选中项映射。勾选后直接点击一键映射立即生效；更新配置后可长期保存。

覆盖先写入目标目录中的临时文件，再替换原文件；传输或替换失败时保留原文件。上传覆盖需要服务器 SFTP 支持 OpenSSH posix-rename 扩展，不支持时显示失败，不删除原文件。同名文件与文件夹的类型冲突、符号链接继续跳过。覆盖会替换已有内容，请确认源目录与方向。


## 2.11.2 一键连接历史服务器

点击顶部“服务器”图标 → “一键连接历史所有服务器”，自动读取历史地址、账号、端口与登录方式，为各服务器建立连接。复用已有匹配页面，跳过已连接、正在连接及繁忙的匹配页面；没有匹配页面时使用空白页面或新建页面。每个页面显示连接中、成功或失败及原因。重复点击不会重连成功或正在连接的服务器。

密码登录使用当前 Windows 用户加密保存的密码；未保存密码或无法解密时，该页面提示补填密码，其他服务器继续连接。原“连接全部页面”仍只连接已打开页面。实现入口为 desktop_app.MultiServerApp.connect_history，凭据填充复用 server_page.ServerPage.apply_history，SSH 仍由各页面现有后台任务处理。


## 2.11.3 查空闲状态提示

点击“查空闲”查询已连接服务器：全部卡空闲显示绿色，部分卡使用显示黄色，全部卡使用显示红色。按物理卡统计，同一卡上的多个进程或 NPU 芯片不重复计数；状态栏显示已使用卡数/总卡数。点击服务器标签（包括当前标签）恢复原色。查询失败或无法关联物理卡时显示原因，不标色。


## 2.11.4 加速卡识别修复

兼容不含字母后缀的 NPU 型号及 Ascend 950 不含 Chip 列的进程表，避免漏报设备或将有任务的卡误判为空闲。SSH 环境 PATH 缺少驱动命令时尝试标准安装路径；命令不可用仍显示查询失败，不冒充空闲。


## 2.11.5 批量查空闲与标签悬停

在任意页面点击“查空闲”，一键查询所有已连接服务器，无需逐页操作；未连接的服务器先连接后再查。鼠标悬停服务器标签，显示最近一次查询的“已用卡数/总卡数”，查询中及失败时显示相应状态。点击标签清除颜色后仍保留悬停信息；断开连接清除历史卡数。ServerTabs 复用 Tooltip 展示提示，occupancy_details 与颜色标记分别保存。


## 2.12.0 多端映射模块

- mapping_dialog.py：端点列表、来源/目标选择、已连接服务器目录浏览、本机中转文件夹选择；启动前验证只读状态并快照连接对象，复用 LocalFiles 后台传输与取消入口。
- multi_mapping.py：Location 封装本机/SFTP 文件操作；MultiMapping 复用 DirectoryMapping 的连接通道，实现递归合并、多目标、独占暂存文件和提交。只为本次来源/目标打开 SFTP，按服务器复用一次会话；取消为协作取消，保留通道用于清理，密码 SFTP 通道 IO 超时 30 秒，原生 OpenSSH 通道沿用系统 SSH 的连接保活机制。
- mapping_direct.py：源端 SSH 子进程直传，JSON 心跳和低速回退；不传本机凭据。失败后中转使用新的暂存文件，避免退出中的直传进程写入同一文件。远端 Python 程序必须保持参数经 JSON/shlex 编码。
- 配置 locations=[{server,path}], source=索引, targets=[索引], relay=用户本机目录, direct=优先直传, minimum_mbps=低速阈值, overwrite=覆盖；server 继续使用现有 endpoint 键，local 代表本机。migrate_record 兼容旧配置，不保存任何认证信息。
- test_multi_mapping.py 覆盖多目标、覆盖/补齐、直传成功与回退、取消、空间不足及清理；test_mapping_dialog.py 使用真实 Tk 验证本机默认端点和中转目录选择保存。GUI 与 SSH 集成测试建议分进程执行，避免 Tk 对象在线程垃圾回收时影响测试。

搜索目录支持可视化选择：在搜索窗口选择“本地”或“当前服务器”，点击路径右侧“选择文件夹…”。本机使用系统文件夹选择窗口，远程复用 RemoteDirectoryDialog 和现有 SSH 目录通道，选定后回填搜索起始路径。

搜索目标下拉框支持本地和所有已打开的服务器页面（按账号、地址、端口区分）；选择服务器后，可可视化选择该服务器上的搜索目录。未连接的页面需先连接。双击结果会定位到搜索时所选服务器；页面关闭或连接变更后需重新搜索。

2.12.1：双击搜索结果切换到对应服务器文件浏览。文件夹进入该目录；文件进入所在目录并在目录加载后选中。搜索窗口暂时隐藏，点击搜索入口可恢复结果。映射配置的“参与目录数”表示配置中的目录位置数量，不是其内部文件或子目录数量。

2.12.2：映射入口简化为历史目录映射下拉框、新增映射和修改映射。仅新增或修改时展开编辑区，保存后自动收起；选择历史方案后可直接一键映射。


## 2.14.0 独立映射行与双栏浏览

点击“新增映射”添加一行，表格展示映射方向、来源文件夹和目标文件夹。单击方向单元格选择本机或已连接服务器的组合；单击路径单元格可直接输入，点击其中的“…”可视化选目录。支持本机→服务器、服务器→本机、服务器→服务器，也可选择本机两个目录。右键“保存映射”写入历史；“取消当前映射”移除当前行，保留历史与实际文件。

单击选中一行，点击“一键映射”递归映射来源目录全部内容。双击该行打开来源与目标双栏目录：双击文件夹进入，左侧 Ctrl / Shift 多选或 Ctrl+A 全选，右键“映射选中项”传输所选文件 / 文件夹；也可右键映射当前目录全部内容。子目录保留相对来源根目录的路径，目标浏览位置不会改变传输目的地。表头支持名称、大小、修改时间的升序、降序、重置排序。

“历史映射查看”展示全部记录，可选用、单选 / 多选删除、全部删除；只删除配置。顶部快捷历史仅列出对应服务器均已连接的记录。旧多目标配置自动拆成一条条来源→目标映射，保存后继续使用。

选中行后，下方设置该条映射的本机中转目录、覆盖已有文件、优先直传、低速阈值。覆盖关闭时只补齐缺失文件；开启时覆盖同名普通文件，两者均保留目标独有文件。直传失败或连续 15 秒低速时询问是否本机中转，中转采用约 8 MiB 分块，不将全部文件先落到本机。传输速度在底部显示；需要改变已打开双栏窗口的映射路径或选项时，请关闭该双栏窗口，修改后重新双击打开。

实现分工：mapping_dialog.py 管理独立行、行内编辑、校验与传输队列；mapping_rows.py 将旧多目标配置转换为两端记录并保留稳定 id；mapping_history.py 只管理历史配置；mapping_browser.py 提供双栏异步浏览与选项快照。目录读取复用 connection.request 持久通道及每个面板缓存，后台线程不访问 Tk。文件映射继续调用 MultiMapping.run_many，selected 为空代表全部来源内容，非空为来源根目录内的绝对路径。新增模块不保存凭据。

test_mapping_rows 验证历史拆分与稳定 id；test_mapping_dialog 验证真实 Tk 行管理、可视化选目录、全量与多选映射分发、远程目录连接复用及缓存。真实跨服务器 SSH 直传仍需对应环境验收。


## 2.14.1 映射文件夹选择

映射列表下方始终显示“选择来源文件夹”和“选择目标文件夹”两个大按钮。先选中映射，再点击对应按钮，可视化选择本机或服务器文件夹；路径单元格仍可手动编辑。复用 MappingDialog.choose_folder，服务器目录继续使用已有持久连接和缓存。

双击映射进入双栏目录后，两侧均可输入绝对路径并回车，或点击“选择文件夹”修改映射根目录；本机侧可用磁盘下拉框快速切换盘符。成功读取后同步更新主列表，保存仍通过右键操作。普通双击进入子文件夹保持相对映射路径；切换根目录后，选中项按新根目录计算。
