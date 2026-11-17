"""Desktop window and server-tab lifecycle; no SSH or process operations here."""
from server_look.paths import resource_root
from server_look.localization.localized_ui import tk
from pathlib import Path
import sys
from server_look.localization.localized_ui import messagebox, ttk
from server_look.ui.ui_icons import navigation_button

from server_look.app.server_page import ServerPage
from server_look.transport.connection_history import ConnectionHistory
from server_look.localization.i18n import set_language, tr
from server_look.config.ui_preferences import load_preferences
from server_look.ui.theme import apply_theme, PALETTES, load_theme, save_theme
from server_look.app.settings import APP_NAME, APP_VERSION, DEFAULT_SERVERS


class MultiServerApp:
    """Each page owns its connection, worker, snapshot and action selection."""
    def __init__(self, root):
        self.root = root
        self.pages = {}
        self.occupancy_marks = {}
        self.occupancy_details = {}
        root._serverlook_app = self
        self.preferences = load_preferences()
        set_language(self.preferences['language'])
        root._serverlook_options = self.preferences
        self.bound_shortcuts = []
        self.dialogs = []
        apply_theme(root, load_theme())
        icon = resource_root() / 'assets' / 'server.ico'
        root.iconbitmap(default=str(icon))
        root.title(f'{tr(APP_NAME)} {APP_VERSION}')
        width = min(1320, root.winfo_screenwidth() - 40)
        height = min(900, root.winfo_screenheight() - 90)
        root.geometry(f'{width}x{height}')
        root.minsize(min(1050, width), min(650, height))
        self.header = ttk.Frame(root, padding=(12, 4))
        self.header.pack(fill='x')
        ttk.Label(self.header, text=APP_NAME, style='Brand.TLabel').pack(side='right', padx=12)
        self.theme_name = tk.StringVar(value=root._serverlook_theme)
        self.body = ttk.Frame(root)
        self.body.pack(fill='both', expand=True)
        self.navigation = ttk.Frame(root, padding=0)
        self.navigation_buttons = []
        for label, command in [('服务器', self.show_servers), ('设置', self.show_settings), ('搜索', self.show_search), ('映射', self.show_mapping), ('帮助', self.show_help)]:
            widget = navigation_button(self.navigation, label, command)
            self.navigation_buttons.append(widget)
        self.server_menu = tk.Menu(root, tearoff=False)
        self.server_menu.add_command(label='当前服务器连接 / 历史记录', command=lambda: self.current_action('show_connection_dialog'))
        self.server_menu.add_command(label='添加服务器页面', command=self.add_server)
        self.server_menu.add_separator()
        self.server_menu.add_command(label='连接全部页面', command=self.connect_all)
        self.server_menu.add_command(label='一键连接历史所有服务器', command=self.connect_history)
        self.server_menu.add_command(label='断开全部服务器', command=self.disconnect_all)
        self.server_menu.add_command(label='关闭全部服务器页面', command=self.close_all)
        self.server_menu.add_command(label='关闭当前页面', command=self.close_page)
        from server_look.ui.server_tabs import ServerTabs
        self.workarea = ttk.Frame(self.body)
        self.notebook = ttk.Notebook(self.workarea, style='Server.TNotebook')
        self.server_tabs = ServerTabs(self.workarea, self)
        self.server_tabs.pack(fill='x')
        self.notebook.pack(fill='both', expand=True)
        self.notebook.bind('<<NotebookTabChanged>>', self.visited)
        for host in DEFAULT_SERVERS or ('',):
            self.add_server(host)
        self.notebook.select(0)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.apply_preferences(self.preferences)

    def current_page(self):
        return self.pages.get(self.notebook.select())

    def current_action(self, method):
        page = self.current_page()
        if page:
            getattr(page, method)()

    def retheme(self):
        apply_theme(self.root, self.theme_name.get())
        self.server_tabs.draw()

    def show_servers(self):
        widget = self.navigation_buttons[0]
        try:
            self.server_menu.tk_popup(widget.winfo_rootx(), widget.winfo_rooty() + widget.winfo_height())
        finally:
            self.server_menu.grab_release()

    def show_settings(self):
        from server_look.ui.settings_dialog import show_settings
        show_settings(self)

    def show_search(self):
        from server_look.files.search_dialog import SearchDialog
        for dialog in self.dialogs:
            if isinstance(dialog, SearchDialog) and not dialog.closed and dialog.window.winfo_exists():
                dialog.window.deiconify()
                dialog.window.lift()
                return
        page = self.current_page()
        if page:
            window = SearchDialog(self, page)
            self.dialogs.append(window)

    def show_mapping(self, remote=None):
        from server_look.mapping.mapping_dialog import MappingDialog
        for dialog in self.dialogs:
            if isinstance(dialog, MappingDialog) and dialog.window.winfo_exists():
                dialog.window.deiconify()
                dialog.window.lift()
                return
        page = self.current_page()
        if page:
            self.dialogs.append(MappingDialog(self, page, remote))

    def visited(self, event=None):
        self.occupancy_marks.pop(self.notebook.select(), None)
        self.server_tabs.draw()

    def query_idle(self):
        count = 0
        for page in self.pages.values():
            if page.connection and page.connection_state.get() == '连接成功' and not getattr(page, 'idle_pending', False):
                page.idle_pending = True
                self.occupancy_marks.pop(str(page.root), None)
                self.occupancy_details[str(page.root)] = '正在查询卡占用情况…'
                page.status.set('正在查询所有已连接服务器的加速卡空闲状态…')
                page.submit('idle')
                count += 1
        self.server_tabs.draw()
        if not count and self.current_page():
            self.current_page().status.set('没有可查询的已连接服务器，或查询正在进行')

    def idle_result(self, page, result, error):
        page.idle_pending = False
        self.occupancy_marks.pop(str(page.root), None)
        if error or result.get('errors'):
            reason = '空闲状态查询失败：' + (error or '；'.join(result['errors']))
            self.occupancy_details[str(page.root)] = reason
            page.status.set(reason)
        else:
            self.occupancy_details[str(page.root)] = f"已用卡数/总卡数：{result['used']}/{result['total']}（最近一次查询）"
            state = result['state']
            self.occupancy_marks[str(page.root)] = state
            label = {'idle': '绿色：全部空闲', 'partial': '黄色：部分使用', 'full': '红色：全部使用'}[state]
            page.status.set(f"{label}（已使用 {result['used']} / {result['total']} 张卡）；点击服务器清除提示")
        self.server_tabs.draw()

    def disconnect_all(self):
        for page in self.pages.values():
            page.resources.local.cancel()
            page.disconnect()
        self.occupancy_marks.clear()
        self.occupancy_details.clear()
        self.server_tabs.draw()

    def close_all(self):
        if not all(page.resources.editors.close_all() for page in self.pages.values()):
            return
        for tab, page in list(self.pages.items()):
            self.notebook.forget(tab)
            page.close()
        self.pages.clear()
        self.occupancy_marks.clear()
        self.occupancy_details.clear()
        self.update_server_tabs()

    def show_help(self):
        from server_look.ui.help_dialog import show_help
        show_help(self)

    def apply_preferences(self, values):
        self.preferences = values
        set_language(values['language'])
        self.root.title(f'{tr(APP_NAME)} {APP_VERSION}')
        self.root._serverlook_options = values
        self.navigation.pack_forget()
        self.workarea.pack_forget()
        vertical = values['navigation'] == '左侧竖排'
        self.navigation.pack(in_=self.body if vertical else self.header,
                             side='left', fill='y' if vertical else 'none')
        for widget in self.navigation_buttons:
            widget.pack_forget()
            widget.pack(side='top' if vertical else 'left', padx=4, pady=2)
        self.workarea.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.root.state('zoomed' if values['window'] == '最大化' else 'normal')
        for page in self.pages.values():
            self.configure_page(page)
        for key in self.bound_shortcuts:
            self.root.unbind(key)
        actions = {'服务器': self.add_server, '连接': lambda: self.current_action('show_connection_dialog'), '刷新': lambda: self.current_action('refresh'), '断开': lambda: self.current_action('disconnect'), '搜索': self.show_search, '设置': self.show_settings, '帮助': self.show_help}
        self.bound_shortcuts = []
        for action, key in values['shortcuts'].items():
            if key != '无' and action in actions:
                self.root.bind(key, lambda event, action=action: self.run_shortcut(event, actions[action]))
                self.bound_shortcuts.append(key)
        self.retheme()

    def run_shortcut(self, event, action):
        # Dialog controls have their own keyboard behavior.
        if event.widget.winfo_toplevel() is self.root:
            action()
            return 'break'

    def configure_page(self, page):
        page.readonly.set(self.preferences['readonly'])
        if page.readonly.get():
            page.commands.disconnect()
        page.readonly_label.configure(text='远程只读' if page.readonly.get() else '远程可写')
        page.resources.local.configure_shortcuts(self.preferences['shortcuts'])
        page.buttons()

    def change_theme(self, event=None):
        name = self.theme_name.get()
        self.retheme()
        try:
            save_theme(name)
        except OSError:
            messagebox.showwarning('界面配色', '配色已切换，但偏好保存失败；下次启动可能恢复原配色。', parent=self.root)

    def add_server(self, host=''):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=host or '未连接')
        page = ServerPage(frame, embedded=True, host=host,
                   on_connect=lambda address: self.rename_tab(frame, address),
                   on_close=lambda: self.close_page(str(frame)))
        self.pages[str(frame)] = page
        self.update_server_tabs()
        self.configure_page(page)
        self.notebook.select(frame)
        apply_theme(self.root, self.root._serverlook_theme)
        return page

    def rename_tab(self, frame, address):
        self.notebook.tab(frame, text=address)
        self.server_tabs.draw()

    def update_server_tabs(self):
        self.notebook.configure(style='Solo.Server.TNotebook' if len(self.pages) == 1 else 'Server.TNotebook')
        self.server_tabs.draw()

    def connect_all(self):
        for page in self.pages.values():
            if page.host.get().strip() and not page.connection:
                page.connect()

    def connect_history(self):
        """Reuse matching pages; existing page workers perform SSH asynchronously."""
        try:
            records = ConnectionHistory().load()
        except (OSError, ValueError) as exc:
            messagebox.showerror('连接历史', str(exc), parent=self.root)
            return
        if not records:
            messagebox.showinfo('连接历史', '暂无历史服务器，请先连接并保存服务器。', parent=self.root)
            return
        for record in records:
            identity = ConnectionHistory.identity(record)
            matching = []
            for page in self.pages.values():
                current = page.connected_record if page.connection else dict(
                    host=page.host.get().strip(), user=page.user.get().strip(), port=page.port.get().strip())
                if current and ConnectionHistory.identity(current) == identity:
                    matching.append(page)
            if any(page.connection and page.connection_state.get() in ('连接成功', '连接中…')
                   for page in matching):
                continue
            page = next((page for page in matching if not page.busy), None)
            if page is None and matching:
                continue
            if page is None:
                page = next((page for page in self.pages.values()
                             if not page.connection and not page.busy and not page.host.get().strip()), None)
            if page is None:
                page = self.add_server()
            available = page.apply_history(record)
            self.rename_tab(page.root, f"{record['user']}@{record['host']}:{record['port']}")
            if not available or (record['auth_mode'] == 'password' and not page.password.get()):
                reason = ('保存的密码无法解密，请重新输入密码' if not available
                          else '未保存密码，请在连接设置中输入密码')
                page.set_connection_state('连接失败', reason)
                page.status.set(reason)
                continue
            page.connect()

    def close_page(self, selected=None):
        selected = selected or self.notebook.select()
        if not selected:
            return
        page = self.pages[selected]
        if page.busy:
            messagebox.showinfo('正在操作', '当前页面有采集或操作尚未完成，请稍后关闭。', parent=self.root)
            return
        if not page.resources.editors.close_all():
            return
        self.notebook.forget(selected)
        self.pages.pop(selected).close()
        self.occupancy_marks.pop(selected, None)
        self.occupancy_details.pop(selected, None)
        self.update_server_tabs()

    def close(self):
        if not all(page.resources.editors.close_all() for page in self.pages.values()):
            return
        for dialog in self.dialogs:
            dialog.close()
        for page in list(self.pages.values()):
            page.close()
        self.pages.clear()
        self.root.destroy()


def main():
    from tkinterdnd2 import TkinterDnD
    window = TkinterDnD.Tk()
    MultiServerApp(window)
    window.mainloop()
