"""Independent editable mapping rows, with existing transfer workers."""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import queue
import threading
import uuid
from localized_ui import tk
from localized_ui import filedialog, messagebox, ttk

from directory_mapping import endpoint, load_mappings, save_mappings
from mapping_rows import expand_records, direction_label, server_label
from multi_mapping import MultiMapping


class MappingDialog:
    def __init__(self, app, page, remote=None):
        self.app, self.page = app, page
        self.records = expand_records(load_mappings())
        self.rows, self.browsers = {}, []
        self.events = queue.Queue()
        self.running = self.syncing = False
        self.mapping = None
        self.edit_widget = self.edit_timer = None
        self.button_timer = None
        self.window = win = tk.Toplevel(app.root)
        win.title('目录映射')
        win.transient(app.root)
        win.geometry('980x570')
        win.minsize(780,510)
        win.protocol('WM_DELETE_WINDOW',self.close)
        form = ttk.Frame(win,padding=14)
        form.pack(fill='both',expand=True)
        bar = ttk.Frame(form)
        bar.pack(fill='x')
        ttk.Button(bar,text='＋ 新增映射',command=self.new_record).pack(side='left')
        ttk.Label(bar,text='快捷选用历史：').pack(side='left',padx=(16,4))
        self.history = ttk.Combobox(bar,state='readonly',width=48)
        self.history.pack(side='left',fill='x',expand=True)
        self.history.bind('<<ComboboxSelected>>',self.use_history)
        ttk.Button(bar,text='历史映射查看',command=self.show_history).pack(side='right',padx=(8,0))
        self.folder_buttons = {}
        ttk.Style(win).configure('Mapping.Treeview',rowheight=38)
        self.directories = ttk.Treeview(form,style='Mapping.Treeview',columns=('direction','source','target'),show='headings',selectmode='browse',height=8)
        for key,title,width in [('direction','映射方向',240),('source','来源文件夹',320),('target','目标文件夹',320)]:
            self.directories.heading(key,text=title)
            self.directories.column(key,width=width,minwidth=140)
        self.directories.pack(fill='both',expand=True,pady=(12,6))
        scroll = ttk.Scrollbar(self.directories,command=self.directories.yview)
        scroll.pack(side='right',fill='y')
        def scrolled(first,last):
            scroll.set(first,last)
            self.position_folder_buttons()
        self.directories.configure(yscrollcommand=scrolled)
        self.directories.bind('<Configure>',lambda event:self.position_folder_buttons())
        self.directories.bind('<<TreeviewSelect>>',self.select)
        self.directories.bind('<ButtonRelease-1>',self.schedule_edit)
        self.directories.bind('<ButtonRelease-1>',lambda event:self.position_folder_buttons(),add='+')
        self.directories.bind('<Double-1>',self.open_browser)
        self.directories.bind('<Button-3>',self.context_menu)
        ttk.Label(form,text='路径右侧可选择文件夹；单击路径可手动修改；双击查看两侧目录；右键保存或取消。').pack(anchor='w')
        options = ttk.LabelFrame(form,text='选中映射的传输选项',padding=10)
        options.pack(fill='x',pady=10)
        self.relay = tk.StringVar(value=str(page.resources.local.current))
        row = ttk.Frame(options)
        row.pack(fill='x')
        ttk.Label(row,text='本机中转目录').pack(side='left')
        ttk.Entry(row,textvariable=self.relay).pack(side='left',fill='x',expand=True,padx=8)
        ttk.Button(row,text='选择文件夹…',command=self.choose_relay).pack(side='left')
        row = ttk.Frame(options)
        row.pack(fill='x',pady=(8,0))
        self.overwrite = tk.BooleanVar(value=False)
        self.direct = tk.BooleanVar(value=True)
        self.minimum = tk.StringVar(value='1')
        ttk.Checkbutton(row,text='覆盖已有文件',variable=self.overwrite).pack(side='left')
        ttk.Checkbutton(row,text='服务器之间优先直传',variable=self.direct).pack(side='left',padx=12)
        ttk.Label(row,text='低速阈值 MB/s').pack(side='left')
        ttk.Entry(row,textvariable=self.minimum,width=8).pack(side='left',padx=6)
        for var in (self.relay,self.overwrite,self.direct,self.minimum):
            var.trace_add('write',self.update_options)
        ttk.Label(options,text='直传失败或连续 15 秒低速时询问是否本机中转；关闭覆盖时仅补齐缺少文件。').pack(anchor='w',pady=(6,0))
        footer = ttk.Frame(form)
        footer.pack(fill='x')
        self.speed = tk.StringVar(value='当前传输速度：未开始')
        ttk.Label(footer,textvariable=self.speed).pack(side='left')
        ttk.Button(footer,text='一键映射',command=self.confirm_run).pack(side='right')
        self.refresh_history()
        for record in self.available_records:
            self.add_history(record)
        if not self.rows:
            self.new_record(remote=remote)
        self.timer = win.after(100,self.poll)

    def connected(self):
        return {endpoint(p.connection):p for p in self.app.pages.values()
                if p.connection and p.connection_state.get() == '连接成功'}

    def refresh_history(self):
        pages = self.connected()
        self.available_records = [record for record in self.records if all(
            item['server']=='local' or item['server'] in pages for item in record['locations'])]
        self.history.configure(values=[f'{i+1}. {direction_label(record)} · {record["locations"][0]["path"]} → {record["locations"][1]["path"]}'
                                      for i,record in enumerate(self.available_records)])
        self.history.set('')
        for iid in self.rows:
            self.render(iid)

    def use_history(self,event=None):
        index = self.history.current()
        if index >= 0:
            self.add_history(self.available_records[index])

    def add_history(self,record):
        iid = record['id']
        if iid not in self.rows:
            self.rows[iid] = deepcopy(record)
            self.directories.insert('', 'end', iid=iid)
            self.render(iid)
        self.directories.selection_set(iid)
        self.directories.see(iid)
        self.select()

    def new_record(self,remote=None):
        if self.running:
            return
        pages = self.connected()
        local = dict(server='local',path=str(self.page.resources.local.current))
        server = endpoint(self.page.connection) if self.page.connection and endpoint(self.page.connection) in pages else next(iter(pages),'local')
        target = dict(server=server,path=pages[server].resources.current or '/') if server!='local' else dict(local)
        locations = [target,local] if remote else [local,target]
        record = dict(id=uuid.uuid4().hex,name='目录映射',locations=locations,source=0,targets=[1],
                      relay=str(self.page.resources.local.current),direct=True,overwrite=False,minimum_mbps=1)
        self.add_history(record)

    def current(self):
        selection = self.directories.selection()
        return self.rows.get(selection[0]) if selection else None

    def render(self,iid):
        record = self.rows[iid]
        if iid not in self.folder_buttons:
            self.folder_buttons[iid] = [ttk.Button(self.directories,text='选择文件夹',width=12,
                command=lambda index=index,iid=iid:self.choose_row_folder(iid,index)) for index in range(2)]
        if self.button_timer is None:
            self.button_timer = self.window.after_idle(self.refresh_folder_buttons)
        saved = any(item == record for item in self.records)
        self.directories.item(iid,values=(direction_label(record)+('  ✓' if saved else ''),
            record['locations'][0]['path'],record['locations'][1]['path']))

    def select(self,event=None):
        record = self.current()
        if not record:
            return
        self.syncing = True
        self.relay.set(record.get('relay',''))
        self.overwrite.set(record.get('overwrite',False))
        self.direct.set(record.get('direct',True))
        self.minimum.set(str(record.get('minimum_mbps',1)))
        self.syncing = False

    def update_options(self,*args):
        record = self.current()
        if self.syncing or not record:
            return
        minimum = self.minimum.get()
        try:
            minimum = float(minimum)
        except ValueError:
            pass  # Keep incomplete input editable; validate before save or transfer.
        record.update(relay=self.relay.get(),overwrite=self.overwrite.get(),direct=self.direct.get(),minimum_mbps=minimum)
        self.render(record['id'])

    def choose_relay(self):
        path = filedialog.askdirectory(parent=self.window,initialdir=self.relay.get(),title='选择本机中转目录')
        if path:
            self.relay.set(path)

    def cancel_edit(self):
        if self.edit_timer:
            self.window.after_cancel(self.edit_timer)
            self.edit_timer = None
        if self.edit_widget:
            self.edit_widget.destroy()
            self.edit_widget = None

    def schedule_edit(self,event):
        if getattr(self,'double_click',False):
            self.double_click = False
            return
        self.cancel_edit()
        iid = self.directories.identify_row(event.y)
        column = self.directories.identify_column(event.x)
        if iid and column in ('#1','#2','#3'):
            self.edit_timer = self.window.after(550,lambda:self.edit_cell(iid,column))

    def edit_cell(self,iid,column):
        self.edit_timer = None
        if self.running or iid not in self.rows:
            return
        box = self.directories.bbox(iid,column)
        if not box:
            return
        record = self.rows[iid]
        frame = self.edit_widget = ttk.Frame(self.directories)
        width = box[2] if column=='#1' else box[2]-112
        frame.place(x=box[0],y=box[1],width=width,height=box[3])
        if column == '#1':
            servers = ['local',*self.connected()]
            for item in record['locations']:
                if item['server'] not in servers:
                    servers.append(item['server'])
            pairs = {f'{server_label(a)} → {server_label(b)}':(a,b) for a in servers for b in servers}
            combo = ttk.Combobox(frame,state='readonly',values=list(pairs))
            combo.pack(fill='both',expand=True)
            pair = tuple(item['server'] for item in record['locations'])
            combo.set(next(label for label,value in pairs.items() if value==pair))
            def changed(event):
                for index,server in enumerate(pairs[combo.get()]):
                    item = record['locations'][index]
                    if item['server'] != server:
                        item['server'] = server
                        if server == 'local':
                            item['path'] = str(self.page.resources.local.current)
                        else:
                            page = self.connected().get(server)
                            item['path'] = (page.resources.current or '/') if page else '/'
                self.render(iid)
                self.cancel_edit()
            combo.bind('<<ComboboxSelected>>',changed)
            combo.focus_set()
        else:
            index = int(column[1:])-2
            value = tk.StringVar(value=record['locations'][index]['path'])
            entry = ttk.Entry(frame,textvariable=value)
            entry.pack(side='left',fill='both',expand=True)
            def commit(event=None):
                record['locations'][index]['path'] = value.get().strip()
                self.render(iid)
            entry.bind('<Return>',lambda event:(commit(),self.cancel_edit()))
            value.trace_add('write',lambda *args:commit())
            entry.focus_set()
        frame.bind('<Escape>',lambda event:self.cancel_edit())

    def refresh_folder_buttons(self):
        self.button_timer = None
        self.position_folder_buttons()

    def position_folder_buttons(self):
        if not self.directories.winfo_exists():
            return
        for iid,buttons in list(self.folder_buttons.items()):
            if iid not in self.rows:
                for button in buttons:
                    button.destroy()
                del self.folder_buttons[iid]
                continue
            for index,button in enumerate(buttons):
                box = self.directories.bbox(iid,f'#{index+2}')
                if box:
                    x,y,width,height = box
                    button.place(x=x+width-112,y=y+3,width=106,height=height-6)
                else:
                    button.place_forget()

    def choose_row_folder(self,iid,index):
        if self.running or iid not in self.rows:
            return
        self.directories.selection_set(iid)
        self.select()
        self.cancel_edit()
        self.choose_folder(iid,index)

    def choose_folder(self,iid,index,value=None):
        record = self.rows[iid]
        item = record['locations'][index]
        def chosen(path):
            if iid not in self.rows:
                return
            self.rows[iid]['locations'][index]['path'] = path
            if value is not None:
                value.set(path)
            self.render(iid)
            self.cancel_edit()
        if item['server']=='local':
            path = filedialog.askdirectory(parent=self.window,initialdir=item['path'])
            if path:
                chosen(path)
        else:
            page = self.connected().get(item['server'])
            if not page:
                messagebox.showinfo('选择目录','请先连接服务器：'+server_label(item['server']),parent=self.window)
                return
            from remote_directory_dialog import RemoteDirectoryDialog
            pickers = getattr(self, 'folder_pickers', {})
            self.folder_pickers = pickers
            key = (iid, index)
            existing = pickers.get(key)
            if existing and not existing.closed and existing.window.winfo_exists():
                existing.selected = chosen
                existing.window.deiconify()
                existing.window.lift()
                return
            pickers[key] = RemoteDirectoryDialog(self.window,page.connection,item['path'],chosen)
            self.app.retheme()

    def validated(self,record):
        record = deepcopy(record)
        record['minimum_mbps'] = float(record.get('minimum_mbps',1))
        if not 0.01 <= record['minimum_mbps'] <= 100000:
            raise ValueError('低速阈值须为 0.01–100000 MB/s')
        for item in record['locations']:
            path = Path(item['path']) if item['server']=='local' else PurePosixPath(item['path'])
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('目录必须为不含 .. 的绝对路径')
        source,target = record['locations']
        if source['server']==target['server']:
            kind = Path if source['server']=='local' else PurePosixPath
            a,b = kind(source['path']),kind(target['path'])
            if a==b or a in b.parents or b in a.parents:
                raise ValueError('来源和目标不能相同或互为子目录')
        if all(item['server']!='local' for item in record['locations']):
            relay = Path(record.get('relay',''))
            if not relay.is_absolute() or not relay.is_dir():
                raise ValueError('请选择可用的本机中转目录')
        record['name'] = direction_label(record)
        return record

    def save(self):
        record = self.current()
        if not record:
            return
        try:
            record = self.validated(record)
            records = [deepcopy(item) for item in self.records if item['id'] != record['id']]+[record]
            save_mappings(records)
            self.records = records
            self.rows[record['id']] = deepcopy(record)
            self.refresh_history()
        except (ValueError,OSError) as exc:
            messagebox.showerror('保存映射',str(exc),parent=self.window)

    def remove(self):
        record = self.current()
        if record and not self.running:
            self.cancel_edit()
            self.directories.delete(record['id'])
            del self.rows[record['id']]
            self.position_folder_buttons()

    def context_menu(self,event):
        self.cancel_edit()
        item = self.directories.identify_row(event.y)
        if not item:
            return
        self.directories.selection_set(item)
        self.select()
        menu = tk.Menu(self.window,tearoff=False)
        menu.add_command(label='保存映射',command=self.save)
        menu.add_command(label='取消当前映射',command=self.remove)
        menu.add_separator()
        menu.add_command(label='查看两侧目录 / 选择文件映射',command=self.open_browser)
        menu.tk_popup(event.x_root,event.y_root)

    def show_history(self):
        from mapping_history import show_history
        show_history(self)

    def open_browser(self,event=None):
        self.double_click = event is not None
        self.cancel_edit()
        record = self.current()
        if not record:
            return
        try:
            record = self.validated(record)
            from mapping_browser import MappingBrowser
            self.browsers = [browser for browser in self.browsers
                             if not browser.closed and browser.window.winfo_exists()]
            for browser in self.browsers:
                if browser.record['id'] == record['id']:
                    browser.window.deiconify()
                    browser.window.lift()
                    return
            browser = MappingBrowser(self,record)
            self.browsers.append(browser)
            self.app.retheme()
        except (ValueError,OSError) as exc:
            messagebox.showerror('映射目录',str(exc),parent=self.window)

    def confirm_relay(self,reason):
        answer,result = threading.Event(),[]
        self.events.put(('confirm',(reason,answer,result)))
        while not answer.wait(0.1):
            self.mapping.check()
        return result[0]

    def poll(self):
        while True:
            try:
                kind,value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind=='speed':
                self.speed.set(f'当前传输速度：{value:.2f} MB/s')
            elif kind=='confirm':
                reason,answer,result = value
                result.append(messagebox.askyesno('是否本机中转','直传失败或低于阈值：\n'+reason[-500:]+'\n是否使用本机中转目录？\n'+self.active_relay,parent=self.window))
                answer.set()
            elif kind=='done':
                self.running = False
                self.speed.set('当前传输速度：已结束')
                for browser in self.browsers:
                    browser.refresh()
        self.timer = self.window.after(100,self.poll)

    def confirm_run(self):
        record = self.current()
        if self.running or not record:
            return
        source,target = record['locations']
        overwrite = '是（覆盖目标中的同名文件）' if record.get('overwrite') else '否（仅补齐缺少的文件）'
        details = (f"来源：{server_label(source['server'])} · {source['path']}\n"
                   f"目标：{server_label(target['server'])} · {target['path']}\n"
                   f"覆盖已有文件：{overwrite}\n\n是否确定开始映射？")
        if messagebox.askyesno('确认目录映射',details,parent=self.window):
            self.run(record)

    def run(self,record=None,selected=()):
        local = self.page.resources.local
        try:
            if self.running or local.active:
                raise ValueError('请等待当前传输结束')
            if record is None:
                record = self.current()
            if not record:
                raise ValueError('请先选择一条映射')
            record = self.validated(record)
            pages = self.connected()
            for index,item in enumerate(record['locations']):
                server = item['server']
                if server!='local' and server not in pages:
                    raise ValueError('请先连接服务器：'+server_label(server))
                if index==1 and server!='local' and pages[server].readonly.get():
                    raise ValueError('目标服务器为只读模式')
            self.mapping = local.transfer = mapping = MultiMapping()
            mapping.confirm_relay = self.confirm_relay
            mapping.progress = lambda speed:self.events.put(('speed',speed))
            self.active_relay = record.get('relay','')
            connections = {key:page.connection for key,page in pages.items()}
            def transfer():
                try:
                    return mapping.run_many(connections,record,selected)
                finally:
                    self.events.put(('done',None))
            self.running = True
            self.speed.set('当前传输速度：连接中…')
            local.launch(transfer,'目录映射')
            return True
        except (ValueError,OSError) as exc:
            messagebox.showerror('目录映射',str(exc),parent=self.window)
            return False

    def close(self):
        if not self.window.winfo_exists():
            return
        if self.running:
            if not messagebox.askyesno('目录映射','映射正在进行，取消传输并关闭？',parent=self.window):
                return
            self.mapping.cancel()
        self.cancel_edit()
        self.window.after_cancel(self.timer)
        if self.button_timer is not None:
            self.window.after_cancel(self.button_timer)
            self.button_timer = None
        for browser in self.browsers:
            browser.close()
        for picker in getattr(self, 'folder_pickers', {}).values():
            if not picker.closed:
                picker.close()
        self.window.destroy()
