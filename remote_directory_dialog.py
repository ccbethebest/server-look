"""Asynchronous remote folder picker reusing the page's persistent directory channel."""
from concurrent.futures import ThreadPoolExecutor
import posixpath
import queue
import tkinter as tk
from tkinter import ttk


class RemoteDirectoryDialog:
    def __init__(self, parent, connection, path, selected):
        self.connection, self.selected = connection, selected
        self.window = tk.Toplevel(parent)
        self.window.title('选择服务器目录 · 双击进入')
        self.window.geometry('640x440')
        self.window.transient(parent)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.closed, self.loading = False, False
        self.current, self.cache = None, {}
        self.events = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill='both', expand=True)
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        ttk.Button(bar, text='上一级', command=lambda: self.browse(posixpath.dirname(self.current or '/'))).pack(side='left')
        self.path = tk.StringVar(value=path or '/')
        entry = ttk.Entry(bar, textvariable=self.path)
        entry.pack(side='left', fill='x', expand=True, padx=8)
        entry.bind('<Return>', lambda event: self.browse(self.path.get()))
        ttk.Button(bar, text='刷新', command=lambda: self.browse(self.current or self.path.get(), True)).pack(side='left')
        self.tree = ttk.Treeview(frame, show='tree', selectmode='browse')
        self.tree.pack(fill='both', expand=True, pady=10)
        self.tree.bind('<Double-1>', self.enter)
        scroll = ttk.Scrollbar(self.tree, command=self.tree.yview)
        scroll.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.status = tk.StringVar()
        ttk.Label(frame, textvariable=self.status).pack(anchor='w')
        ttk.Button(frame, text='选择当前目录', command=self.choose).pack(side='right', pady=8)
        ttk.Button(frame, text='取消', command=self.close).pack(side='right', padx=8)
        self.timer = self.window.after(50, self.poll)
        self.browse(path or '/')

    def browse(self, path, refresh=False):
        if self.closed or self.loading:
            return
        path = posixpath.normpath(path.strip())
        if not path.startswith('/'):
            self.status.set('请输入服务器绝对目录')
            return
        if not refresh and path in self.cache:
            self.show(self.cache[path])
            return
        self.loading = True
        self.status.set('正在读取目录…')
        def work():
            try:
                self.events.put((True, self.connection.request('list_directory', path=path)))
            except Exception as exc:
                self.events.put((False, str(exc)))
        self.executor.submit(work)

    def show(self, data):
        self.current = data['path']
        self.path.set(self.current)
        self.cache[self.current] = data
        self.tree.delete(*self.tree.get_children())
        self.folders = {}
        for item in sorted(data['entries'], key=lambda row: row['name'].casefold()):
            if item['is_dir']:
                iid = self.tree.insert('', 'end', text='▸  ' + item['name'])
                self.folders[iid] = item['path']
        self.status.set('双击文件夹进入，再选择当前目录。' + ('目录条目过多，列表已截断；可输入完整路径。' if data.get('truncated') else ''))

    def enter(self, event=None):
        rows = self.tree.selection()
        if rows:
            self.browse(self.folders[rows[0]])

    def choose(self):
        if not self.loading and self.current is not None:
            self.selected(self.current)
            self.close()

    def poll(self):
        try:
            success, data = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.loading = False
            if success:
                self.show(data)
            else:
                self.status.set('读取失败：' + data)
        self.timer = self.window.after(80, self.poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.window.after_cancel(self.timer)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
