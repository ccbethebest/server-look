## 2.18.3 命令行图形编辑 / Graphical editing from the shell

- 新建命令行后，输入 `vim 文件名` 或 `vi 文件名`，直接打开与文件浏览相同的独立文本编辑窗口；按命令行当前目录解析路径，支持空格与中文文件名。Ctrl+S 保存、Ctrl+Z 撤销，未保存关闭时询问保存/放弃/取消。
- 采用图形编辑替代启动 Vim，不会留下等待退出的 Vim 进程；终端立即返回提示符，关闭窗口后继续使用。重复打开同一文件会唤起已有窗口。
- 适用于支持 POSIX 函数的当前 SSH shell，远端需有 python3；只处理单个非选项文件参数。不改远端配置文件；Python 会话、sudo、docker exec、嵌套 SSH 及多文件/带参数命令保持原执行方式。仅替换当前会话的 vi/vim 别名，不修改持久配置。
- 需要原生 Vim 时使用 `command vim 文件名`。新文件、可执行文件、二进制及超过 4 MiB 的文件不在图形编辑范围；沿用编辑器的只读、断连、外部修改与编码保护。
- 补齐应用方向键、F1–F12、修饰键、括号粘贴、备用屏幕恢复与中文光标位置。类似兼容性问题后续优先复用合适的图形窗口；当前并未自动重写其他终端程序。
- In a new POSIX SSH shell with python3, `vim FILE` / `vi FILE` opens the existing graphical editor relative to the shell's current directory. Ctrl+S saves, Ctrl+Z undoes, and closing unsaved edits asks Save/Discard/Cancel. No Vim process starts; the prompt returns immediately. `command vim FILE` runs native Vim. Options, multiple files, sudo, containers, nested SSH and Python sessions retain normal execution. vi/vim aliases are replaced only in this shell session; persistent profiles remain unchanged. Existing text files only, up to 4 MiB, with the editor's existing permission, conflict and encoding checks. Application keys, function keys, bracketed paste, alternate-screen restoration and wide-character cursor positions have regression coverage; this does not assert full Xshell parity or target-server verification.

服务器看看 2.18.3 使用说明

2.18.2：连接、刷新、断开旁新增“关闭”，关闭当前服务器页；未保存编辑内容时仍询问保存/放弃/取消。命令行支持私有光标位置查询，并隔离单个会话的显示错误。

“命令行控制”通过 SSH 伪终端启动服务器端 Shell；命令、当前目录和环境变量均属于该服务器上的独立会话，权限与登录账号一致。可输入 `hostname`、`whoami`、`pwd` 核对。Python 页签启动服务器上的 `python3`，需要远端已安装；它不是本机 Python。终端显示兼容性仍与 Xshell 有差异，不能保证所有全屏交互程序完全一致。

Command tabs open remote shells over SSH PTYs. Commands, working directories, environment variables and account permissions belong to the remote session. Use hostname, whoami and pwd to check. Python tabs require python3 on the server. Terminal display compatibility may differ from Xshell for full-screen applications.

若公钥连接报 `No ED25519 host key is known ... strict checking`，表示服务器身份尚未获得信任，并非登录公钥被拒绝。先使用密码连接，核对并确认主机指纹，完成“公钥配置”，再切换为公钥连接。2.18.2 统一读取 `~/.ssh/known_hosts` 与 `~/.ssh/server_look_known_hosts`；生成密钥不会自动配置远端。指纹发生变化时仍会阻止连接，应先向管理员核实。顶部连接失败状态旁的“失败原因”可查看完整错误。

2.18.2: Close beside Disconnect closes the server tab with unsaved-file confirmation. Terminal private cursor queries are supported and display errors are isolated. An unknown host key error occurs before user authentication: connect with a password, verify and confirm the host fingerprint, configure the public key, then select key login. Both standard and app-confirmed known-host files are used. Changed host keys remain blocked. Generating a key alone does not install it remotely.

2.18.1 修复 Windows OpenSSH 公钥配置的换行兼容问题。若显示 `Authorized users only. All activities may be monitored and reported.`，这是服务器登录提示；`set: invalid option` 才是脚本执行错误，旧版本应更新至 2.18.1 后重试。

