"""Two-pane mapping browser; directory IO stays off the Tk thread."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path, PurePosixPath
import queue
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import filedialog, ttk
from server_look.mapping.mapping_rows import direction_label, server_label
from server_look.ui.table_sort import enable_sort


def local_listing(path):
    entries = []
    with os.scandir(path) as children:
        for child in children:
            info = child.stat(follow_symlinks=False)
            entries.append(dict(name=child.name,path=child.path,is_dir=child.is_dir(follow_symlinks=False),
                                link=child.is_symlink() or os.path.isjunction(child.path),size=info.st_size,
                                modified=datetime.fromtimestamp(info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')))
    return dict(path=str(Path(path)),entries=entries)


class DirectoryPane:
    def __init__(self, browser, parent, location, connection, source):
        self.browser, self.connection, self.source = browser, connection, source
        self.kind = Path if location['server']=='local' else PurePosixPath
        self.root = self.current = self.kind(location['path'])
        self.closed = self.loading = False
        self.pending_root = None
        self.cache, self.items = {}, {}
        self.events = queue.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1)
        box = ttk.LabelFrame(parent,text=('来源 · ' if source else '目标 · ')+server_label(location['server']),padding=8)
        box.pack(side='left',fill='both',expand=True,padx=4)
        bar = ttk.Frame(box)
        bar.pack(fill='x')
        ttk.Button(bar,text='↑',width=3,command=lambda:self.browse(self.current.parent,change_root=True)).pack(side='left')
        self.path = tk.StringVar(value=str(self.root))
        entry = ttk.Entry(bar,textvariable=self.path)
        entry.pack(side='left',fill='x',expand=True,padx=5)
        entry.bind('<Return>',lambda event:self.browse(self.path.get(),change_root=True))
        ttk.Button(bar,text='刷新',command=self.refresh).pack(side='right')
        chooser = ttk.Frame(box)
        chooser.pack(fill='x',pady=(6,0))
        ttk.Button(chooser,text='选择文件夹',padding=(10,5),command=self.choose_folder).pack(side='left')
        if self.kind is Path:
            drives = [f'{letter}:/' for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' if Path(f'{letter}:/').is_dir()]
            ttk.Label(chooser,text='磁盘').pack(side='left',padx=(10,4))
            self.drive = ttk.Combobox(chooser,values=drives,state='readonly',width=8)
            self.drive.pack(side='left')
            self.drive.set(self.current.anchor)
            self.drive.bind('<<ComboboxSelected>>',lambda event:self.browse(self.drive.get(),change_root=True))
        self.tree = ttk.Treeview(box,columns=('name','size','modified'),show='headings',selectmode='extended')
        for key,title,width in [('name','名称',220),('size','大小 / 字节',95),('modified','修改时间',145)]:
            self.tree.heading(key,text=title)
            self.tree.column(key,width=width,minwidth=60)
        self.tree.pack(fill='both',expand=True,pady=8)
        enable_sort(self.tree)
        scroll = ttk.Scrollbar(self.tree,command=self.tree.yview)
        scroll.pack(side='right',fill='y')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<Double-1>',self.enter)
        self.tree.bind('<Button-3>',self.context)
        self.tree.bind('<Control-a>',self.select_all)
        self.status = tk.StringVar()
        ttk.Label(box,textvariable=self.status).pack(anchor='w')
        self.timer = self.tree.after(60,self.poll)
        self.browse(self.root)

    def choose_folder(self):
        if self.loading:
            return
        if self.connection:
            from server_look.files.remote_directory_dialog import RemoteDirectoryDialog
            RemoteDirectoryDialog(self.tree.winfo_toplevel(),self.connection,str(self.current),
                                  lambda path:self.browse(path,change_root=True))
        else:
            path = filedialog.askdirectory(parent=self.tree.winfo_toplevel(),initialdir=str(self.current))
            if path:
                self.browse(path,change_root=True)

    def browse(self,path,refresh=False,change_root=False):
        if self.closed or self.loading:
            return
        if change_root and self.browser.owner.running:
            self.status.set('请等待当前映射传输完成后修改目录')
            return
        path = self.kind(path)
        if not path.is_absolute() or '..' in path.parts or (not change_root and not path.is_relative_to(self.root)):
            self.status.set('请在此映射目录内浏览')
            self.path.set(str(self.current))
            return
        self.pending_root = path if change_root else None
        key = str(path)
        if not refresh and key in self.cache:
            self.show(self.cache[key])
            return
        self.loading = True
        self.status.set('正在读取目录…')
        def work():
            try:
                data = self.connection.request('list_directory',path=key) if self.connection else local_listing(key)
                self.events.put((True,data))
            except Exception as exc:
                self.events.put((False,str(exc)))
        self.executor.submit(work)

    def show(self,data):
        current = self.kind(data['path'])
        if self.pending_root is not None:
            self.root = current
            self.pending_root = None
            index = 0 if self.source else 1
            self.browser.record['locations'][index]['path'] = str(current)
            owner = self.browser.owner
            record = owner.rows.get(self.browser.record['id'])
            if record:
                record['locations'][index]['path'] = str(current)
                owner.render(record['id'])
        if not current.is_relative_to(self.root):
            self.status.set('目录解析后超出映射范围，请选择实际目录路径')
            return
        self.current = current
        self.path.set(str(self.current))
        self.cache[str(self.current)] = data
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        for item in sorted(data['entries'],key=lambda row:(not row['is_dir'],row['name'].casefold())):
            prefix = '▸ ' if item['is_dir'] else ''
            iid = self.tree.insert('','end',values=(prefix+item['name'],'—' if item['is_dir'] else item['size'],item.get('modified','')))
            self.items[iid] = item
        self.tree.sorting.refreshed()
        self.status.set(f'{len(self.items)} 项'+('（列表已截断，整目录映射仍处理全部内容）' if data.get('truncated') else ''))

    def poll(self):
        try:
            success,data = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.loading = False
            if success:
                self.show(data)
            else:
                self.pending_root = None
                self.path.set(str(self.current))
                self.status.set('读取失败：'+data)
        self.timer = self.tree.after(80,self.poll)

    def refresh(self):
        self.cache.clear()
        self.browse(self.current,True)

    def enter(self,event=None):
        selected = self.tree.selection()
        if selected:
            item = self.items[selected[0]]
            if item['is_dir'] and not item.get('link'):
                self.browse(item['path'])

    def select_all(self,event=None):
        self.tree.selection_set(self.tree.get_children())
        return 'break'

    def map_selected(self):
        paths = tuple(self.items[iid]['path'] for iid in self.tree.selection())
        if paths:
            self.browser.owner.run(self.browser.record,paths)
        else:
            self.status.set('请先选择一个或多个文件 / 文件夹')

    def map_directory(self):
        paths = () if self.current==self.root else (str(self.current),)
        self.browser.owner.run(self.browser.record,paths)

    def context(self,event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.tree.selection_remove(*self.tree.selection())
        elif iid not in self.tree.selection():
            self.tree.selection_set(iid)
        menu = tk.Menu(self.tree,tearoff=False)
        if self.source:
            state = 'disabled' if self.loading else 'normal'
            menu.add_command(label='映射选中项 → 目标',command=self.map_selected,state=state)
            menu.add_command(label='映射当前目录全部内容 → 目标',command=self.map_directory,state=state)
            menu.add_separator()
        menu.add_command(label='全选',command=self.select_all)
        menu.add_command(label='刷新',command=self.refresh)
        menu.tk_popup(event.x_root,event.y_root)

    def close(self):
        self.closed = True
        self.tree.after_cancel(self.timer)
        self.executor.shutdown(wait=False,cancel_futures=True)


class MappingBrowser:
    def __init__(self,owner,record):
        self.owner, self.record, self.closed = owner, deepcopy(record), False
        pages = owner.connected()
        for item in record['locations']:
            if item['server']!='local' and item['server'] not in pages:
                raise ValueError('请先连接服务器：'+server_label(item['server']))
        self.window = tk.Toplevel(owner.window)
        self.window.title('映射目录 · '+direction_label(record))
        self.window.geometry('1120x540')
        self.window.minsize(820,380)
        self.window.transient(owner.window)
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        ttk.Label(self.window,text='左侧选择来源文件（Ctrl / Shift 多选，Ctrl+A 全选），右键映射到目标；文件夹双击进入。子目录保留相对来源根目录的路径。',padding=10).pack(anchor='w')
        body = ttk.Frame(self.window,padding=6)
        body.pack(fill='both',expand=True)
        self.panes = [DirectoryPane(self,body,item,pages[item['server']].connection if item['server']!='local' else None,index==0)
                      for index,item in enumerate(record['locations'])]

    def refresh(self):
        if not self.closed:
            for pane in self.panes:
                pane.refresh()

    def close(self):
        if not self.closed:
            self.closed = True
            for pane in self.panes:
                pane.close()
            self.window.destroy()
