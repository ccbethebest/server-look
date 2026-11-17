"""Per-server command workspace with independent shell and Python PTYs."""
import queue
import threading
from tkinter import font as tkfont
from server_look.localization.localized_ui import tk, ttk, messagebox
from server_look.transport.terminal import TerminalSession, python_command
from server_look.transport.ssh_keys import detect_keys, ensure_key, configure_key, check_key


class CommandPanel:
    def __init__(self, page):
        self.page = page
        self.frame = ttk.Frame(page.tabs)
        page.tabs.add(self.frame, text='命令行控制')
        self.sessions = {}
        self.serial = 0
        self.jobs = queue.Queue()
        self.key_busy = False
        bar = ttk.Frame(self.frame)
        bar.pack(fill='x', pady=6)
        self.actions = []
        for title, command in [('新建命令行', self.new_shell), ('新建 Python', self.new_python),
                               ('关闭当前会话', self.close_current), ('密钥检测', lambda: self.key_action('detect')),
                               ('密钥生成', lambda: self.key_action('generate')), ('公钥配置', lambda: self.key_action('configure'))]:
            widget = ttk.Button(bar, text=title, command=command)
            widget.pack(side='left', padx=3)
            self.actions.append(widget)
        self.notice = tk.StringVar(value='连接服务器后可新建多个命令行或 Python 会话')
        ttk.Label(self.frame, textvariable=self.notice, style='Muted.TLabel').pack(fill='x')
        self.tabs = ttk.Notebook(self.frame)
        self.tabs.pack(fill='both', expand=True)
        self.poll_job = page.root.after(50, self.poll)
        self.closed = False

    def allowed(self):
        if self.page.readonly.get():
            messagebox.showwarning('命令行控制', '只读模式下不可执行命令或配置公钥', parent=self.frame)
            return False
        if not self.page.connection:
            messagebox.showwarning('命令行控制', '请先连接服务器', parent=self.frame)
            return False
        return True

    def new_shell(self):
        self.new_session(False)

    def new_python(self):
        self.new_session(True)

    def new_session(self, python):
        if not self.allowed():
            return
        import pyte
        from server_look.transport.terminal_screen import TerminalScreen
        self.serial += 1
        frame = ttk.Frame(self.tabs)
        self.tabs.add(frame, text=f'{"Python" if python else "Shell"} {self.serial}')
        self.tabs.select(frame)
        output = tk.Text(frame, wrap='none', height=24, font=('Consolas', 10), undo=False)
        scroll = ttk.Scrollbar(frame, command=output.yview)
        scroll.pack(side='right', fill='y')
        output.configure(yscrollcommand=scroll.set)
        output.pack(fill='both', expand=True)
        screen = TerminalScreen(100, 28, history=1000)
        stream = pyte.Stream(screen)
        session = TerminalSession(self.page.connection, python=python)
        item = {'frame': frame, 'output': output, 'screen': screen, 'stream': stream,
                'session': session, 'ready': False, 'ended': False}
        # pyte answers terminal status queries through the same SSH input queue.
        screen.write_process_input = session.send
        self.sessions[str(frame)] = item
        output.bind('<KeyPress>', lambda event: self.keypress(event, item))
        output.bind('<<Paste>>', lambda event: self.paste(item))
        output.bind('<Control-Shift-C>', lambda event: self.copy(item))
        output.bind('<Control-Shift-V>', lambda event: self.paste(item))
        output.bind('<Button-1>', lambda event: output.focus_set())
        output.bind('<Configure>', lambda event: self.resize(item))
        if python:
            editor_bar = ttk.Frame(frame)
            editor_bar.pack(fill='x')
            ttk.Label(editor_bar, text='Python 多行代码（Ctrl+Enter 执行，变量保留）').pack(side='left')
            editor = tk.Text(frame, height=6, wrap='none', font=('Consolas', 10), undo=True)
            editor.pack(fill='x')
            item['editor'] = editor
            ttk.Button(editor_bar, text='执行代码', command=lambda: self.execute_cell(item)).pack(side='right')
            editor.bind('<Control-Return>', lambda event: self.execute_cell(item))
        self.notice.set('正在打开会话…')
        app = getattr(self.page.root.winfo_toplevel(), '_serverlook_app', None)
        if app:
            app.retheme()
        output.focus_set()

    def send(self, item, text):
        if item['ready'] and not item['ended'] and not self.page.readonly.get():
            try:
                item['session'].send(text)
            except queue.Full:
                self.notice.set('输入队列已满，请稍后重试')
        return 'break'

    def keypress(self, event, item):
        if event.state & 4:
            if event.keysym.lower() == 'v':
                return self.paste(item)
            if event.keysym.lower() == 'c' and item['output'].tag_ranges('sel'):
                return self.copy(item)
            if len(event.keysym) == 1 and 'a' <= event.keysym.lower() <= 'z':
                return self.send(item, chr(ord(event.keysym.lower()) - 96))
        keys = {'Return': '\r', 'BackSpace': '\x7f', 'Tab': '\t', 'Escape': '\x1b',
                'Up': '\x1b[A', 'Down': '\x1b[B', 'Right': '\x1b[C', 'Left': '\x1b[D',
                'Home': '\x1b[H', 'End': '\x1b[F', 'Delete': '\x1b[3~',
                'Prior': '\x1b[5~', 'Next': '\x1b[6~'}
        text = keys.get(event.keysym, event.char)
        if text:
            self.send(item, text)
        return 'break'

    def copy(self, item):
        widget = item['output']
        if widget.tag_ranges('sel'):
            widget.clipboard_clear()
            widget.clipboard_append(widget.get('sel.first', 'sel.last'))
        return 'break'

    def paste(self, item):
        try:
            text = item['output'].clipboard_get()
        except tk.TclError:
            return 'break'
        if '\n' in text or '\r' in text:
            if not messagebox.askyesno('粘贴多行命令', '剪贴板包含多行，粘贴后可能立即执行。是否继续？', parent=self.frame):
                return 'break'
        return self.send(item, text)

    def execute_cell(self, item):
        return self.send(item, python_command(item['editor'].get('1.0', 'end-1c')))

    def resize(self, item):
        output = item['output']
        font = tkfont.Font(font=output.cget('font'))
        columns = max(20, (output.winfo_width() - 24) // max(1, font.measure('M')))
        rows = max(5, (output.winfo_height() - 20) // max(1, font.metrics('linespace')))
        item['screen'].resize(lines=rows, columns=columns)
        item['session'].resize(columns, rows)

    def render(self, item):
        screen, output = item['screen'], item['output']
        # A bounded scrollback plus the live PTY screen, including cursor position.
        history = [''.join(line[x].data for x in range(screen.columns)) for line in screen.history.top]
        output.delete('1.0', 'end')
        output.insert('1.0', '\n'.join(history + screen.display))
        output.mark_set('insert', f'{len(history) + screen.cursor.y + 1}.{screen.cursor.x}')
        output.see('insert')

    def poll(self):
        if self.closed:
            return
        for item in list(self.sessions.values()):
            if item['ended']:
                continue
            try:
                self.poll_session(item)
            except Exception as exc:
                item['ended'] = True
                item['session'].close()
                self.notice.set(f'终端显示失败，请新建会话：{exc}')
        while not self.jobs.empty():
            self.key_result(*self.jobs.get_nowait())
        self.poll_job = self.page.root.after(50, self.poll)

    def poll_session(self, item):
        dirty = False
        for _ in range(32):
            try:
                kind, value = item['session'].events.get_nowait()
            except queue.Empty:
                break
            if kind == 'ready':
                item['ready'] = True
                self.notice.set('会话已连接 · Ctrl+C 中断 · Ctrl+Shift+C/V 复制粘贴')
                self.resize(item)
            elif kind == 'data':
                item['stream'].feed(value)
                dirty = True
            else:
                item['ended'] = True
                self.notice.set(value)
                break
        if dirty:
            self.render(item)

    def key_action(self, action):
        if self.key_busy:
            return
        if action == 'configure' and not self.allowed():
            return
        pairs = detect_keys()
        if action == 'detect' or (action == 'generate' and pairs):
            title = '密钥检测' if action == 'detect' else '密钥生成'
            result = ('本机已存在 SSH 密钥对' if action == 'detect' else '已拥有密钥，无需生成') if pairs else '本机未检测到完整 SSH 密钥对'
            if pairs:
                result += '\n' + '\n\n'.join(self.key_locations(path) for path in pairs)
            messagebox.showinfo(title, result, parent=self.frame)
            return
        if action == 'configure' and not pairs:
            messagebox.showwarning('公钥配置', '请先点击密钥生成', parent=self.frame)
            return
        try:
            public_key = pairs[0].read_text(encoding='utf-8').strip() if action == 'configure' else None
        except (OSError, UnicodeError) as exc:
            messagebox.showerror('SSH 密钥', str(exc), parent=self.frame)
            return
        self.start_key_job(action, self.page.generation, self.page.connection, public_key)

    @staticmethod
    def key_locations(path):
        return f'公钥：{path}\n私钥：{path.with_suffix("")}'

    def start_key_job(self, action, generation, connection, public_key):
        self.key_busy = True
        self.notice.set('正在处理密钥…')
        def work():
            try:
                if action == 'generate':
                    result = '本机密钥已就绪\n' + self.key_locations(ensure_key())
                elif action == 'configure':
                    result = check_key(connection, public_key)
                else:
                    configure_key(connection, public_key)
                    result = '公钥已添加，已配对：~/.ssh/authorized_keys'
                error = False
            except Exception as exc:
                result = str(exc)
                error = True
            self.jobs.put((action, generation, connection, public_key, result, error))
        threading.Thread(target=work, daemon=True).start()

    def key_result(self, action, generation, connection, public_key, result, error):
        self.key_busy = False
        if generation != self.page.generation or (action != 'generate' and connection is not self.page.connection):
            return
        if error:
            self.notice.set(result)
            messagebox.showerror('SSH 密钥', result, parent=self.frame)
            return
        if action == 'configure':
            if result:
                result = '已配对：服务器 ~/.ssh/authorized_keys 已添加本机公钥'
            else:
                self.notice.set('服务器尚未添加本机公钥')
                if not self.allowed():
                    return
                if not messagebox.askyesno('是否添加公钥', '服务器 ~/.ssh/authorized_keys 尚未添加本机公钥。\n是否将本机公钥追加到该文件末尾？', parent=self.frame):
                    self.notice.set('已取消添加公钥')
                    return
                if generation != self.page.generation or connection is not self.page.connection or not self.allowed():
                    return
                self.start_key_job('install', generation, connection, public_key)
                return
        self.notice.set(result)
        messagebox.showinfo('SSH 密钥', result, parent=self.frame)

    def close_current(self):
        item = self.sessions.pop(self.tabs.select(), None)
        if item:
            item['session'].close()
            item['frame'].destroy()

    def disconnect(self):
        for item in self.sessions.values():
            item['session'].close()
            item['ended'] = True
        self.notice.set('连接服务器后可新建多个命令行或 Python 会话')

    def close(self):
        self.closed = True
        self.disconnect()
        self.page.root.after_cancel(self.poll_job)