2.18.1 fixes line-ending compatibility for public-key pairing via Windows OpenSSH. The authorized-users message is a server login banner; `set: invalid option` indicates script failure. Update older versions to 2.18.1 and retry.


2.17.0 新功能
设置最前面的“全局大小修正（%）”支持 50%～200%，统一调整字体、图标、按钮间距和表格布局，并记住选择。
“命令行控制”可新建多个交互 SSH 命令行和 Python 会话；Python 编辑区支持多行代码，Ctrl+Enter 执行，同一会话保留变量。终端 Ctrl+C 中断，Ctrl+Shift+C/V 复制粘贴。断开服务器会关闭会话。只读模式不能打开交互会话或配置远端公钥。
密钥检测检查本机 ~/.ssh 下成对的公钥和私钥，并报告两者完整路径；已有密钥时，密钥生成提示“已拥有密钥，无需生成”并显示位置，不覆盖已有文件。公钥配置先只读检测当前登录用户的 ~/.ssh/authorized_keys：已有同一公钥则提示“已配对”；未添加则询问“是否添加公钥”，选“是”才在文件末尾追加，选“否”不改动服务器。追加前加锁再次检查，忽略注释差异，兼容带选项的密钥条目，避免重复；私钥不上传。配置其他账号需要先以该账号登录；本账号通常不需要 root 权限。
任务下方显示采集到的启动命令，不等同于启动脚本正文。“读取来源详情”按需查询工作目录、可执行文件、参数中的脚本/数据路径线索、打开的文件和父进程链。SSH 来源仅在进程环境中可追溯时显示地址；无法保证识别实际操作者或其电脑名称。容器归属随任务信息显示。读取结果受登录账号权限限制。
“结束全部 NPU 任务”仅覆盖当前快照中占用昇腾 NPU 的进程。必须在列出服务器和进程的提示中确认，默认取消。执行时重新核验 NPU 占用、PID 和启动时间，跳过新任务、退出进程、PID 复用及受保护的监控进程；权限不足会报告。使用 SIGKILL，未保存结果会丢失；Docker/systemd 等管理的服务可能自动重启，按钮不停止整个容器或修改重启策略。需要服务器 Python/Linux 支持 pidfd，避免误杀。NVIDIA GPU 任务不在此按钮范围内。

设置操作（新版）
设置中可选择简体中文或 English，保存后立即应用并记住。恢复默认设置会恢复语言、配色、字号、布局、只读选项和快捷键，不清除连接历史和映射记录。服务器原始输出、文件名、路径和用户数据保持原文。
快捷键：点击对应按钮，再按下实际按键或组合键；Esc 取消本次录入，“清除”禁用该快捷键。字号使用 − / + 按钮。配色、布局等点击选择，滚轮不会更改设置。完成后点击“保存并应用”。
重复打开同一映射、搜索、历史或任务关系窗口会将已有窗口置前；关闭后可重新打开。

安装与启动

普通用户下载发布页的 EXE 后双击运行即可。源码用户先安装 Python 3.12（包含 Tcl/Tk，加入 PATH），解压源码后双击 install.cmd 安装依赖，再双击 start.cmd 启动。首次源码安装需要联网；后续启动不要求互联网，连接远程服务器需要服务器网络可达。

连接服务器
左上五个彩色图标依次为服务器、设置、搜索、映射、帮助，悬停显示名称。
服务器入口可新增页面、选择历史连接、连接全部、断开全部或关闭全部页面。填写地址、账号、端口，选择公钥或密码登录；首次连接核对指纹后信任。
勾选记住密码后，密码使用当前 Windows 用户加密保存。连接中、成功、失败及失败原因显示在服务器页面上方。
软件无需访问互联网，但本机必须能访问服务器；服务器需要 SSH、Python 3 和相应设备驱动。支持昇腾 NPU 和 NVIDIA GPU。

