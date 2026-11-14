"""Resource summary and read-only remote file explorer widgets."""
import posixpath
import time
from collections import OrderedDict
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import ttk
from server_look.ui.ui_icons import button as icon_button
from server_look.files.local_files import LocalFiles
from server_look.ui.table_sort import enable_sort


def size_text(value):
    if value is None:
        return '—'
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
        if abs(value) < 1024:
            return f'{value:,.1f} {unit}'
        value /= 1024
    return f'{value:,.1f} EiB'


class ResourceViews:
    def __init__(self, page):
        self.page = page
        self.hardware = page.table('硬件配置', [('key', '配置项', 230), ('value', '服务器配置', 800)])
        self.hardware.localized_columns = (0,)
        self.disks = page.table('磁盘与挂载', [('mount', '挂载目录', 250), ('device', '设备 / 远程源', 300),
                                            ('type', '类型', 100), ('total', '总容量', 120),
                                            ('used', '已用', 120), ('available', '可用', 120), ('percent', '使用率', 120)])
        self.disks.bind('<Double-1>', self.open_mount)
        self.disks.tag_configure('warning', foreground='#ffdc99', background='#3b342a')
        self.disks.tag_configure('critical', foreground='#ffbdc8', background='#442b3b')
        self.frame = ttk.Frame(page.tabs, padding=10)
        page.tabs.add(self.frame, text='文件浏览')
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x', pady=(0, 10))
        icon_button(bar, text='上级', command=self.up).pack(side='left')
        self.path = tk.StringVar(value='/')
        entry = ttk.Entry(bar, textvariable=self.path)
        entry.pack(side='left', fill='x', expand=True, padx=8)
        entry.bind('<Return>', lambda event: self.browse(self.path.get(), force=True))
        icon_button(bar, text='前往 / 刷新', command=lambda: self.browse(self.path.get(), force=True)).pack(side='left')
        columns = ttk.Panedwindow(self.frame, orient='horizontal')
        columns.pack(fill='both', expand=True)
        pane = ttk.Panedwindow(columns, orient='horizontal')
        columns.add(pane, weight=3)
        self.folders = self.tree(pane, (), 'tree')
        self.folders.heading('#0', text='目录树 · 点击展开')
        self.files = self.tree(pane, ('kind', 'size', 'modified'), 'tree headings')
        self.files.localized_columns = (0,)
        self.files.configure(selectmode='extended')
        self.files.heading('#0', text='名称')
        for key, title, width in [('kind', '类型', 90), ('size', '大小', 110), ('modified', '修改时间', 175)]:
            self.files.heading(key, text=title)
            self.files.column(key, width=width, minwidth=70)
        self.files.column('#0', width=300)
        enable_sort(self.files)
        self.folders.bind('<<TreeviewOpen>>', self.expand)
        self.folders.bind('<<TreeviewSelect>>', self.select_folder)
        self.files.bind('<Double-1>', self.enter)
        self.hint = tk.StringVar(value='只读浏览 · 连接后点击“前往”，支持隐藏文件、目录和符号链接')
        ttk.Label(self.frame, textvariable=self.hint).pack(fill='x', pady=(8, 0))
        self.reset()
        self.local = LocalFiles(self, columns)

    @staticmethod
    def tree(pane, columns, show):
        frame = ttk.Frame(pane)
        pane.add(frame, weight=1 if not columns else 3)
        tree = ttk.Treeview(frame, columns=columns, show=show, selectmode='browse')
        vertical = ttk.Scrollbar(frame, command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        return tree

    def reset(self):
        if hasattr(self, 'local'):
            self.local.cancel()
        self.path.set('/')
        self.current = None
        self.target_node = None
        self.loading = False
        self.pending = None
        self.select_path = None
        self.cache = OrderedDict()
        self.nodes = {}
        self.entries = {}
        for tree in (self.folders, self.files, self.hardware, self.disks):
            tree.delete(*tree.get_children())
        node = self.folders.insert('', 'end', text='/ 服务器根目录', open=False, caption=True)
        self.nodes['/'] = node
        self.folders.insert(node, 'end', text='加载…', caption=True)
        self.hint.set('只读浏览 · 连接后点击“前往”，或展开目录树')

    def render(self, data):
        self.hardware.delete(*self.hardware.get_children())
        for key, value in data.get('hardware', {}).items():
            self.hardware.insert('', 'end', values=(key, size_text(value) if key.startswith('内存') else value))
        self.hardware.insert('', 'end', caption_columns=(0, 1), values=('NPU / GPU 设备详情', '请切换“NPU / GPU 状态”：型号、健康状态、温度、功耗、显存及运行进程'))
        self.disks.delete(*self.disks.get_children())
        for index, disk in enumerate(data.get('disks', [])):
            percent = int(disk['percent'].strip('%')) if disk['percent'].strip('%').isdigit() else 0
            self.disks.insert('', 'end', iid=str(index), values=(disk['mount'], disk['device'], disk['type'],
                              size_text(disk['total']), size_text(disk['used']), size_text(disk['available']), disk['percent']),
                              tags=('critical' if percent >= 90 else 'warning' if percent >= 80 else 'normal',))

        self.hardware.sorting.refreshed()
        self.disks.sorting.refreshed()

    def browse(self, path, node=None, force=False, select=None):
        if not self.page.connection:
            self.hint.set('请先连接服务器')
            return
        if self.loading:
            self.pending = (path, node, force, select)
            return
        self.select_path = select
        self.target_node = node
        cached = self.cache.get(path)
        if not force and cached and time.monotonic() - cached[0] < 15:
            self.cache.move_to_end(path)
            self.apply(cached[1])
            self.hint.set(self.hint.get() + ' · 目录缓存（15 秒内）；点击刷新获取最新数据')
            return
        self.loading = True
        self.hint.set('正在读取目录…')
        self.page.submit('list_directory', path=path)

    def complete(self, result, error):
        self.loading = False
        if result:
            self.cache[result['path']] = (time.monotonic(), result)
            self.cache.move_to_end(result['path'])
            while len(self.cache) > 32:
                self.cache.popitem(last=False)
        if self.pending:
            pending, self.pending = self.pending, None
            self.browse(*pending[:2], force=pending[2], select=pending[3])
        elif error:
            self.hint.set('目录读取失败：' + error.replace('\n', ' ')[:200])
        else:
            self.apply(result)

    def apply(self, result):
        path = result['path']
        self.current = path
        self.path.set(path)
        node = self.target_node or self.nodes.get(path)
        if node is None:
            node = self.folders.insert('', 'end', text=path)
        self.nodes[path] = node
        # Remove stale descendants from the path index before rebuilding this branch.
        descendants = set()
        def remember(parent):
            for child in self.folders.get_children(parent):
                descendants.add(child)
                remember(child)
        remember(node)
        self.nodes = {key: value for key, value in self.nodes.items() if value not in descendants}
        self.folders.delete(*self.folders.get_children(node))
        self.folders.item(node, open=True)
        self.files.delete(*self.files.get_children())
        self.entries = {}
        for entry in result['entries']:
            if entry['is_dir']:
                child = self.folders.insert(node, 'end', text=entry['name'])
                self.nodes[entry['path']] = child
                self.folders.insert(child, 'end', text='加载…', caption=True)
            iid = self.files.insert('', 'end', text=('▸ ' if entry['is_dir'] else '') + entry['name'],
                                   values=('目录链接' if entry['is_dir'] and entry['link'] else '目录' if entry['is_dir'] else '链接' if entry['link'] else '文件',
                                           '—' if entry['is_dir'] else size_text(entry['size']), entry['modified']))
            self.entries[iid] = entry
        self.hint.set(f"{len(result['entries'])} 项 · 只读浏览" + (' · 已达到 3000 项上限，请输入子目录路径继续' if result['truncated'] else ''))

        self.files.sorting.refreshed()
        for iid, entry in self.entries.items():
            if entry['path'] == self.select_path:
                self.files.selection_set(iid)
                self.files.focus(iid)
                self.files.see(iid)
                self.files.focus_set()
                break
        self.select_path = None

    def expand(self, event=None):
        node = self.folders.focus()
        path = next((path for path, value in self.nodes.items() if value == node), None)
        if path:
            self.browse(path, node)

    def select_folder(self, event=None):
        selected = self.folders.selection()
        path = next((path for path, value in self.nodes.items() if selected and value == selected[0]), None)
        if path and path != self.current:
            self.browse(path, selected[0])

    def enter(self, event=None):
        selected = self.files.selection()
        entry = self.entries.get(selected[0]) if selected else None
        if entry and entry['is_dir']:
            self.browse(entry['path'])

    def up(self):
        self.browse(posixpath.dirname(self.current or '/') or '/')

    def open_mount(self, event=None):
        selected = self.disks.selection()
        if selected:
            mount = self.disks.item(selected[0], 'values')[0]
            self.page.tabs.select(self.frame)
            self.browse(mount)
