"""Independent server page; all Tk widget updates stay on the main thread."""
from server_look.ui.platform_ui import monospace
from concurrent.futures import ThreadPoolExecutor
import json
import queue
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import messagebox, ttk
from server_look.ui.table_sort import enable_sort
from server_look.localization.i18n import subscribe, tr
from server_look.ui.ui_icons import button as icon_button

from server_look.transport.client_core import Connection, find_task, task_identity
from server_look.transport.connection_history import ConnectionHistory
from server_look.ui.resource_views import ResourceViews
from server_look.ui.theme import apply_theme
from server_look.app.settings import APP_NAME, APP_VERSION, POLL_INTERVAL_MS, REFRESH_INTERVAL_MS


class ServerPage:
    """One server: widgets, snapshot, selection and background request lifecycle."""
    def __init__(self, root, embedded=False, host='', on_connect=None, on_close=None):
        self.root = root
        self.closed = False
        self.on_connect = on_connect
        self.on_close = on_close or self.close
        self.connection = None
        self.connected_record = None
        self.pending_history = None
        self.data = {}
        self.identity = None
        self.generation = 0
        self.busy = False
        self.fresh = False
        self.results = queue.Queue()
        self.worker = ThreadPoolExecutor(max_workers=2)
        if not embedded:
            apply_theme(root)
            root.title(f'{APP_NAME} {APP_VERSION}')
            root.geometry('1250x820')
            root.minsize(1000, 680)
        self._build_widgets(host)
        subscribe(self)
        if not embedded:
            root.protocol('WM_DELETE_WINDOW', self.close)
        self.buttons()
        self.poll_job = root.after(POLL_INTERVAL_MS, self.poll)
        self.tick_job = root.after(REFRESH_INTERVAL_MS, self.tick)

    def _build_widgets(self, host):
        outer = ttk.Frame(self.root, padding=(10, 4))
        outer.pack(fill='both', expand=True)
        self.history_store = ConnectionHistory()
        self.history_records = []
        self.host, self.user, self.port = tk.StringVar(value=host), tk.StringVar(value='root'), tk.StringVar(value='22')
        self.readonly = tk.BooleanVar(value=False)
        self.auth_mode = tk.StringVar(value='公钥登录')
        self.password = tk.StringVar()
        self.remember_password = tk.BooleanVar(value=True)
        self.connection_state = tk.StringVar(value='尚未连接')
        self.connection_error = ''
        self.status = tk.StringVar(value='点击“服务器连接”设置地址和登录方式')
        toolbar = self.toolbar = ttk.Frame(outer, padding=(0, 2, 0, 6))
        toolbar.pack(fill='x')
        icon_button(toolbar, text='连接', style='Capsule.TButton', command=self.show_connection_dialog).pack(side='left')
        icon_button(toolbar, text='刷新', style='Capsule.TButton', command=self.refresh).pack(side='left', padx=5)
        icon_button(toolbar, text='断开', style='Capsule.TButton', command=self.disconnect).pack(side='left')
        self.close_button = icon_button(toolbar, text='关闭', style='Capsule.TButton', command=self.on_close)
        self.close_button.pack(side='left', padx=5)
        self.idle_button = icon_button(toolbar, text='查空闲', style='Capsule.TButton', command=lambda: self.root.winfo_toplevel()._serverlook_app.query_idle())
        self.idle_button.pack(side='left', padx=(5, 0))
        self.connection_badge = ttk.Label(toolbar, textvariable=self.connection_state, style='Muted.TLabel')
        self.connection_badge.pack(side='left', padx=8)
        self.error_button = icon_button(toolbar, text='失败原因', state='disabled', command=self.show_connection_error)
        self.readonly_label = ttk.Label(outer, text='远程可写', style='Muted.TLabel')
        self._build_connection_dialog()
        self.summary = tk.StringVar(value='连接服务器后显示任务与资源数据')
        ttk.Label(outer, textvariable=self.summary, style='Summary.TLabel').pack(fill='x', pady=(0, 4))
        self._build_views(outer)
        self._build_actions(outer)
        self.tabs.pack_forget()
        self.footer = ttk.Frame(outer)
        self.footer.pack(side='bottom', fill='x', pady=(4, 0))
        ttk.Label(self.footer, textvariable=self.status, style='Muted.TLabel', anchor='w').pack(side='left', fill='x', expand=True)
        self.readonly_label.pack(in_=self.footer, side='right')
        self.controls.pack(side='bottom', fill='x', before=self.footer)
        self.tabs.pack(fill='both', expand=True)
        self.reload_history()

    def _build_connection_dialog(self):
        # Keep the form alive while hidden, so closing it never loses typed credentials.
        self.connection_dialog = tk.Toplevel(self.root)
        self.connection_dialog.withdraw()
        self.connection_dialog.title('服务器连接')
        self.connection_dialog.resizable(False, False)
        self.connection_dialog.transient(self.root.winfo_toplevel())
        self.connection_dialog.protocol('WM_DELETE_WINDOW', self.connection_dialog.withdraw)
        form = ttk.Frame(self.connection_dialog, padding=24)
        form.pack(fill='both', expand=True)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text='选择历史连接或填写服务器信息', style='Muted.TLabel').grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 16))
        ttk.Label(form, text='历史连接').grid(row=1, column=0, sticky='w', padx=(0, 16))
        self.history_selector = ttk.Combobox(form, state='readonly', width=34, postcommand=self.reload_history)
        self.history_selector.grid(row=1, column=1, sticky='ew', pady=5)
        self.history_selector.bind('<<ComboboxSelected>>', self.select_history)
        icon_button(form, text='删除历史', command=self.forget_history).grid(row=1, column=2, padx=(8, 0))
        for row, (label, variable) in enumerate([('服务器地址', self.host), ('用户名', self.user), ('SSH 端口', self.port)], start=2):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky='w')
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, columnspan=2, sticky='ew', pady=5)
        ttk.Label(form, text='认证方式').grid(row=5, column=0, sticky='w')
        selector = ttk.Combobox(form, textvariable=self.auth_mode, values=('公钥登录', '账号密码'), state='readonly')
        selector.grid(row=5, column=1, columnspan=2, sticky='ew', pady=5)
        selector.bind('<<ComboboxSelected>>', self.change_auth)
        ttk.Label(form, text='密码').grid(row=6, column=0, sticky='w')
        self.password_entry = ttk.Entry(form, textvariable=self.password, show='●', state='disabled')
        self.password_entry.grid(row=6, column=1, columnspan=2, sticky='ew', pady=5)
        ttk.Checkbutton(form, text='记住密码（系统安全存储）', variable=self.remember_password).grid(row=7, column=1, columnspan=2, sticky='w', pady=(6, 16))
        actions = ttk.Frame(form)
        actions.grid(row=8, column=0, columnspan=3, sticky='e')
        icon_button(actions, text='取消', command=self.connection_dialog.withdraw).pack(side='left', padx=8)
        icon_button(actions, text='连接服务器', style='Accent.TButton', command=self.connect).pack(side='left')

    def show_connection_dialog(self):
        window = self.connection_dialog
        owner = self.root.winfo_toplevel()
        window.geometry(f'+{owner.winfo_rootx() + 80}+{owner.winfo_rooty() + 100}')
        window.deiconify()
        window.lift()
        window.focus_set()
        apply_theme(owner, getattr(owner, '_serverlook_theme', '深海蓝'))

    def _build_views(self, outer):
        self.tabs = ttk.Notebook(outer, style='Content.TNotebook')
        self.tabs.pack(fill='both', expand=True)
        self.tasks = self.table('运行任务', [('pid', 'PID', 85), ('ppid', '父 PID', 85), ('children', '直接子 PID', 150), ('started', '任务开始时间', 200), ('user', '用户', 90), ('npu', '设备 / 显存 MiB', 150), ('container', 'Docker', 220), ('command', '启动命令', 450)])
        self.containers = self.table('Docker 容器', [('name', '容器名称', 280), ('started', '容器开始时间', 210), ('pid', '入口 PID', 100), ('image', '镜像', 480)])
        npu = ttk.Frame(self.tabs)
        self.tabs.add(npu, text='NPU / GPU 状态')
        self.npu = tk.Text(npu, font=(monospace(), 11), wrap='none', state='disabled')
        self.npu.pack(fill='both', expand=True)
        self.resources = ResourceViews(self)
        from server_look.ui.command_panel import CommandPanel
        self.commands = CommandPanel(self)
        self.view_choice = tk.StringVar(value=self.tabs.select())
        self.view_buttons = []
        group = ttk.Frame(self.toolbar)
        group.pack(side='right')
        labels = ('运行任务', '容器', 'NPU / GPU', '硬件配置', '磁盘挂载', '文件浏览', '命令行控制')
        for tab, label in zip(self.tabs.tabs(), labels):
            widget = ttk.Radiobutton(group, text=label, value=tab, variable=self.view_choice,
                                     style='View.TRadiobutton', command=lambda tab=tab: self.tabs.select(tab))
            widget.pack(side='left', padx=1)
            self.view_buttons.append(widget)

    def _build_actions(self, outer):
        controls = ttk.Frame(outer, padding=(0, 5))
        self.controls = controls
        self.all_tasks = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text='显示容器内全部进程', variable=self.all_tasks, command=self.render).pack(side='left')
        self.parent_button = icon_button(controls, text='选中父任务', command=self.parent)
        self.parent_button.pack(side='left', padx=8)
        self.relations_button = icon_button(controls, text='任务关系', command=self.relations)
        self.relations_button.pack(side='left', padx=(0, 8))
        self.term_button = icon_button(controls, text='结束任务', command=lambda: self.act('term'))
        self.term_button.pack(side='left')
        self.kill_button = icon_button(controls, text='强制结束', style='Danger.TButton', command=lambda: self.act('kill'))
        self.kill_button.pack(side='left', padx=8)
        self.stop_button = icon_button(controls, text='停止选中 Docker', command=lambda: self.act('stop'))
        self.stop_button.pack(side='left')
        extra = ttk.Frame(controls)
        extra.pack(side='bottom', fill='x', pady=(5, 0), before=controls.winfo_children()[0])
        self.provenance_button = icon_button(extra, text='读取来源详情', command=self.load_task_details)
        self.provenance_button.pack(side='left')
        self.kill_npu_button = icon_button(extra, text='结束全部 NPU 任务', style='Danger.TButton', command=self.kill_npu)
        self.kill_npu_button.pack(side='left', padx=8)
        self.task_provenance = {}
        self.details_box = ttk.Frame(outer)
        self.details = tk.Text(self.details_box, height=8, wrap='word', font=('Microsoft YaHei UI', 10), state='disabled', pady=3)
        scroll = ttk.Scrollbar(self.details_box, command=self.details.yview)
        scroll.pack(side='right', fill='y')
        self.details.configure(yscrollcommand=scroll.set)
        self.details.pack(fill='both', expand=True)
        self.tasks.bind('<<TreeviewSelect>>', self.select_task)
        self.containers.bind('<<TreeviewSelect>>', lambda event: self.show_details())
        self.tabs.bind('<<NotebookTabChanged>>', lambda event: self.show_details())
        self.tasks.bind('<Delete>', lambda event: self.act('term'))
        self.tasks.bind('<Shift-Delete>', lambda event: self.act('kill'))

    def table(self, title, columns):
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=title)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show='headings', selectmode='browse')
        for key, label, width in columns:
            tree.heading(key, text=label)
            tree.column(key, width=width, minwidth=70, stretch=key in ('command', 'image'))
        vertical = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        enable_sort(tree)
        return tree

    def reload_history(self):
        try:
            self.history_records = self.history_store.load()
        except (OSError, ValueError):
            self.history_records = []
            self.status.set('无法读取连接历史，请检查用户配置目录中的 connections.json')
        self.history_selector.configure(values=[f"{r['user']}@{r['host']}:{r['port']} · {'密码' if r['auth_mode'] == 'password' else '公钥'}"
                                                 for r in self.history_records])

    def select_history(self, event=None):
        index = self.history_selector.current()
        if not 0 <= index < len(self.history_records):
            return
        record = self.history_records[index]
        self.apply_history(record)

    def apply_history(self, record):
        """Fill saved credentials for manual or bulk connection; return availability."""
        self.host.set(record['host'])
        self.user.set(record['user'])
        self.port.set(record['port'])
        self.auth_mode.set('账号密码' if record['auth_mode'] == 'password' else '公钥登录')
        self.change_auth()
        self.remember_password.set(bool(record.get('password')))
        try:
            self.password.set(self.history_store.password(record) if record['auth_mode'] == 'password' else '')
            self.status.set('已填入历史连接，点击连接 / 重新连接')
            return True
        except (OSError, ValueError, UnicodeError):
            self.password.set('')
            self.status.set('无法从当前系统安全存储读取密码，请重新输入密码')
            return False

    def forget_history(self):
        index = self.history_selector.current()
        if not 0 <= index < len(self.history_records):
            return
        try:
            self.history_store.delete(self.history_records[index])
        except (OSError, ValueError):
            self.status.set('无法删除连接历史，请检查配置目录权限')
            return
        self.history_selector.set('')
        self.password.set('')
        self.reload_history()
        self.status.set('已删除该连接历史和保存的密码；当前连接不受影响')

    def save_connected_history(self):
        pending, self.pending_history = self.pending_history, None
        if pending is None:
            return
        record, password, remember = pending
        try:
            self.history_store.save(record, password, remember)
            self.reload_history()
        except (OSError, ValueError):
            messagebox.showwarning('连接历史', '连接成功，但保存历史失败。请检查用户配置目录权限及系统密码安全存储服务。', parent=self.root)

    def set_connection_state(self, state, error=''):
        self.connection_state.set(state)
        self.connection_error = error
        style = ('ConnectionError.TLabel' if error else
                 'ConnectionSuccess.TLabel' if state == '连接成功' else
                 'ConnectionPending.TLabel' if state == '连接中…' else 'Muted.TLabel')
        self.connection_badge.configure(style=style)
        self.error_button.configure(state='normal' if error else 'disabled')
        if error:
            self.error_button.pack(side='left', padx=4)
        else:
            self.error_button.pack_forget()

    def show_connection_error(self):
        if self.connection_error:
            messagebox.showerror(self.connection_state.get(), self.connection_error, parent=self.root)

    def change_auth(self, event=None):
        self.password_entry.configure(state="normal" if self.auth_mode.get() == "账号密码" else "disabled")
        self.password.set("")

    def connect(self):
        try:
            connection = Connection(self.host.get().strip(), self.user.get().strip(), self.port.get(),
                                    auth_mode="password" if self.auth_mode.get() == "账号密码" else "key",
                                    password=self.password.get())
        except (ValueError, RuntimeError) as exc:
            self.set_connection_state('连接失败', str(exc))
            self.status.set('连接参数错误：' + str(exc))
            messagebox.showerror('连接参数', str(exc))
            return
        pending = (dict(host=self.host.get().strip(), user=self.user.get().strip(),
                        port=str(int(self.port.get())),
                        auth_mode='password' if self.auth_mode.get() == '账号密码' else 'key'),
                   self.password.get(), self.remember_password.get())
        self.disconnect()
        self.pending_history = pending
        self.connected_record = pending[0]
        self.password.set("")
        self.connection = connection
        self.connected_address = f'{self.user.get().strip()}@{self.host.get().strip()}:{self.port.get()}'
        if self.on_connect:
            self.on_connect(self.connected_address)
        self.set_connection_state('连接中…')
        self.status.set(f'正在连接 {self.connected_address}，等待 SSH 认证及首次数据返回…')
        self.refresh()
        self.connection_dialog.withdraw()

    def disconnect(self):
        self.task_provenance.clear()
        self.commands.disconnect()
        app = getattr(self.root.winfo_toplevel(), '_serverlook_app', None)
        if app:
            app.occupancy_marks.pop(str(self.root), None)
            app.occupancy_details.pop(str(self.root), None)
            app.server_tabs.draw()
        self.pending_history = None
        self.idle_pending = False
        self.generation += 1
        if self.connection and hasattr(self.connection, 'close'):
            self.connection.close()
        self.connection = None
        self.connected_record = None
        self.data, self.identity = {}, None
        self.busy = self.fresh = False
        self.set_connection_state('已断开')
        self.status.set('已断开')
        self.resources.reset()
        self.render()

    def submit(self, action, **values):
        if action not in ('list_directory', 'idle'):
            self.busy = True
            self.buttons()
        # A reconnect invalidates queued results from the previous connection.
        generation, connection = self.generation, self.connection
        def work():
            try:
                result = connection.request(action, **values)
                self.results.put((generation, action, result, None))
            except Exception as exc:
                self.results.put((generation, action, None, str(exc)))
        self.worker.submit(work)

    def refresh(self):
        if self.connection and not self.busy:
            if self.connection_state.get() != '连接中…':
                self.status.set('正在通过 SSH 获取数据…')
            self.submit('snapshot')

    def poll(self):
        """Apply worker results only on the Tk thread and for this connection generation."""
        self.resources.local.poll()
        try:
            while True:
                generation, action, result, error = self.results.get_nowait()
                if generation != self.generation:
                    continue
                if action == 'idle':
                    self.root.winfo_toplevel()._serverlook_app.idle_result(self, result, error)
                    continue
                if action == 'list_directory':
                    self.resources.complete(result, error)
                    continue
                self.busy = False
                if error:
                    self.fresh = False
                    if action == 'snapshot':
                        self.set_connection_state('连接异常' if self.data else '连接失败', error)
                    self.status.set(('连接或数据读取失败：' if action == 'snapshot' else '操作失败：') + error.replace('\n', ' ')[:250] + (' · 点击“查看失败原因”查看完整信息' if action == 'snapshot' else ''))
                    session = getattr(self.connection, 'session', None)
                    prompt = session.host_key_prompt() if session else None
                    if prompt:
                        trusted = messagebox.askyesno('确认服务器主机指纹', prompt, default='no', icon='warning', parent=self.root)
                        try:
                            session.confirm_host_key(trusted)
                        except OSError as exc:
                            messagebox.showerror('无法保存主机指纹', str(exc), parent=self.root)
                        else:
                            if trusted:
                                self.refresh()
                    if action != 'snapshot':
                        messagebox.showerror('操作失败', error)
                elif action == 'task_details':
                    self.task_provenance[(result['pid'], result['ticks'])] = result
                    self.show_details()
                elif action == 'snapshot':
                    self.set_connection_state('连接成功')
                    self.save_connected_history()
                    self.data, self.fresh = result, True
                    result['errors'] = result.get('errors', []) + result.get('resource_errors', [])
                    self.status.set(f"{result['host']} · 服务器时间 {result['time']} · 每 3 秒自动刷新" + (' · ' + '; '.join(result['errors']) if result['errors'] else ''))
                    self.render()
                else:
                    self.status.set('操作完成：' + result['message'])
                    if action == 'kill_npu':
                        messagebox.showinfo('批量结束结果', result['message'], parent=self.root)
                    self.fresh = False
                    self.refresh()
                self.buttons()
        except queue.Empty:
            pass
        if not self.closed:
            self.poll_job = self.root.after(POLL_INTERVAL_MS, self.poll)

    def tick(self):
        # Terminal output arrives through its SSH channel; monitoring snapshots
        # are unnecessary while this page is used as an interactive terminal.
        if self.tabs.select() != str(self.commands.frame):
            self.refresh()
        if not self.closed:
            self.tick_job = self.root.after(REFRESH_INTERVAL_MS, self.tick)

    @staticmethod
    def write(widget, text):
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget.configure(state='disabled')

    def refresh_language(self):
        if not self.closed and self.root.winfo_exists() and not self.data.get('npu'):
            self.write(self.npu, tr('连接服务器后显示 NPU / GPU 利用率、显存、功耗、温度和进程。'))

    def render(self):
        processes = self.data.get('processes', {})
        npu_count = sum(bool(proc.get('npu')) for proc in processes.values())
        if self.data:
            summary = f"加速卡任务 {npu_count} · 容器 {len(self.data.get('containers', {}))} · 容器及加速卡进程 {len(processes)}"
            if not npu_count:
                summary += ' · 当前没有正在占用 NPU / GPU 的计算任务'
            if not self.all_tasks.get():
                summary += ' · 仅显示 加速卡任务；勾选“显示容器内全部进程”可查看其他进程'
            self.summary.set(summary)
        else:
            self.summary.set('连接服务器后显示任务与资源数据')
        cid = self.selected_container()
        self.tasks.delete(*self.tasks.get_children())
        children = {}
        for proc in processes.values():
            children.setdefault(proc.get('ppid'), []).append(proc['pid'])
        for proc in processes.values():
            if not self.all_tasks.get() and not proc.get('npu'):
                continue
            container = self.data['containers'].get(proc['container'], {})
            iid = f"{proc['pid']}:{proc['ticks']}"
            self.tasks.insert('', 'end', iid=iid, values=(proc['pid'], proc.get('ppid', '—'), ', '.join(map(str, sorted(children.get(proc['pid'], [])))) or '—', proc['started'], proc['user'], ', '.join(f'{k}: {v}' for k, v in proc.get('npu', {}).items()), container.get('name', '宿主机'), proc['command']))
            if task_identity(proc) == self.identity:
                self.tasks.selection_set(iid)
        self.containers.delete(*self.containers.get_children())
        for container in self.data.get('containers', {}).values():
            self.containers.insert('', 'end', iid=container['id'], values=(container['name'], container['started'], container['pid'], container['image']))
        if cid and self.containers.exists(cid):
            self.containers.selection_set(cid)
        self.tasks.sorting.refreshed()
        self.containers.sorting.refreshed()
        self.resources.render(self.data)
        self.write(self.npu, self.data.get('npu') or tr('连接服务器后显示 NPU / GPU 利用率、显存、功耗、温度和进程。'))
        self.show_details()

    def select_task(self, event=None):
        selection = self.tasks.selection()
        if selection:
            self.identity = tuple(map(int, selection[0].split(':')))
        self.show_details()

    def selected_container(self):
        selection = self.containers.selection()
        return selection[0] if selection else None

    def show_details(self):
        index = self.tabs.index('current')
        self.view_choice.set(self.tabs.select())
        if index >= 2:
            item = None
            self.controls.pack_forget()
        elif index == 1:
            item = self.data.get('containers', {}).get(self.selected_container())
        else:
            item = find_task(self.data, self.identity)
            if item:
                item = dict(item, docker=self.data.get('containers', {}).get(item['container']))
                item['执行服务器'] = self.data.get('host') or getattr(self, 'connected_address', self.host.get())
                item['来源详情（按需读取）'] = self.task_provenance.get(task_identity(item), '点击“读取来源详情”获取工作目录、脚本/数据路径线索和启动来源')
        if index < 2:
            self.controls.pack(side='bottom', fill='x', before=self.footer)
        if item:
            self.write(self.details, json.dumps(item, ensure_ascii=False, indent=2))
            self.details.pack(fill='both', expand=True)
            self.details_box.pack(side='bottom', fill='x', before=self.controls)
        else:
            self.details.pack_forget()
            self.details_box.pack_forget()
        self.buttons()

    def buttons(self):
        enabled = self.connection is not None and self.fresh and not self.busy and not self.readonly.get()
        task = find_task(self.data, self.identity)
        task_tab = self.tabs.index('current') == 0 and bool(self.tasks.selection())
        for button in (self.term_button, self.kill_button):
            button.configure(state='normal' if enabled and task and task_tab else 'disabled')
        self.parent_button.configure(state='normal' if task and task_tab else 'disabled')
        self.relations_button.configure(state='normal' if task and task_tab else 'disabled')
        self.stop_button.configure(state='normal' if enabled and self.tabs.index('current') == 1 and self.selected_container() else 'disabled')
        self.provenance_button.configure(state='normal' if self.connection and not self.busy and task and task_tab else 'disabled')
        self.kill_npu_button.configure(state='normal' if enabled and self.npu_targets() and self.tabs.index('current') == 0 else 'disabled')

    def load_task_details(self):
        task = find_task(self.data, self.identity)
        if self.connection and not self.busy and task:
            self.submit('task_details', pid=task['pid'], ticks=task['ticks'])

    def npu_targets(self):
        return [p for p in self.data.get('processes', {}).values()
                if any(':' in device and device.split(':', 1)[0].isdigit() for device in p.get('npu', {}))]

    def kill_npu(self):
        if not self.connection or self.busy or not self.fresh or self.readonly.get():
            return
        targets = self.npu_targets()
        if not targets:
            return
        lines = [f"PID {p['pid']} · {p['user']} · {p['command'][:160]}" for p in targets]
        prompt = (f'服务器：{self.connected_address}\n\n确认强制结束全部 {len(targets)} 个 NPU 任务？\n'
                  '未保存的数据会丢失；服务管理器可能自动重启服务。\n仅结束本次确认且执行时仍占用 NPU 的进程。\n\n' + '\n'.join(lines))
        if messagebox.askyesno('确认结束全部 NPU 任务', prompt, default='no', icon='warning', parent=self.root):
            self.submit('kill_npu', targets=[{'pid': p['pid'], 'ticks': p['ticks']} for p in targets])

    def relations(self):
        task = find_task(self.data, self.identity)
        if task:
            from server_look.ui.task_relations import show_relations
            show_relations(self.root, self.data.get('processes', {}), task, self.select_related)
            apply_theme(self.root.winfo_toplevel(), getattr(self.root.winfo_toplevel(), '_serverlook_theme', '深海蓝'))

    def select_related(self, task):
        current = find_task(self.data, task_identity(task))
        if current:
            self.identity = task_identity(current)
            self.all_tasks.set(True)
            self.render()
            self.tasks.see(f"{current['pid']}:{current['ticks']}")
        else:
            messagebox.showinfo('任务已变更', '该任务已退出，请刷新后查看。', parent=self.root)

    def parent(self):
        task = find_task(self.data, self.identity)
        parent = self.data.get('processes', {}).get(str(task['ppid'])) if task else None
        if parent:
            self.identity = task_identity(parent)
            self.all_tasks.set(True)
            self.render()
            self.tasks.see(f"{parent['pid']}:{parent['ticks']}")
        else:
            messagebox.showinfo('父任务', '父任务已退出，或不在容器任务列表内。')

    def act(self, action):
        if not self.connection or self.busy or not self.fresh or self.readonly.get():
            return
        if action == 'stop':
            item = self.data.get('containers', {}).get(self.selected_container())
            if not item or self.tabs.index('current') != 1:
                return
            values = {'cid': item['id']}
            prompt = f"停止容器 {item['name']}？\n容器内全部任务都将停止。\n{item['id']}"
        else:
            item = find_task(self.data, self.identity)
            if not item or self.tabs.index('current') != 0 or not self.tasks.selection():
                return
            values = {'pid': item['pid'], 'ticks': item['ticks']}
            prompt = f"{'强制结束' if action == 'kill' else '结束'}任务及其当前子进程？\nPID: {item['pid']}\n开始时间: {item['started']}\n{item['command'][:800]}"
        if messagebox.askyesno('确认操作', f'服务器：{self.connected_address}\n\n{prompt}', default='no', icon='warning', parent=self.root):
            self.submit(action, **values)

    def close(self):
        if self.closed:
            return
        if not self.resources.editors.close_all():
            return False
        self.closed = True
        self.commands.close()
        self.pending_history = None
        self.resources.local.cancel()
        if self.connection and hasattr(self.connection, 'close'):
            self.connection.close()
        self.generation += 1
        self.root.after_cancel(self.poll_job)
        self.root.after_cancel(self.tick_job)
        self.worker.shutdown(wait=False, cancel_futures=True)
        self.connection_dialog.destroy()
        self.root.destroy()
