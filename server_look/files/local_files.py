"""Local explorer and background file operations for one server page."""
from pathlib import Path
import queue
import threading
from server_look.localization.localized_ui import ttk, StringVar, messagebox, simpledialog, Menu
from server_look.ui.ui_icons import button as icon_button

from server_look.files.file_transfer import Transfer, open_local_folder
from server_look.ui.table_sort import enable_sort


class LocalFiles:
    def __init__(self, resources, pane):
        self.resources = resources
        self.page = resources.page
        self.events = queue.Queue()
        self.active = False
        self.transfer = None
        frame = ttk.Frame(pane, padding=(10, 0, 0))
        pane.add(frame, weight=2)
        ttk.Label(frame, text='本地文件 · 双击进入文件夹').pack(anchor='w')
        self.path = StringVar(value=str(Path.home()))
        entry = ttk.Entry(frame, textvariable=self.path)
        entry.pack(fill='x', pady=6)
        entry.bind('<Return>', lambda event: self.browse())
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        for title, command in [('上级', self.up), ('刷新', self.browse), ('打开窗口', self.open)]:
            icon_button(bar, text=title, command=command).pack(side='left', padx=2)
        self.files = ttk.Treeview(frame, columns=('kind',), show='tree headings', selectmode='extended')
        self.files.localized_columns = (0,)
        self.files.heading('#0', text='本地名称')
        self.files.heading('kind', text='类型')
        self.files.column('kind', width=65, stretch=False)
        enable_sort(self.files)
        self.files.pack(fill='both', expand=True, pady=6)
        scroll = ttk.Scrollbar(self.files, command=self.files.yview)
        scroll.pack(side='right', fill='y')
        self.files.configure(yscrollcommand=scroll.set)
        self.files.bind('<Double-1>', self.enter)
        actions = ttk.Frame(frame)
        actions.pack(fill='x')
        for title, command in [('上传', lambda: self.start('upload')),
                               ('下载', lambda: self.start('download')),
                               ('取消传输', self.cancel)]:
            icon_button(actions, text=title, command=command).pack(side='left', padx=2)
        self.status = StringVar(value='Ctrl / Shift 多选；本地与服务器之间可直接拖拽传输')
        ttk.Label(frame, textvariable=self.status, wraplength=460).pack(fill='x', pady=6)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x')
        self.items = {}
        self.browse()
        from server_look.files.file_drag import RemoteDrag
        self.drag = RemoteDrag(self)
        self.clipboard = None
        for tree, remote in ((self.files, False), (resources.files, True)):

            menu = Menu(tree, tearoff=False)
            commands = [('新建文件夹', 'mkdir'), ('拷贝', 'copy'),
                        ('粘贴', 'paste'), ('重命名', 'rename'),
                        ('压缩为 ZIP…', 'compress'), ('解压到文件夹…', 'extract'),
                        ('删除', 'delete'), ('映射所选项…', 'mapping')]
            for label, action in commands:
                menu.add_command(label=label, command=lambda a=action, r=remote: self.operate(r, a))
            tree.bind('<Button-3>', lambda event, tree=tree, menu=menu: self.context_menu(event, tree, menu))

    def configure_shortcuts(self, shortcuts):
        from server_look.config.ui_preferences import FILE_ACTIONS
        for tree, remote in ((self.files, False), (self.resources.files, True)):
            for key in getattr(tree, '_file_keys', []):
                tree.unbind(key)
            tree._file_keys = []
            for label, action in FILE_ACTIONS.items():
                key = shortcuts[label]
                if key != '无':
                    tree.bind(key, lambda event, r=remote, a=action: self.operate(r, a))
                    tree._file_keys.append(key)

    @staticmethod
    def context_menu(event, tree, menu):
        row = tree.identify_row(event.y)
        if not row:
            tree.selection_remove(*tree.selection())
        elif row not in tree.selection():
            tree.selection_set(row)
        tree.focus_set()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return 'break'

    def operate(self, remote, action):
        """Snapshot selection and endpoint before dispatching background mutations."""
        if action == 'mapping':
            self.page.root.winfo_toplevel()._serverlook_app.show_mapping(remote)
            return 'break'
        if action == 'delete':
            return self.delete_selected(remote)
        if self.active:
            self.status.set('请等待当前操作完成')
            return 'break'
        if remote and not self.page.connection:
            self.status.set('请先连接服务器')
            return 'break'
        if remote and action != 'copy' and self.page.readonly.get():
            self.status.set('只读模式禁止远程写入，请先关闭只读模式')
            return 'break'
        if action == 'mkdir':
            self.remote_mkdir() if remote else self.mkdir_local()
            return 'break'
        parent = self.resources.current if remote else str(self.current)
        tree = self.resources.files if remote else self.files
        names = ([self.resources.entries[i]['name'] for i in tree.selection() if i in self.resources.entries]
                 if remote else [self.items[i].name for i in tree.selection() if i in self.items])
        connection = self.page.connection if remote else None
        if action == 'copy':
            if names:
                self.clipboard = (remote, connection, parent, names)
                self.status.set(f'已拷贝 {len(names)} 项；进入目标目录后粘贴')
            else:
                self.status.set('请先选择要拷贝的文件或文件夹')
            return 'break'
        options = {}
        if action == 'paste':
            if not self.clipboard or self.clipboard[:2] != (remote, connection):
                self.status.set('请在同一本地或服务器面板拷贝；跨端请使用上传 / 下载')
                return 'break'
            _, _, source, names = self.clipboard
            options['destination'] = parent
            parent, action = source, 'copy'
        elif action in ('rename', 'compress', 'extract'):
            if not names or (action != 'compress' and len(names) != 1):
                self.status.set('请选择一项' if action != 'compress' else '请先选择文件或文件夹')
                return 'break'
            title = {'rename': '重命名', 'compress': '压缩为 ZIP', 'extract': '解压到新文件夹'}[action]
            initial = names[0] if action == 'rename' else (names[0] + '.zip' if action == 'compress' else names[0] + '_解压')
            name = simpledialog.askstring(title, '请输入目标名称（不会覆盖同名项）：',
                                          initialvalue=initial, parent=self.page.root)
            if name is None:
                return 'break'
            options['name'] = name
        if remote:
            work = lambda: connection.directory.request(parent, action=action, names=names, options=options)
        else:
            from server_look.remote.server_resources import file_operation
            work = lambda: file_operation(parent, action, names, **options)
        self.launch(work, {'copy': '复制', 'rename': '重命名', 'compress': '压缩', 'extract': '解压'}[action])
        return 'break'

    def delete_selected(self, remote):
        if self.active:
            self.status.set('请等待当前操作完成')
            return 'break'
        if remote and (not self.page.connection or self.page.readonly.get()):
            self.status.set('请连接服务器并关闭只读模式后删除')
            return 'break'
        if remote:
            import posixpath
            parent = self.resources.current
            paths = [self.resources.entries[i]['path'] for i in self.resources.files.selection()
                     if i in self.resources.entries]
            if not parent or any(posixpath.dirname(p) != parent for p in paths):
                self.status.set('删除目标必须位于当前服务器目录')
                return 'break'
            names = [posixpath.basename(p) for p in paths]
        else:
            parent = str(self.current)
            paths = [str(self.items[i]) for i in self.files.selection() if i in self.items]
            if any(Path(p).parent != self.current for p in paths):
                self.status.set('删除目标必须位于当前本地目录')
                return 'break'
            names = [Path(p).name for p in paths]
        if not paths:
            self.status.set('请选择要删除的文件或文件夹')
            return 'break'
        location = ('服务器：' + self.page.connected_address) if remote else '本地电脑'
        listing = '\n'.join(paths)
        if not messagebox.askyesno('永久删除确认',
                f'{location}\n将永久删除 {len(paths)} 项：\n{listing}\n\n文件夹及其全部内容将被删除，不进入回收站，无法撤销。继续？',
                default='no', icon='warning', parent=self.page.root):
            return 'break'
        if remote:
            connection = self.page.connection
            self.launch(lambda: connection.directory.request(parent, action='delete', names=names), '远程删除')
        else:
            from server_look.remote.server_resources import delete_entries
            self.launch(lambda: delete_entries(parent, names), '本地删除')
        return 'break'

    def browse(self):
        try:
            folder = Path(self.path.get()).resolve(strict=True)
            entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            self.files.delete(*self.files.get_children())
            self.items.clear()
            for item in entries:
                iid = self.files.insert('', 'end', text=item.name, values=('文件夹' if item.is_dir() else '文件',))
                self.items[iid] = item
            self.current = folder
            self.path.set(str(folder))
        except OSError as exc:
            self.status.set(str(exc))

        self.files.sorting.refreshed()

    def selected(self):
        selection = self.files.selection()
        return self.items.get(selection[0]) if selection else None

    def open(self):
        item = self.selected() or getattr(self, 'current', None)
        if item and item.is_dir():
            try:
                open_local_folder(item)
            except OSError as exc:
                self.status.set(str(exc))
        return 'break'

    def enter(self, event=None):
        item = self.selected()
        if item and item.is_dir():
            self.path.set(str(item))
            self.browse()
        return 'break'

    def up(self):
        self.path.set(str(Path(self.path.get()).parent))
        self.browse()

    def mkdir_local(self):
        name = simpledialog.askstring('本地新建文件夹', '文件夹名称：', parent=self.page.root)
        if name:
            try:
                self.validate_name(name)
                (self.current / name).mkdir()
                self.browse()
            except (ValueError, OSError) as exc:
                self.status.set(str(exc))

    @staticmethod
    def validate_name(name):
        if name in ('.', '..') or not name or any(c in name for c in '/\\\0\r\n'):
            raise ValueError('请输入单个文件夹名称')

    def remote_mkdir(self):
        if self.active or not self.page.connection or self.page.readonly.get():
            self.status.set('请连接服务器并关闭只读模式；等待当前操作完成')
            return
        name = simpledialog.askstring('服务器新建文件夹', '文件夹名称：', parent=self.page.root)
        if not name:
            return
        try:
            self.validate_name(name)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        connection = self.page.connection
        path = self.resources.current or '/'
        self.launch(lambda: connection.directory.request(path, action='mkdir', name=name), '创建文件夹')

    def start(self, direction):
        if self.active or not self.page.connection:
            self.status.set('请连接服务器并等待当前操作完成')
            return
        if direction == 'upload' and self.page.readonly.get():
            self.status.set('只读模式禁止上传')
            return
        remote = self.resources.current
        if not remote or not hasattr(self, 'current'):
            self.status.set('请先打开服务器目录和本地目录')
            return
        if direction == 'upload':
            sources = [self.items[i].as_posix() for i in self.files.selection() if i in self.items]
            if not sources:
                self.status.set('请选择要上传的本地项')
                return
            destination = remote
        else:
            sources = [self.resources.entries[i]['path'] for i in self.resources.files.selection()
                       if i in self.resources.entries]
            if not sources:
                self.status.set('请选择要下载的服务器项')
                return
            destination = self.current.as_posix()
        listing = '\n'.join(sources[:8]) + ('\n…' if len(sources) > 8 else '')
        if not messagebox.askyesno('确认文件传输',
                f'服务器：{self.page.connected_address}\n共 {len(sources)} 项：\n{listing}\n目标目录：{destination}\n\n同名文件会被覆盖，文件夹会合并。中断可能留下部分文件。继续？',
                default='no', parent=self.page.root):
            return
        connection = self.page.connection
        self.transfer = Transfer()
        transfer = self.transfer
        self.launch(lambda: transfer.run_many_connection(connection, direction, sources, destination),
                    ('上传' if direction == 'upload' else '下载') + f' {len(sources)} 项')

    def launch(self, work, title):
        self.active = True
        generation = self.page.generation
        self.status.set(title + '进行中…')
        self.progress.start()
        def run():
            result = None
            try:
                result = work()
                error = None
            except Exception as exc:
                error = str(exc)
            self.events.put((generation, error, result if not error and isinstance(result, str) else None))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                generation, error = event[:2]
                detail = event[2] if len(event) > 2 else None
                self.active = False
                self.transfer = None
                self.progress.stop()
                if generation == self.page.generation:
                    self.status.set('操作失败：' + error if error else detail or '操作完成')
                    self.browse()
                    self.resources.cache.clear()
                    self.resources.browse(self.resources.current or '/', force=True)
        except queue.Empty:
            pass

    def cancel(self):
        if self.transfer:
            self.transfer.cancel()
