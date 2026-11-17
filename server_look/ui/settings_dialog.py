"""Settings dialog: validate and persist all fields before applying them."""
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import ttk, messagebox
from server_look.localization.i18n import LANGUAGES
from server_look.ui.theme import PALETTES
from server_look.config.ui_preferences import validate, save_preferences
from server_look.ui.shortcut_capture import shortcut_control
from server_look.ui.ui_icons import button


def show_settings(app):
    if getattr(app, 'settings_window', None) and app.settings_window.winfo_exists():
        app.settings_window.lift()
        return
    win = app.settings_window = tk.Toplevel(app.root)
    win.title('设置 · 服务器看看')
    win.transient(app.root)
    form = ttk.Frame(win, padding=20)
    form.pack(fill='both', expand=True)
    tabs = ttk.Notebook(form)
    tabs.pack(fill='both', expand=True)
    general, keys = ttk.Frame(tabs, padding=16), ttk.Frame(tabs, padding=16)
    tabs.add(general, text='界面与操作')
    tabs.add(keys, text='快捷键')
    values = app.preferences
    variables = {key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.IntVar(value=value) if isinstance(value, int) else tk.StringVar(value=value)) for key, value in values.items() if key not in ('shortcuts', 'language')}
    language = tk.StringVar(value=LANGUAGES[values['language']])
    theme = tk.StringVar(value=app.theme_name.get())
    ttk.Checkbutton(general, text='远程只读（应用于全部服务器）', variable=variables['readonly']).grid(row=9, column=0, columnspan=2, sticky='w', pady=8)
    fields = [('全局大小修正（%）', variables['global_scale'], tuple(range(50, 201, 10))), ('语言 / Language', language, tuple(LANGUAGES.values())), ('界面配色', theme, tuple(PALETTES)), ('界面字体大小', variables['font_size'], tuple(range(8, 19))), ('按键字体大小', variables['button_font'], tuple(range(8, 19))), ('按键与图标大小', variables['button_size'], ('紧凑', '标准', '宽松')), ('入口按键布局', variables['navigation'], ('顶部横排', '左侧竖排')), ('窗口布局', variables['window'], ('普通窗口', '最大化'))]
    for row, (label, variable, choices) in enumerate(fields):
        ttk.Label(general, text=label).grid(row=row, column=0, sticky='w', pady=7)
        if label in ('界面字体大小', '按键字体大小'):
            control = ttk.Frame(general)
            def adjust(value, delta):
                value.set(max(8, min(18, value.get() + delta)))
            ttk.Button(control, text='−', width=4, command=lambda v=variable: adjust(v, -1)).pack(side='left')
            ttk.Label(control, textvariable=variable, width=6, anchor='center').pack(side='left')
            ttk.Button(control, text='+', width=4, command=lambda v=variable: adjust(v, 1)).pack(side='left')
        else:
            control = ttk.Combobox(general, textvariable=variable, values=choices, state='readonly', width=20)
            for event in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                control.bind(event, lambda event: 'break')
        control.grid(row=row, column=1, sticky='e', padx=(30, 0))
    shortcuts = {}
    for row, (action, key) in enumerate(values['shortcuts'].items()):
        shortcuts[action] = tk.StringVar(value=key)
        group, row = divmod(row, 7)
        ttk.Label(keys, text=action).grid(row=row, column=group * 2, sticky='w', pady=5)
        shortcut_control(keys, shortcuts[action]).grid(row=row, column=group * 2 + 1, padx=12)
    ttk.Label(keys, text='点击快捷键按钮后，直接按下所需组合键；Esc 取消录入，清除可禁用。\nControl = Ctrl；Return = 回车；comma = 逗号。文件操作仅在文件列表中生效。', style='Muted.TLabel').grid(row=8, column=0, columnspan=4, sticky='w', pady=10)
    def restore():
        defaults = validate({})
        for key, variable in variables.items():
            variable.set(defaults[key])
        language.set(LANGUAGES[defaults['language']])
        theme.set('深海蓝')
        for action, variable in shortcuts.items():
            variable.set(defaults['shortcuts'][action])
        save()
    def save():
        try:
            settings = validate(dict((k, v.get()) for k, v in variables.items()) | {'language': next(code for code, label in LANGUAGES.items() if label == language.get()), 'shortcuts': {k: v.get() for k, v in shortcuts.items()}})
            save_preferences(settings)
            app.theme_name.set(theme.get())
            app.change_theme()
            app.apply_preferences(settings)
        except (ValueError, OSError, tk.TclError) as exc:
            messagebox.showerror('无法保存设置', str(exc), parent=win)
            return
        win.destroy()
    bar = ttk.Frame(form)
    bar.pack(fill='x', pady=(16, 0))
    button(bar, text='恢复默认设置', command=restore).pack(side='left')
    button(bar, text='取消', command=win.destroy).pack(side='right')
    button(bar, text='保存并应用', style='Accent.TButton', command=save).pack(side='right', padx=8)
    app.retheme()
