"""A multiline Python window using the interpreter in the current shell."""
from pathlib import Path
from tkinter import filedialog
from server_look.localization.localized_ui import tk, ttk, messagebox
from server_look.transport.terminal import python_command
from server_look.ui.text_actions import bind_text_menu
from server_look.ui.text_indent import bind_indentation


class ContextPythonWindow:
    def __init__(self, panel, item, standalone=False):
        import pyte
        from server_look.transport.terminal_screen import TerminalScreen
        self.panel, self.item = panel, item
        self.standalone = standalone
        self.path, self.baseline = None, ''
        self.active, self.closing = True, False
        self.exit_job = None
        self.window = tk.Toplevel(panel.frame)
        self.window.title('Python 脚本编辑 · ' + ('服务器环境' if standalone else '当前 Shell / 容器环境'))
        self.window.geometry('1050x800')
        self.window.minsize(700, 500)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.status = tk.StringVar(value='Shift+F10 运行 · Alt+Shift+E 运行选中代码 · Ctrl+S 保存本地 .py')
        ttk.Label(self.window, textvariable=self.status).pack(fill='x', padx=8, pady=6)
        bar = ttk.Frame(self.window)
        bar.pack(fill='x', padx=8, pady=4)
        for label, callback in [('打开本地 .py', self.open_file), ('保存 Ctrl+S', self.save),
                                ('运行 Shift+F10', self.execute), ('运行选中 Alt+Shift+E', self.execute_selection),
                                ('中断', lambda: self.send('\x03')), ('查找 Ctrl+F', self.show_search),
                                ('关闭 Python', self.close)]:
            ttk.Button(bar, text=label, command=callback).pack(side='left', padx=2)
        ttk.Label(self.window, text='Tab 缩进 4 格 · Shift+Tab 回退 4 格 · Ctrl+/ 注释/取消注释 · F5 / Ctrl+Enter 也可运行').pack(fill='x', padx=8)
        self.search_bar = ttk.Frame(self.window)
        self.search_query = tk.StringVar(master=self.window)
        self.search_status = tk.StringVar(master=self.window)
        self.search_entry = ttk.Entry(self.search_bar, textvariable=self.search_query)
        self.search_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(self.search_bar, text='查找下一个', command=self.find_text).pack(side='left')
        ttk.Label(self.search_bar, textvariable=self.search_status).pack(side='left')
        ttk.Button(self.search_bar, text='关闭查找', command=lambda: self.search_bar.pack_forget()).pack(side='left')
        self.search_entry.bind('<Return>', self.find_text)
        self.panes = ttk.Panedwindow(self.window, orient='vertical')
        self.panes.pack(fill='both', expand=True, padx=8, pady=6)
        source = ttk.Labelframe(self.panes, text='Python 脚本（本地编辑，服务器执行）')
        results = ttk.Labelframe(self.panes, text='运行结果（只读）')
        self.panes.add(source, weight=3)
        self.panes.add(results, weight=1)
        self.editor = self.text_area(source, 26, undo=True)
        self.output = self.text_area(results, 9, undo=False)
        self.output.configure(state='disabled')
        self.screen = TerminalScreen(110, 30, history=1000)
        self.screen.write_process_input = self.send
        self.stream = pyte.Stream(self.screen)
        bind_text_menu(self.editor)
        self.editor.bind('<Control-Return>', self.execute)
        bind_indentation(self.editor)
        self.editor.bind('<Control-a>', self.select_all)
        self.editor.bind('<Control-y>', lambda event: self.edit('<<Redo>>'))
        self.editor.bind('<Control-z>', lambda event: self.edit('<<Undo>>'))
        self.editor.tag_configure('search_match', background='#ffe08a', foreground='#171717')
        self.window.bind('<F5>', self.execute)
        self.window.bind('<Shift-F10>', self.execute)
        self.window.bind('<Alt-Shift-KeyPress-E>', self.execute_selection)
        self.window.bind('<Alt-Shift-KeyPress-e>', self.execute_selection)
        self.window.bind('<Control-s>', self.save)
        self.window.bind('<Control-f>', self.show_search)
        self.window.bind('<Control-o>', self.open_file)
        input_bar = ttk.Frame(self.window)
        input_bar.pack(fill='x', padx=8, pady=(0, 8))
        ttk.Label(input_bar, text='程序输入（用于 input()）：').pack(side='left')
        self.stdin = ttk.Entry(input_bar)
        self.stdin.pack(side='left', fill='x', expand=True)
        bind_text_menu(self.stdin)
        self.stdin.bind('<Return>', self.submit_input)
        ttk.Button(input_bar, text='发送输入', command=self.submit_input).pack(side='left')
        self.editor.focus_set()

    @staticmethod
    def text_area(parent, height, undo):
        text = tk.Text(parent, wrap='none', height=height, undo=undo, autoseparators=True,
                       maxundo=-1, font=('Consolas', 11))
        vertical = ttk.Scrollbar(parent, command=text.yview)
        horizontal = ttk.Scrollbar(parent, orient='horizontal', command=text.xview)
        text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        text.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        return text

    def send(self, text):
        page = self.panel.page
        if (self.active and not self.item['ended'] and not page.readonly.get()
                and self.item['connection'] is page.connection
                and self.item['generation'] == page.generation):
            return self.panel.transmit(self.item, text, track=False)
        self.status.set('Python 已结束、连接已改变或当前为只读模式；代码仍可编辑和保存')
        return False

    def execute(self, event=None):
        if self.active and not self.closing:
            self.send(python_command(self.editor.get('1.0', 'end-1c')))
        return 'break'

    def execute_selection(self, event=None):
        if self.editor.tag_ranges('sel') and not self.closing:
            self.send(python_command(self.editor.get('sel.first', 'sel.last')))
        return 'break'

    def submit_input(self, event=None):
        if self.send(self.stdin.get() + '\r'):
            self.stdin.delete(0, 'end')
        return 'break'

    def select_all(self, event=None):
        self.editor.tag_add('sel', '1.0', 'end-1c')
        return 'break'

    def edit(self, action):
        self.editor.event_generate(action)
        return 'break'

    def show_search(self, event=None):
        self.search_bar.pack(fill='x', padx=8, before=self.panes)
        self.search_entry.focus_set()
        return 'break'

    def find_text(self, event=None):
        previous = self.editor.tag_ranges('search_match')
        start = str(previous[-1]) if previous else '1.0'
        self.editor.tag_remove('search_match', '1.0', 'end')
        query = self.search_query.get()
        count = tk.IntVar(master=self.window)
        match = self.editor.search(query, start, exact=True, count=count) if query else ''
        if match:
            self.editor.tag_add('search_match', match, match + '+' + str(count.get()) + 'c')
            self.editor.see(match)
        self.search_status.set('已找到 ' + match if match else '未找到')
        return 'break'

    def dirty(self):
        return self.editor.get('1.0', 'end-1c') != self.baseline

    def save(self, event=None):
        path = self.path or filedialog.asksaveasfilename(parent=self.window, defaultextension='.py',
                                                       filetypes=[('Python', '*.py'), ('所有文件', '*.*')])
        if not path:
            return False
        try:
            content = self.editor.get('1.0', 'end-1c')
            Path(path).write_text(content, encoding='utf-8')
        except OSError as exc:
            messagebox.showerror('保存失败', str(exc), parent=self.window)
            return False
        self.path, self.baseline = path, content
        self.status.set('已保存本地脚本：' + str(path))
        return True

    def confirm_saved(self):
        if self.dirty():
            answer = messagebox.askyesnocancel('保存脚本？', '脚本尚未保存，是否保存到本机？', parent=self.window)
            if answer is None or (answer and not self.save()):
                return False
        return True

    def open_file(self, event=None):
        if not self.confirm_saved():
            return 'break'
        path = filedialog.askopenfilename(parent=self.window, filetypes=[('Python', '*.py'), ('所有文件', '*.*')])
        if path:
            try:
                content = Path(path).read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError) as exc:
                messagebox.showerror('打开失败', str(exc), parent=self.window)
                return 'break'
            self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', content)
            self.editor.edit_reset()
            self.path, self.baseline = path, content
            self.status.set('本地脚本：' + str(path) + ' · 在服务器当前 Python 会话执行')
        return 'break'

    def feed(self, text):
        self.stream.feed(text)
        lines = [''.join(row[x].data for x in range(self.screen.columns)).rstrip()
                 for row in self.screen.history.top]
        lines.extend(line.rstrip() for line in self.screen.display)
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', '\n'.join(lines).rstrip() + '\n')
        self.output.configure(state='disabled')
        self.output.see('end')

    def close(self):
        if self.closing:
            return False
        if not self.confirm_saved():
            return False
        if self.standalone:
            self.panel.tabs.select(self.item['frame'])
            self.panel.close_current()
            return True
        if not self.active:
            self.destroy()
        elif not self.closing:
            self.closing = True
            self.status.set('正在中断并退出 Python；如程序不响应中断，可关闭原 Shell 会话')
            self.send('\x03')
            # Wait for the PTY to process SIGINT before sending the exit statement.
            self.exit_job = self.window.after(200, self.request_exit)

    def request_exit(self):
        self.exit_job = None
        self.send('raise SystemExit\r')

    def finish(self):
        self.active = False
        self.status.set('Python 已退出，可以返回原 Shell；输出和代码仍可复制')
        if self.closing:
            self.destroy()

    def destroy(self):
        self.active = False
        if self.exit_job is not None:
            self.window.after_cancel(self.exit_job)
            self.exit_job = None
        if self.window.winfo_exists():
            self.window.destroy()
