"""Compact rounded server tabs with independent idle highlighting."""
from server_look.localization.localized_ui import tk
from tkinter import font
from server_look.ui.theme import PALETTES
from server_look.ui.ui_icons import Tooltip


class ServerTabs(tk.Canvas):
    def __init__(self, parent, app):
        super().__init__(parent, height=36, highlightthickness=0, takefocus=True)
        self.app = app
        self.targets = {}
        self.hovered_tab = None
        self.tooltip = Tooltip(self, '', bind_events=False,
                               position=lambda: (self.winfo_pointerx() + 12, self.winfo_pointery() + 16))
        self.bind('<Motion>', self.hover)
        self.bind('<Leave>', self.hide_tooltip)
        self.bind('<Destroy>', self.hide_tooltip)
        self.bind('<Button-1>', self.click)
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<MouseWheel>', lambda event: self.xview_scroll(-1 if event.delta > 0 else 1, 'units'))
        self.bind('<Left>', lambda event: self.step(-1))
        self.bind('<Right>', lambda event: self.step(1))

    def hide_tooltip(self, event=None):
        self.hovered_tab = None
        self.tooltip.hide()

    def hover(self, event):
        tab = next((self.targets[tag] for tag in self.gettags('current') if tag in self.targets), None)
        if tab == self.hovered_tab:
            return
        self.hide_tooltip()
        self.hovered_tab = tab
        if tab:
            self.tooltip.text = self.app.occupancy_details.get(tab, '尚未查询；点击“查空闲”查询所有已连接服务器')
            self.tooltip.schedule()

    def step(self, offset):
        tabs = self.app.notebook.tabs()
        if tabs:
            index = tabs.index(self.app.notebook.select())
            self.select(tabs[(index + offset) % len(tabs)])

    def select(self, tab):
        self.app.occupancy_marks.pop(tab, None)
        self.app.notebook.select(tab)
        self.draw()

    def click(self, event):
        for tag in self.gettags('current'):
            if tag in self.targets:
                self.select(self.targets[tag])
                break

    def draw(self):
        self.hide_tooltip()
        app = self.app
        colors = PALETTES[app.root._serverlook_theme]
        background, surface, raised, text, muted, accent, selected, success, error = colors
        self.configure(background=background)
        self.delete('all')
        self.face = face = font.Font(family='Microsoft YaHei UI', size=app.preferences['button_font'])
        self.targets.clear()
        x = 2
        for index, tab in enumerate(app.notebook.tabs()):
            label = app.notebook.tab(tab, 'text')
            width = face.measure(label) + 32
            active = tab == app.notebook.select()
            fill = selected if active else raised
            mark = app.occupancy_marks.get(tab)
            warning = '#a66500' if app.root._serverlook_theme == '云雾白' else '#f5c451'
            foreground = {'idle': success, 'partial': warning, 'full': error}.get(mark, text if active else muted)
            tag = f'tab{index}'
            self.targets[tag] = tab
            self.create_oval(x, 3, x + 28, 31, fill=fill, outline='', tags=tag)
            self.create_oval(x + width - 28, 3, x + width, 31, fill=fill, outline='', tags=tag)
            self.create_rectangle(x + 14, 3, x + width - 14, 31, fill=fill, outline='', tags=tag)
            self.create_text(x + width / 2, 17, text=label, fill=foreground, font=face, tags=tag)
            x += width + 6
        self.configure(scrollregion=(0, 0, x, 36))