查看任务与资源
页面显示任务、容器、设备、硬件和挂载磁盘；双击磁盘挂载点可进入目录。
点击表头依次按升序、降序、原始顺序排列，刷新保持所选排序。选中任务或容器可查看完整命令、开始时间等详情。
“查空闲”检查所有连接成功的服务器；未检测到加速卡任务的服务器标签显示绿色，点击后恢复。它不表示没有 CPU 服务或其他工作；查询失败不标为空闲。
结束任务或停止容器会影响服务器实际工作，请核对目标。

文件浏览与拖拽
左侧服务器、右侧本地。双击文件夹在 App 内进入；地址栏输入路径后回车，“上级”返回。“打开窗口”才打开 Windows 文件资源管理器。
远程目录使用持久 SSH 通道和缓存，刷新读取最新内容。
Ctrl／Shift 多选；右键执行新建文件夹、删除、拷贝、粘贴、重命名、压缩 ZIP、解压和映射。跨服务器与本地使用上传、下载或拖拽。
App 内两侧可相互拖拽：落在文件夹行时传到该文件夹，落在空白或文件行时传到当前目录，直接传输到目标，不经过默认临时目录。
远程拖出到 Windows 资源管理器需要先下载到临时目录；大文件需等待，准备完成后可重新拖动。临时文件位于 %TEMP%\server-look-drag-*，确认 Windows 复制完成后可手动清理。本地资源管理器文件也可拖入远程列表上传。
拖拽始终复制。普通上传下载可能覆盖同名文件、合并目录，操作前核对确认框；取消或失败可能留下部分文件，不支持断点续传。

目录映射
新增映射后，在行内设置方向、来源和目标；选中映射后，使用来源、目标路径右侧始终显示的“选择文件夹”按钮，可视化选择本机或服务器目录。
单击选中行，点击“一键映射”传输整个来源目录；双击行打开两侧目录，在左侧多选后右键映射。
右键保存或取消当前映射。“历史映射查看”可查看、选用和删除历史配置。
覆盖默认关闭，仅补齐缺失文件；可勾选覆盖同名文件。支持本机与服务器、服务器之间传输，详细说明见文末。
映射拒绝符号链接及不能安全写入 Windows 的名称；可取消，已完成的文件保留。

搜索
搜索名称，不搜索文件内容。选择本地或当前服务器和起始目录，尽量缩小范围以加快搜索。
包含：log 匹配 training.log；完全匹配：config.json 只匹配同名项。
近似匹配：mdl 可匹配 model，字符必须按顺序出现，可间隔，不是拼写纠错。
通配符：*.safetensors；正则：^model.*\.(bin|safetensors)$。
默认忽略大小写，可启用区分大小写，筛选文件／文件夹，选择是否递归；不进入符号链接或目录联接。
结果分批显示，可停止并保留已返回结果；双击结果定位。每次最多 1,000 个结果、扫描 100,000 项、扫描限时 15 秒，SSH 建连时间另计。达到限制或跳过无权限目录时结果可能不完整。

设置、只读与快捷键
支持黑／蓝／白主题、界面与按钮字号、按钮尺寸、顶部／侧栏布局、普通／最大化窗口。设置保存后立即生效。
可自定义或禁用连接、刷新、搜索及新建、拷贝、粘贴、删除、重命名、压缩、解压等快捷键。文件快捷键仅在文件列表获得焦点时生效，当前配置列在帮助下方。
只读模式禁止服务器上传、映射写入、删除、新建、粘贴、重命名、压缩、解压、结束任务和停止容器；允许浏览、搜索、下载、服务器向本地映射及本地文件操作。实际权限也受服务器账号限制。
单个 exe 包含代码和运行库，无需安装 Python。本机偏好、映射配置和历史记录保存在 %APPDATA%\ServerLook；分享 exe 不会分享账号密码。


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


## 2.12.0 多端目录映射与本机中转

打开“映射”，默认只有一个本机目录。点击“添加服务器”，从已连接服务器中按地址选择并浏览远程目录；可添加多个服务器或本机目录。选中目录后点击“设为来源”，其余目录通过“切换目标”设置为一个或多个目标；双击目录修改路径。

