"""Per-server command workspace with independent shell and Python PTYs."""
import queue
import threading
import secrets
from tkinter import font as tkfont
from server_look.localization.localized_ui import tk, ttk, messagebox, Menu
from server_look.transport.terminal import TerminalSession, python_command
from server_look.transport.terminal_editor import EditorBridge, editor_setup, editor_command
from server_look.transport.terminal_input import encode_key
from server_look.transport.terminal_selection import ShellLine
from server_look.ui.text_actions import bind_text_menu, has_selection
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
        input_bar = ttk.Frame(frame)
        input_bar.pack(side='bottom', fill='x')
        input_status = tk.StringVar(value='键盘输入：点击终端启用')
        ttk.Label(input_bar, textvariable=input_status).pack(side='left', padx=4)
        output = tk.Text(frame, wrap='none', height=24, font=('Consolas', 10), undo=False)
        scroll = ttk.Scrollbar(frame, command=output.yview)
        scroll.pack(side='right', fill='y')
        output.configure(yscrollcommand=scroll.set)
        output.pack(fill='both', expand=True)
        if not python:
            command_bar = ttk.Frame(frame)
            command_bar.pack(side='bottom', fill='x', pady=4)
            ttk.Label(command_bar, text='命令输入').pack(side='left', padx=4)
            command_entry = ttk.Entry(command_bar)
            command_entry.pack(side='left', fill='x', expand=True)
        screen = TerminalScreen(100, 28, history=1000)
        stream = pyte.Stream(screen)
        session = TerminalSession(self.page.connection, python=python)
        item = {'frame': frame, 'output': output, 'screen': screen, 'stream': stream,
                'session': session, 'ready': False, 'ended': False,
                'editor_bridge': None if python else EditorBridge(secrets.token_hex(16)),
                'connection': self.page.connection, 'generation': self.page.generation,
                'input_status': input_status, 'shell_line': None if python else ShellLine()}
        # pyte answers terminal status queries through the same SSH input queue.
        screen.write_process_input = session.send
        self.sessions[str(frame)] = item
        if not python:
            item['command_entry'] = command_entry
            command_entry.bind('<Return>', lambda event: self.execute_command(item))
            command_entry.bind('<Control-c>', lambda event: None if has_selection(command_entry) else self.send(item, '\x03'))
            bind_text_menu(command_entry)
            ttk.Button(command_bar, text='执行', command=lambda: self.execute_command(item)).pack(side='left', padx=4)
            ttk.Button(command_bar, text='中断 Ctrl+C', command=lambda: self.send(item, '\x03')).pack(side='left')
            ttk.Button(command_bar, text='恢复显示 Ctrl+Q', command=lambda: self.send(item, '\x11')).pack(side='left', padx=4)
        output.bind('<KeyPress>', lambda event: self.keypress(event, item))
        output.bind('<<Paste>>', lambda event: self.paste(item))
        output.bind('<Control-Shift-C>', lambda event: self.copy(item))
        output.bind('<Control-Shift-V>', lambda event: self.paste(item))
        menu = item['text_menu'] = Menu(output, tearoff=False)
        menu.add_command(label='复制', command=lambda: self.copy(item))
        menu.add_command(label='粘贴', command=lambda: self.paste(item))
        menu.add_command(label='删除选中文字', command=lambda: self.delete_selection(item))
        output.bind('<Button-3>', lambda event: self.right_click(event, item))
        ttk.Button(input_bar, text='启用终端输入',
                   command=lambda: self.activate_terminal(item)).pack(side='right', padx=4)
        output.bind('<Button-1>', lambda event: self.activate_terminal(item))
        output.bind('<FocusIn>', lambda event: input_status.set('键盘输入已启用'))
        output.bind('<FocusOut>', lambda event: input_status.set('键盘输入：点击终端启用'))
        output.bind('<Map>', lambda event: self.activate_terminal(item, force=False))
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
            bind_text_menu(editor)
        self.notice.set('正在打开会话…')
        app = getattr(self.page.root.winfo_toplevel(), '_serverlook_app', None)
        if app:
            app.retheme()

    def activate_terminal(self, item, force=True):
        # A Text created inside a notebook may not be mapped until idle. Only
        # an explicit click/button may activate the OS window; never a timer.
        output = item['output']
        if (self.closed or not output.winfo_exists() or not output.winfo_ismapped()
                or self.tabs.select() != str(item['frame'])
                or self.page.tabs.select() != str(self.frame)):
            return
        if not force and output.focus_get() not in (None, self.page.root.winfo_toplevel()):
            # Do not steal input from an entry or another dialog. A new session
            # can take focus from controls in this command workspace.
            focus = output.focus_get()
            if not str(focus).startswith(str(self.frame) + '.'):
                return
        if force:
            output.focus_force()
        else:
            output.focus_set()

    def send(self, item, text):
        self.transmit(item, text)
        return 'break'

    def transmit(self, item, text, track=True):
        if track and item.get('python_window'):
            self.notice.set('当前 Shell 正在运行 Python，请在弹出的 Python 窗口中操作')
            item['python_window'].window.lift()
            return False
        if item['ended']:
            self.notice.set('会话已结束，请新建会话')
        elif not item['ready']:
            self.notice.set('正在连接，请等待会话连接完成后输入')
        elif self.page.readonly.get():
            self.notice.set('只读模式下不可执行命令')
        else:
            try:
                item['session'].send(text)
                if track and item.get('shell_line') is not None:
                    item['shell_line'].record(item['screen'], text)
                return True
            except queue.Full:
                self.notice.set('输入队列已满，请稍后重试')
        return False

    def execute_command(self, item):
        entry = item['command_entry']
        command = entry.get()
        if item['editor_bridge']:
            command = editor_command(command, item['editor_bridge'].token)
        if self.transmit(item, command + '\r'):
            entry.delete(0, 'end')
        return 'break'

    def keypress(self, event, item):
        if event.state & 4:
            if event.keysym.lower() == 'v':
                return self.paste(item)
            if event.keysym.lower() == 'c' and item['output'].tag_ranges('sel'):
                return self.copy(item)
        if item['output'].tag_ranges('sel') and event.keysym in ('BackSpace', 'Delete'):
            return self.delete_selection(item)
        text = encode_key(event.keysym, event.char, event.state, (1 << 5) in item['screen'].mode)
        # Readline also enables application cursor keys at a normal shell prompt.
        # Only the alternate screen indicates a fullscreen editor here.
        if (text == '\r' and item.get('shell_line') is not None
                and item['screen']._primary is None):
            line = item['shell_line']
            if line.matches(item['screen']):
                command = editor_command(line.text, item['editor_bridge'].token)
                if command != line.text:
                    text = '\x05\x15' + command + '\r'
        if text:
            self.send(item, text)
        return 'break'

    def right_click(self, event, item):
        self.activate_terminal(item)
        if not item['output'].tag_ranges('sel'):
            return self.paste(item)
        item['text_menu'].entryconfigure(2, state='normal' if self.selected_deletion(item) else 'disabled')
        try:
            item['text_menu'].tk_popup(event.x_root, event.y_root)
        finally:
            item['text_menu'].grab_release()
        return 'break'

    def selected_deletion(self, item):
        line, output = item['shell_line'], item['output']
        if line is None or not output.tag_ranges('sel') or (1 << 5) in item['screen'].mode:
            return None
        row = len(item['screen'].history.top) + item['screen'].cursor.y + 1
        first, last = output.index('sel.first'), output.index('sel.last')
        if int(first.split('.')[0]) != row or int(last.split('.')[0]) != row:
            return None
        if output.get(f'{row}.0', f'{row}.end').rstrip() != item['screen'].display[item['screen'].cursor.y].rstrip():
            return None
        start = len(output.get(f'{row}.0', first))
        end = len(output.get(f'{row}.0', last))
        return line.deletion(item['screen'], start, end)

    def delete_selection(self, item):
        deletion = self.selected_deletion(item)
        if deletion is None:
            self.notice.set('仅可删除本次输入且尚未执行的单行命令文字；历史输出可复制')
            return 'break'
        text, start, end = deletion
        # Preserve tracked state while the remote readline processes cursor keys.
        line = item['shell_line']
        if self.transmit(item, text, track=False):
            line.deleted(start, end)
            item['output'].tag_remove('sel', '1.0', 'end')
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
        if (2004 << 5) in item['screen'].mode:
            text = '\x1b[200~' + text + '\x1b[201~'
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
        prefix = ''.join(screen.buffer[screen.cursor.y][x].data
                         for x in range(min(screen.cursor.x, screen.columns)))
        column = output.tk.call('string', 'length', prefix)
        output.mark_set('insert', f'{len(history) + screen.cursor.y + 1}.{column}')
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
                self.close_python_windows(item)
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
                if item['editor_bridge']:
                    self.send(item, editor_setup(item['editor_bridge'].token) + '\r')
                    self.notice.set('会话已连接 · vim/vi 文件名打开图形编辑器 · command vim 使用原生终端')
            elif kind == 'data':
                if item['editor_bridge']:
                    for event, payload in item['editor_bridge'].feed_events(value):
                        self.bridge_event(item, event, payload)
                else:
                    item['stream'].feed(value)
                dirty = True
            else:
                item['ended'] = True
                self.close_python_windows(item)
                self.notice.set(value)
                break
        if dirty:
            self.render(item)

    def bridge_event(self, item, event, payload):
        if event == 'text':
            window = item.get('python_window')
            if window:
                window.feed(payload)
            else:
                item['stream'].feed(payload)
            return
        if (item['ended'] or self.page.readonly.get() or item['connection'] is not self.page.connection
                or item['generation'] != self.page.generation):
            return
        if event == 'python':
            if payload and not item.get('python_window'):
                from server_look.ui.context_python import ContextPythonWindow
                window = ContextPythonWindow(self, item)
                item['python_window'] = window
                item.setdefault('python_windows', []).append(window)
            elif not payload and item.get('python_window'):
                item.pop('python_window').finish()
        elif isinstance(payload, dict):
            self.page.resources.editors.open(payload['path'], remote=True, context=payload['context'])
        else:
            self.page.resources.editors.open(payload, remote=True)

    @staticmethod
    def close_python_windows(item):
        for window in item.pop('python_windows', []):
            window.destroy()
        item.pop('python_window', None)

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
        selected = str(self.tabs.select())
        item = self.sessions.pop(selected, None)
        if item:
            item['ended'] = True
            self.close_python_windows(item)
            self.tabs.forget(selected)
            item['frame'].destroy()
            item['session'].close()
            self.notice.set('当前会话已关闭')

    def disconnect(self):
        for item in self.sessions.values():
            self.close_python_windows(item)
            item['session'].close()
            item['ended'] = True
        self.notice.set('连接服务器后可新建多个命令行或 Python 会话')

    def close(self):
        self.closed = True
        self.disconnect()
        self.page.root.after_cancel(self.poll_job)
