"""Offline help viewer; bundled Markdown remains readable in the source release."""
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk


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
    source = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'HELP.md'
    try:
        content = source.read_text(encoding='utf-8-sig')
    except OSError:
        content = '帮助文件缺失。请从完整发布包重新获取客户端。'
    text.insert('end', content)
    text.insert('end', '\n\n当前快捷键（以设置为准）\n' + '\n'.join(f'{name}：{key}' for name, key in app.preferences['shortcuts'].items()))
    text.configure(state='disabled')
    app.retheme()