“本机中转目录”右侧点击“选择文件夹…”即可选择任意有写入权限、空间足够的本机磁盘目录，保存配置后会记住此地址。支持本机→服务器、服务器→本机、服务器→服务器。默认递归补齐缺少的文件；勾选覆盖后替换同路径文件，保留目标独有文件。映射不删除目标文件，也不跟随符号链接。

服务器间勾选“优先直传”时，源服务器使用自己的 SSH 信任和免密认证连接目标服务器，两端需有 Python 3 与 SSH；本机密码和私钥不会上传。连接失败，或连续 15 秒低于设定阈值（默认 1 MB/s）时，自动使用所选本机目录中转。取消勾选可直接使用本机中转。中转逐块读取、发送和清理，每块最多 8 MiB，不会先下载整个目录或整个大文件；需额外保留约 16 MiB 空闲空间。异常或取消会清理本次临时文件，目标原文件在传输成功前保留。目标服务器只读时禁止映射写入。

选中文件右键“映射”仅传选中项，配置来源需与选中项所在位置一致。旧版两端映射配置会自动转换为一个来源、一个目标。

搜索目录支持可视化选择：在搜索窗口选择“本地”或“当前服务器”，点击路径右侧“选择文件夹…”。本机使用系统文件夹选择窗口，远程复用 RemoteDirectoryDialog 和现有 SSH 目录通道，选定后回填搜索起始路径。

搜索目标下拉框支持本地和所有已打开的服务器页面（按账号、地址、端口区分）；选择服务器后，可可视化选择该服务器上的搜索目录。未连接的页面需先连接。双击结果会定位到搜索时所选服务器；页面关闭或连接变更后需重新搜索。

2.12.1：双击搜索结果切换到对应服务器文件浏览。文件夹进入该目录；文件进入所在目录并在目录加载后选中。搜索窗口暂时隐藏，点击搜索入口可恢复结果。映射配置的“参与目录数”表示配置中的目录位置数量，不是其内部文件或子目录数量。

2.12.2：映射入口简化为历史目录映射下拉框、新增映射和修改映射。仅新增或修改时展开编辑区，保存后自动收起；选择历史方案后可直接一键映射。


## 2.14.0 独立映射行与双栏浏览

点击“新增映射”添加一行，表格展示映射方向、来源文件夹和目标文件夹。单击方向单元格选择本机或已连接服务器的组合；单击路径单元格可直接输入，点击其中的“…”可视化选目录。支持本机→服务器、服务器→本机、服务器→服务器，也可选择本机两个目录。右键“保存映射”写入历史；“取消当前映射”移除当前行，保留历史与实际文件。

单击选中一行，点击“一键映射”递归映射来源目录全部内容。双击该行打开来源与目标双栏目录：双击文件夹进入，左侧 Ctrl / Shift 多选或 Ctrl+A 全选，右键“映射选中项”传输所选文件 / 文件夹；也可右键映射当前目录全部内容。子目录保留相对来源根目录的路径，目标浏览位置不会改变传输目的地。表头支持名称、大小、修改时间的升序、降序、重置排序。

“历史映射查看”展示全部记录，可选用、单选 / 多选删除、全部删除；只删除配置。顶部快捷历史仅列出对应服务器均已连接的记录。旧多目标配置自动拆成一条条来源→目标映射，保存后继续使用。

选中行后，下方设置该条映射的本机中转目录、覆盖已有文件、优先直传、低速阈值。覆盖关闭时只补齐缺失文件；开启时覆盖同名普通文件，两者均保留目标独有文件。直传失败或连续 15 秒低速时询问是否本机中转，中转采用约 8 MiB 分块，不将全部文件先落到本机。传输速度在底部显示；需要改变已打开双栏窗口的映射路径或选项时，请关闭该双栏窗口，修改后重新双击打开。

双击映射进入双栏目录后，两侧均可输入绝对路径并回车，或点击“选择文件夹”修改映射根目录；本机侧可用磁盘下拉框快速切换盘符。成功读取后同步更新主列表，保存仍通过右键操作。普通双击进入子文件夹保持相对映射路径；切换根目录后，选中项按新根目录计算。

