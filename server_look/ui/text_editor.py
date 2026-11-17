"""Independent plain-text windows; worker threads only communicate through queues."""
import queue
import threading
from server_look.localization.localized_ui import tk, ttk, messagebox
from server_look.remote.file_editor import edit_file


class EditorManager:
    def __init__(self, page):
        self.page = page
        self.windows = []

    def open(self, path, remote=False):
        if remote and not self.page.connection:
            return
        for editor in self.windows:
            if (editor.path == str(path) and editor.remote == remote
                    and (not remote or (editor.connection is self.page.connection
                                        and editor.generation == self.page.generation))):
                editor.window.deiconify()
                editor.window.lift()
                return
        editor = TextEditor(self, str(path), remote)
        self.windows.append(editor)

    def close_all(self):
        for editor in list(self.windows):
            if not editor.close():
                return False
        return True


class TextEditor:
    def __init__(self, manager, path, remote):
        self.manager, self.page = manager, manager.page
        self.path, self.remote = path, remote
        self.connection, self.generation = self.page.connection, self.page.generation
        self.document = None
        self.baseline = ''
        self.busy = False
        self.closed = False
        self.close_after_save = False
        self.events = queue.Queue()
        self.window = tk.Toplevel(self.page.root)
        self.window.title(('服务器文本编辑 · ' if remote else '本地文本编辑 · ') + path)
        self.window.geometry('1000x720')
        self.window.minsize(620, 400)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        toolbar = ttk.Frame(self.window, padding=6)
        toolbar.pack(fill='x')
        for label, callback in [('保存 (Ctrl+S)', self.save), ('撤销 (Ctrl+Z)', lambda: self.edit('<<Undo>>')),
                                ('重做 (Ctrl+Y)', lambda: self.edit('<<Redo>>')),
                                ('剪切', lambda: self.edit('<<Cut>>')), ('复制', lambda: self.edit('<<Copy>>')),
                                ('粘贴', lambda: self.edit('<<Paste>>'))]:
            ttk.Button(toolbar, text=label, command=callback).pack(side='left', padx=2)
        area = ttk.Frame(self.window)
        area.pack(fill='both', expand=True)
        self.text = tk.Text(area, undo=True, autoseparators=True, maxundo=-1, wrap='none')
        vertical = ttk.Scrollbar(area, command=self.text.yview)
        horizontal = ttk.Scrollbar(area, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.text.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.status = tk.StringVar(master=self.window, value='正在读取文件…')
        ttk.Label(self.window, textvariable=self.status, padding=6).pack(fill='x')
        self.text.bind('<<Modified>>', self.changed)
        self.text.bind('<Control-s>', self.save)
        self.text.bind('<Control-S>', self.save)
        self.text.bind('<Control-z>', lambda event: self.edit('<<Undo>>'))
        self.text.bind('<Control-y>', lambda event: self.edit('<<Redo>>'))
        self.text.bind('<Control-a>', self.select_all)
        self.start('load')
        self.poll_job = self.window.after(80, self.poll)

    def edit(self, action):
        if not self.busy:
            self.text.event_generate(action)
        return 'break'

    def select_all(self, event=None):
        self.text.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def content(self):
        return self.text.get('1.0', 'end-1c')

    def dirty(self):
        return self.document is not None and self.content() != self.baseline

    def changed(self, event=None):
        if self.text.edit_modified():
            self.window.title(('* ' if self.dirty() else '') + ('服务器文本编辑 · ' if self.remote else '本地文本编辑 · ') + self.path)
            self.text.edit_modified(False)

    def start(self, action, **options):
        self.busy = True
        self.text.configure(state='disabled')
        def work():
            try:
                if self.remote:
                    result = self.connection.request('edit_file', options=dict(path=self.path, **options))
                else:
                    result = edit_file(self.path, **options)
                self.events.put((action, result, None))
            except Exception as exc:
                self.events.put((action, None, str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            action, result, error = self.events.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            self.text.configure(state='normal')
            if error:
                self.close_after_save = False
                self.status.set(error)
                messagebox.showerror('文本编辑失败', error, parent=self.window)
                if action == 'load':
                    self.destroy()
                    return
            elif action == 'load':
                self.document = result
                self.baseline = result['text']
                self.text.insert('1.0', self.baseline)
                self.text.edit_reset()
                self.text.edit_modified(False)
                self.status.set(result['encoding'] + ' · Ctrl+S 保存 · Ctrl+Z 撤销 · Ctrl+Y 重做')
                self.text.focus_set()
            else:
                self.document['digest'] = result['digest']
                self.baseline = self.content()
                self.text.edit_modified(True)
                self.status.set('已保存 · ' + self.document['encoding'])
                if self.close_after_save:
                    self.destroy()
                    return
        self.poll_job = self.window.after(80, self.poll)

    def save(self, event=None):
        if self.busy or self.document is None:
            return 'break'
        if self.remote and (self.page.readonly.get() or self.page.connection is not self.connection or self.page.generation != self.generation):
            self.close_after_save = False
            messagebox.showwarning('无法保存', '只读模式或连接已改变，请保留内容并重新打开文件。', parent=self.window)
            return 'break'
        self.status.set('正在保存…')
        self.start('save', text=self.content(), **{key: self.document[key] for key in ('encoding', 'newline', 'digest')})
        return 'break'

    def close(self):
        if self.busy:
            messagebox.showinfo('正在操作', '文件正在读取或保存，请完成后再关闭。', parent=self.window)
            return False
        if self.dirty():
            answer = messagebox.askyesnocancel('保存修改？', '当前内容尚未保存，是否保存后关闭？', parent=self.window)
            if answer is None:
                return False
            if answer:
                self.close_after_save = True
                self.save()
                return False
        self.destroy()
        return True

    def destroy(self):
        self.closed = True
        self.window.after_cancel(self.poll_job)
        self.window.destroy()
        self.manager.windows.remove(self)
