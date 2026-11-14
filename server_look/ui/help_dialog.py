"""Offline help viewer; bundled Markdown remains readable in the source release."""
from server_look.paths import resource_root
import sys
from pathlib import Path
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import ttk
from server_look.localization.i18n import language, subscribe, tr


class HelpContent:
    def __init__(self, app, text):
        self.app, self.text = app, text
        subscribe(self)
        self.refresh_language()

    def refresh_language(self):
        if not self.text.winfo_exists():
            return
        name = 'HELP.en.md' if language() == 'en' else 'HELP.md'
        source = resource_root() / 'docs' / name
        try:
            content = source.read_text(encoding='utf-8-sig')
        except OSError:
            content = tr('帮助文件缺失。请从完整发布包重新获取客户端。')
        shortcuts = '\n'.join(f'{tr(name)}: {tr(key)}' for name, key in self.app.preferences['shortcuts'].items())
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('end', content + '\n\n' + tr('当前快捷键（以设置为准）') + '\n' + shortcuts)
        self.text.configure(state='disabled')


def show_help(app):
    if getattr(app, 'help_window', None) and app.help_window.winfo_exists():
        app.help_window.lift()
        return
    window = app.help_window = tk.Toplevel(app.root)
    window.title('帮助 · 服务器看看')
    window.geometry('850x680')
    window.transient(app.root)
    frame = ttk.Frame(window, padding=16)
    frame.pack(fill='both', expand=True)
    text = tk.Text(frame, wrap='word', font=('Microsoft YaHei UI', 10))
    scroll = ttk.Scrollbar(frame, command=text.yview)
    scroll.pack(side='right', fill='y')
    text.configure(yscrollcommand=scroll.set)
    text.pack(fill='both', expand=True)
    app.help_content = HelpContent(app, text)
    app.retheme()
