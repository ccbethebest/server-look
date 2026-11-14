"""Small code-drawn icons; no image files, fonts, or network dependencies."""
import tkinter as tk
from tkinter import ttk

# Polylines use a consistent 18px grid.
SHAPES = {
    'mapping': [[(2, 5), (13, 5), (10, 2)], [(14, 11), (3, 11), (6, 14)]],
    'server': [[(2, 2), (14, 2), (14, 14), (2, 14), (2, 2)], [(2, 6), (14, 6)], [(2, 10), (14, 10)], [(5, 4), (6, 4)], [(5, 8), (6, 8)], [(5, 12), (6, 12)]],
    'settings': [[(8, 2), (13, 5), (13, 11), (8, 14), (3, 11), (3, 5), (8, 2)], [(6, 6), (10, 6), (10, 10), (6, 10), (6, 6)]],
    'search': [[(6, 2), (10, 4), (10, 8), (6, 10), (2, 8), (2, 4), (6, 2)], [(10, 10), (14, 14)]],
    'help': [[(4, 4), (6, 2), (10, 2), (12, 4), (12, 7), (8, 10), (8, 11)], [(8, 14), (8, 14)]],
    'add': [[(8, 3), (8, 13)], [(3, 8), (13, 8)]],
    'close': [[(4, 4), (12, 12)], [(12, 4), (4, 12)]],
    'connect': [[(5, 2), (5, 6)], [(11, 2), (11, 6)], [(3, 6), (13, 6), (13, 9), (10, 12), (6, 12), (3, 9), (3, 6)], [(8, 12), (8, 15)]],
    'refresh': [[(13, 6), (10, 3), (5, 3), (2, 6), (2, 11), (5, 14), (10, 14), (13, 11)], [(13, 2), (13, 6), (9, 6)]],
    'folder': [[(2, 5), (2, 3), (7, 3), (9, 5), (14, 5), (14, 13), (2, 13), (2, 5), (14, 5)]],
    'up': [[(3, 8), (8, 3), (13, 8)], [(8, 3), (8, 14)]],
    'upload': [[(3, 7), (8, 2), (13, 7)], [(8, 2), (8, 11)], [(2, 11), (2, 14), (14, 14), (14, 11)]],
    'download': [[(3, 6), (8, 11), (13, 6)], [(8, 2), (8, 11)], [(2, 11), (2, 14), (14, 14), (14, 11)]],
    'delete': [[(3, 4), (13, 4)], [(6, 4), (6, 2), (10, 2), (10, 4)], [(4, 4), (5, 14), (11, 14), (12, 4)], [(7, 7), (7, 11)], [(9, 7), (9, 11)]],
    'info': [[(8, 2), (13, 5), (13, 11), (8, 14), (3, 11), (3, 5), (8, 2)], [(8, 7), (8, 11)], [(8, 4), (8, 4)]],
    'stop': [[(3, 3), (13, 3), (13, 13), (3, 13), (3, 3)]],
}


def icon_for(text):
    for words, name in [(("映射",), "mapping"), (("设置",), "settings"), (("搜索",), "search"), (("帮助",), "help"), (("服务器",), "server"), (("上传",), 'upload'), (("下载",), 'download'),
                        (("删除",), 'delete'), (("上级", "↑"), 'up'),
                        (("添加",), 'add'), (("关闭", "取消", "断开"), 'close'),
                        (("刷新",), 'refresh'), (("连接",), 'connect'),
                        (("打开窗口",), 'folder'), (("原因",), 'info'),
                        (("结束", "停止"), 'stop')]:
        if any(word in text for word in words):
            return name
    return None


def update_icon(button, color):
    navigation = getattr(button, '_serverlook_nav', False)
    if navigation:
        color = {'mapping': '#ec7970', 'server': '#2aafff', 'settings': '#a681ed', 'search': '#27ba94', 'help': '#e5a532'}[button._serverlook_icon]
    image = tk.PhotoImage(master=button, width=20, height=18)
    for points in SHAPES[button._serverlook_icon]:
        for start, end in zip(points, points[1:] or points):
            x1, y1 = start
            x2, y2 = end
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for step in range(steps + 1):
                x = round(x1 + (x2 - x1) * step / steps)
                y = round(y1 + (y2 - y1) * step / steps)
                image.put(color, to=(x, y, x + 2, y + 1))
    size = getattr(button.winfo_toplevel(), '_serverlook_options', {}).get('button_size', '紧凑')
    if navigation:
        image = image.zoom(2, 2)
    elif size == '宽松':
        image = image.zoom(4, 4).subsample(3, 3)
    button._serverlook_image = image
    button.configure(image=image, compound='left')


class Tooltip:
    """Delayed labels for icon navigation, including keyboard focus."""

    def __init__(self, widget, text, *, bind_events=True, position=None):
        self.widget, self.text = widget, text
        self.position = position
        self.pending = self.window = None
        if not bind_events:
            return
        for event in ('<Enter>', '<FocusIn>'):
            widget.bind(event, self.schedule, add='+')
        for event in ('<Leave>', '<FocusOut>', '<ButtonPress>', '<Destroy>'):
            widget.bind(event, self.hide, add='+')

    def schedule(self, event=None):
        self.hide()
        self.pending = self.widget.after(350, self.show)

    def show(self):
        self.pending = None
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        x, y = self.position() if self.position else (self.widget.winfo_rootx(), self.widget.winfo_rooty() + self.widget.winfo_height() + 5)
        self.window.geometry(f'+{x}+{y}')
        ttk.Label(self.window, text=self.text, style='Tooltip.TLabel', padding=(10, 5)).pack()

    def hide(self, event=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


def navigation_button(parent, label, command):
    widget = ttk.Button(parent, command=command, style='Nav.TButton', takefocus=True)
    widget._serverlook_nav = True
    widget._serverlook_icon = icon_for(label)
    update_icon(widget, '')
    widget.tooltip = Tooltip(widget, label)
    return widget


def button(parent, **kwargs):
    widget = ttk.Button(parent, **kwargs)
    name = icon_for(kwargs.get('text', ''))
    if name:
        widget._serverlook_icon = name
        color = ttk.Style(widget).lookup(kwargs.get('style', 'TButton'), 'foreground') or '#e8f1fc'
        update_icon(widget, color)
    return widget