2.14.2：来源和目标路径右侧均内置“选择文件夹”按钮，随映射行滚动和调整位置；历史映射窗口默认约 1180×650，可拖动放大，小屏幕自动限制初始尺寸。

点击“一键映射”先显示确认框，核对来源、目标及覆盖选项；点击“是”才开始，点击“否”取消。


文件浏览（2.16）
左侧为服务器文件，右侧为本地文件，可拖动中间分隔线调整宽度。两侧均显示名称、类型、大小、修改时间；点击列标题依次切换升序、降序、恢复原顺序。文件夹大小显示为“—”，不会递归计算以免拖慢浏览。
双击文件夹进入；↑ 返回上级，⌂ 返回根目录，↻ 刷新。本地路径左侧可直接选择 C:、D: 等可用盘符；也可输入路径后按回车。打开窗口在 Windows 文件资源管理器打开所选文件夹或当前目录。
本地工具栏集中上传、下载、取消按钮。先选择来源项再点击对应按钮，目标为对侧当前目录；拖拽到文件夹时以该文件夹为目标。底部显示已完成的顶层项数/总项数及耗时；SFTP 会额外显示当前文件的百分比，系统 SFTP 连接仅显示项数及动态进度条。取消可能保留未完整传输的文件。

文件浏览：两侧导航按钮统一放大，路径栏和文件列表对齐；上传、下载、取消靠右。点击列表空白处可取消选择。服务器拖向本地时显示跟随鼠标的下载提示，按 Esc 可取消本次拖拽。


## 2.18.0：文本编辑与勾选状态

在文件浏览的本地或服务器文件列表中，双击文件夹进入目录，双击非可执行文本文件打开独立编辑窗口。可同时打开多个文件；同一路径会复用已有窗口。编辑器是纯文本编辑器，适合配置、日志、非可执行脚本等，不编辑 Word 富文本格式。

快捷键：Ctrl+S 保存、Ctrl+Z 撤销、Ctrl+Y 重做、Ctrl+A 全选；Ctrl+C/X/V 复制、剪切、粘贴。支持多行编辑、水平和垂直滚动。标题带 * 表示有未保存内容。关闭窗口、服务器页或整个客户端会询问保存、放弃或取消；选择保存会先等待完成再关闭编辑窗口，随后可再次关闭服务器页或程序。读写过程中请等待完成再关闭。

只编辑不超过 4 MiB 的普通文本文件，拒绝二进制文件、可执行文件和设备。保留检测到的 UTF-8、带 BOM UTF-8/UTF-16 或 GB18030 编码；换行按原文件格式保存，混用换行会统一。若文件被其他人修改，保存失败并保留窗口内容，请复制内容另存并重新打开文件。服务器连接发生变化后需重新打开远端文件；只读模式下可查看、复制，不能保存。

所有复选框：勾表示选中/启用，空框表示未选中/关闭。“显示容器内全部进程”勾选后显示容器内全部进程。命令行控制的“关闭当前会话”适用于 Shell 和 Python，关闭当前标签及对应 SSH 会话。

### English — 2.18.0

Double-click a non-executable text file in either file pane to open a separate plain-text editor. Ctrl+S saves, Ctrl+Z undoes, Ctrl+Y redoes, Ctrl+A selects all, and standard copy/cut/paste shortcuts work. Closing an editor, server page, or app prompts to save, discard, or cancel. Saving on close finishes before closing the editor; retry closing the page/app afterwards. Files must be regular text files up to 4 MiB. Supported encodings and line endings are retained (mixed line endings are normalized). External changes prevent overwriting; reconnect and reopen remote files after connection changes. Read-only mode blocks remote saves. A tick means selected/enabled; an empty box means unselected. Close session also closes the current Python session.

English — SSH keys: Detection reports both public/private key paths. Generation reuses existing pairs and reports that no generation is needed. Install first reads the signed-in account’s ~/.ssh/authorized_keys without modifying it. An existing key reports “Paired”; a missing key requires Yes/No confirmation. Only Yes appends the public key at EOF, with a locked duplicate check. Comments and authorized_keys options are supported. Private keys stay local.
