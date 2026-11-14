"""Local/remote file search window. Workers communicate with Tk through a queue."""
from concurrent.futures import ThreadPoolExecutor
import os
from datetime import datetime
from table_sort import enable_sort
import posixpath
import queue
import threading
from localized_ui import tk
from localized_ui import ttk, messagebox, filedialog
from file_search import MODES, run_search, validate_search
from ui_icons import button

class SearchDialog:
    def __init__(self, app, page):
        self.app, self.page = app, page
        self.window = tk.Toplevel(app.root)
        self.window.title('搜索文件与文件夹')
        self.window.geometry('930x600')
        self.window.minsize(740, 430)
        self.window.transient(app.root)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.closed = False
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.active = False
        self.target = tk.StringVar(value='本地')
        self.path = tk.StringVar(value=str(page.resources.local.current))
        self.pattern = tk.StringVar()
        self.mode = tk.StringVar(value='包含')
        self.kind = tk.StringVar(value='全部')
        self.case = tk.BooleanVar(value=False)
        self.directory_sizes = tk.BooleanVar(value=False)
        self.recursive = tk.BooleanVar(value=True)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill='both', expand=True)
        row = ttk.Frame(frame)
        row.pack(fill='x')
        self.target_pages = {}
        target = self.target_box = ttk.Combobox(row, textvariable=self.target, width=30, state='readonly', postcommand=self.refresh_targets)
        self.refresh_targets()
        target.pack(side='left')
        target.bind('<<ComboboxSelected>>', self.change_target)
        ttk.Entry(row, textvariable=self.path).pack(side='left', fill='x', expand=True, padx=(8, 0))
        button(row, text='选择文件夹…', command=self.choose_directory).pack(side='left', padx=(8, 0))
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=10)
        entry = ttk.Entry(row, textvariable=self.pattern)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda e: self.start())
        ttk.Combobox(row, textvariable=self.mode, values=MODES, width=12, state='readonly').pack(side='left', padx=8)
        ttk.Combobox(row, textvariable=self.kind, values=('全部', '文件', '文件夹'), width=8, state='readonly').pack(side='left')
        self.start_button = button(row, text='搜索', style='Accent.TButton', command=self.start)
        self.start_button.pack(side='left', padx=8)
        self.stop_button = button(row, text='停止', command=self.stop, state='disabled')
        self.stop_button.pack(side='left')
        row = ttk.Frame(frame)
        row.pack(fill='x')
        ttk.Checkbutton(row, text='区分大小写', variable=self.case).pack(side='left')
        ttk.Checkbutton(row, text='包含子文件夹', variable=self.recursive).pack(side='left', padx=12)
        ttk.Checkbutton(row, text='统计文件夹总大小（较慢）', variable=self.directory_sizes).pack(side='left')
        ttk.Label(row, text='仅匹配文件/文件夹名称，非文件内容', style='Muted.TLabel').pack(side='right')
        self.tree = ttk.Treeview(frame, columns=('kind', 'size', 'modified', 'path'), show='tree headings')
        self.tree.localized_columns = (0,)
        for column, label, width in [('#0', '名称', 220), ('kind', '类型', 75), ('size', '大小（字节）', 120), ('modified', '修改时间', 155), ('path', '完整路径（双击定位）', 350)]:
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width)
        self.sorting = enable_sort(self.tree)
        self.tree.pack(fill='both', expand=True, pady=10)
        for orient in ('vertical', 'horizontal'):
            scroll = ttk.Scrollbar(self.tree, orient=orient, command=self.tree.yview if orient == 'vertical' else self.tree.xview)
            scroll.pack(side='right' if orient == 'vertical' else 'bottom', fill='y' if orient == 'vertical' else 'x')
            self.tree.configure(**{('yscrollcommand' if orient == 'vertical' else 'xscrollcommand'): scroll.set})
        self.tree.bind('<Double-1>', self.locate)
        self.status = tk.StringVar(value='包含：字面子串（类似 fgrep）；完全：全名相同；近似：字符依次出现，如 mdl 匹配 model；通配符：*.bin；正则：^model.*。默认忽略大小写。')
        ttk.Label(frame, textvariable=self.status, wraplength=850).pack(fill='x')
        self.items = {}
        self.app.retheme()
        entry.focus_set()
        self.timer = self.window.after(100, self.poll)

    def refresh_targets(self):
        selected = self.target_pages.get(self.target.get())
        pages = {}
        for page in self.app.pages.values():
            label = f'{page.user.get()}@{page.host.get() or "未填写地址"}:{page.port.get()}'
            if page is self.page:
                label += '（当前）'
            base = label
            count = 2
            while label in pages:
                label = f'{base} [{count}]'
                count += 1
            pages[label] = page
        self.target_pages = pages
        self.target_box.configure(values=('本地', *pages))
        if selected is not None:
            label = next((key for key, page in pages.items() if page is selected), None)
            if label:
                self.target.set(label)

    def selected_page(self):
        page = self.target_pages.get(self.target.get())
        if page is None or str(page.root) not in self.app.pages:
            raise ValueError('所选服务器页面已关闭，请重新选择服务器')
        if not page.connection:
            raise ValueError('请先连接所选服务器')
        return page

    def change_target(self, event=None):
        page = self.target_pages.get(self.target.get())
        self.path.set((page.resources.current or '/') if page else str(self.page.resources.local.current))

    def choose_directory(self):
        if self.target.get() == '本地':
            path = filedialog.askdirectory(parent=self.window, initialdir=self.path.get(),
                                           title='选择搜索文件夹')
            if path:
                self.path.set(path)
            return
        try:
            page = self.selected_page()
        except ValueError as exc:
            messagebox.showinfo('选择搜索目录', str(exc), parent=self.window)
            return
        from remote_directory_dialog import RemoteDirectoryDialog
        RemoteDirectoryDialog(self.window, page.connection, self.path.get() or '/', self.path.set)
        self.app.retheme()

    def start(self):
        if self.active:
            return
        try:
            options = validate_search(self.path.get().strip(), self.pattern.get(), self.mode.get(), self.case.get(), self.recursive.get(), self.kind.get()) if self.target.get() == '本地' else dict(path=self.path.get().strip(), pattern=self.pattern.get(), mode=self.mode.get(), case_sensitive=self.case.get(), recursive=self.recursive.get(), kind=self.kind.get())
            remote = self.target.get() != '本地'
            page = self.selected_page() if remote else self.page
            # Remote POSIX paths are validated on the server, not by Windows isabs.
            if remote and (not options['path'].startswith('/') or not options['pattern']):
                raise ValueError('请输入服务器绝对目录和搜索条件')
        except Exception as exc:
            messagebox.showerror('搜索条件错误', str(exc), parent=self.window)
            return
        options['directory_sizes'] = self.directory_sizes.get()
        self.search_page = page
        self.connection = page.connection if remote else None
        self.remote = remote
        self.cancel.clear()
        self.active = True
        self.start_button.configure(state='disabled')
        self.stop_button.configure(state='normal')
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        self.status.set('正在搜索… 结果分批显示，可随时停止。最多扫描 10 万项、显示 1000 项，单次扫描限时 15 秒。')
        def work():
            try:
                batch = lambda rows: self.events.put(('batch', rows))
                data = (self.connection.search(options, self.cancel, batch) if self.remote else
                        run_search(**options, cancel=self.cancel, on_batch=batch))
                self.events.put(('done', data))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        self.executor.submit(work)

    def stop(self):
        self.cancel.set()
        self.status.set('正在停止…' if self.remote else '正在停止本地搜索…')
        self.stop_button.configure(state='disabled')

    def poll(self):
        if self.closed:
            return
        try:
            event, data = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            if event == 'batch':
                self.add_results(data)
                self.status.set(f'正在搜索… 已找到 {len(self.items)} 项')
                self.timer = self.window.after(20, self.poll)
                return
            self.active = False
            self.start_button.configure(state='normal')
            self.stop_button.configure(state='disabled')
            if event == 'error':
                self.status.set('搜索失败：' + data)
            else:
                reason = data['reason']
                self.status.set(f"{reason} · {len(data['results'])} 项 · 扫描 {data['scanned'] if data['scanned'] is not None else '未完成统计'} · 跳过 {data['skipped'] if data['skipped'] is not None else '未完成统计'} · {data['elapsed']} 秒")
        self.timer = self.window.after(100, self.poll)

    def add_results(self, rows):
        for item in rows:
            size = item.get('size')
            size_text = '未统计' if size is None else str(size)
            if not item.get('size_complete', True):
                size_text += '（不完整）'
            modified = datetime.fromtimestamp(item['modified']).strftime('%Y-%m-%d %H:%M:%S') if item.get('modified') is not None else '—'
            iid = self.tree.insert('', 'end', text=item['name'], values=('文件夹' if item['directory'] else '文件', size_text, modified, item['path']))
            self.items[iid] = item
        self.sorting.original = list(self.items)
        self.sorting.apply()

    def locate(self, event=None):
        selected = self.tree.selection()
        if not selected or self.closed:
            return
        item = self.items[selected[0]]
        page = self.search_page
        if str(page.root) not in self.app.pages:
            messagebox.showinfo('页面已关闭', '请在新的服务器页面重新搜索。', parent=self.window)
            return
        self.app.notebook.select(page.root)
        page.tabs.select(page.resources.frame)
        if self.remote:
            if page.connection is not self.connection:
                messagebox.showinfo('连接已变更', '请重新搜索所选服务器。', parent=self.window)
                return
            page.resources.browse(item['path'] if item['directory'] else posixpath.dirname(item['path']),
                                  select=None if item['directory'] else item['path'])
        else:
            page.resources.local.path.set(item['path'] if item['directory'] else os.path.dirname(item['path']))
            page.resources.local.browse()
            if not item['directory']:
                local = page.resources.local
                for iid, path in local.items.items():
                    if str(path) == item['path']:
                        local.files.selection_set(iid)
                        local.files.focus(iid)
                        local.files.see(iid)
                        break
        self.window.withdraw()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.window.after_cancel(self.timer)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
