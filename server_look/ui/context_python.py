"""A multiline Python window using the interpreter in the current shell."""
from server_look.localization.localized_ui import tk, ttk
from server_look.transport.terminal import python_command
from server_look.transport.terminal_input import encode_key
from server_look.ui.text_actions import bind_text_menu


class ContextPythonWindow:
    def __init__(self, panel, item):
        import pyte
        from server_look.transport.terminal_screen import TerminalScreen
        self.panel, self.item = panel, item
        self.active, self.closing = True, False
        self.exit_job = None
        self.window = tk.Toplevel(panel.frame)
        self.window.title('Python · 当前 Shell / 容器环境')
        self.window.geometry('960x700')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.status = tk.StringVar(value='沿用当前 Shell 的解释器、目录和环境 · Ctrl+Enter 执行多行代码')
        ttk.Label(self.window, textvariable=self.status).pack(fill='x', padx=8, pady=6)
        self.output = tk.Text(self.window, wrap='none', font=('Consolas', 11), height=22)
        self.output.pack(fill='both', expand=True, padx=8)
        self.screen = TerminalScreen(110, 30, history=1000)
        self.screen.write_process_input = self.send
        self.stream = pyte.Stream(self.screen)
        self.output.bind('<KeyPress>', self.keypress)
        self.output.bind('<<Paste>>', self.paste)
        self.output.bind('<Button-3>', self.paste)
        bar = ttk.Frame(self.window)
        bar.pack(fill='x', padx=8, pady=6)
        ttk.Button(bar, text='执行 Ctrl+Enter', command=self.execute).pack(side='left')
        ttk.Button(bar, text='中断 Ctrl+C', command=lambda: self.send('\x03')).pack(side='left', padx=6)
        ttk.Button(bar, text='退出 Python', command=self.close).pack(side='right')
        self.editor = tk.Text(self.window, height=10, wrap='none', undo=True, font=('Consolas', 11))
        self.editor.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        bind_text_menu(self.editor)
        self.editor.bind('<Control-Return>', self.execute)
        self.editor.focus_set()

    def send(self, text):
        if self.active and not self.item['ended']:
            return self.panel.transmit(self.item, text, track=False)
        return False

    def execute(self, event=None):
        if self.active and not self.closing:
            self.send(python_command(self.editor.get('1.0', 'end-1c')))
        return 'break'

    def keypress(self, event):
        if event.state & 4 and event.keysym.lower() == 'c' and self.output.tag_ranges('sel'):
            self.output.event_generate('<<Copy>>')
            return 'break'
        if event.state & 4 and event.keysym.lower() == 'v':
            return self.paste()
        text = encode_key(event.keysym, event.char, event.state, False)
        if text:
            self.send(text)
        return 'break'

    def paste(self, event=None):
        # Paste source into the editor so multiple lines are executed as one cell.
        try:
            self.editor.insert('insert', self.window.clipboard_get())
            self.editor.focus_set()
        except tk.TclError:
            pass
        return 'break'

    def feed(self, text):
        self.stream.feed(text)
        lines = [''.join(row[x].data for x in range(self.screen.columns)).rstrip()
                 for row in self.screen.history.top]
        lines.extend(line.rstrip() for line in self.screen.display)
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', '\n'.join(lines).rstrip() + '\n')
        self.output.see('end')

    def close(self):
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
