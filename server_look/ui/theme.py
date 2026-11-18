"""Shared dark-blue desktop palette and state-stable navigation styles."""
from server_look.ui.platform_ui import monospace
from server_look.paths import user_data_dir
import json
import sys
import math
import os
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

FONT = ('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 10)


# background, surface, raised, text, muted, accent, selection, success, error
PALETTES = {
    '深海蓝': ('#0b1729', '#11243c', '#19334f', '#e8f1fc', '#a8bdd4', '#1685ed', '#205c91', '#73e0b0', '#ffb0bb'),
    '石墨黑': ('#111318', '#1b1e24', '#2b3039', '#edf0f5', '#b4bdca', '#557bd9', '#375487', '#86dcb0', '#ffb0bb'),
    '云雾白': ('#eef2f7', '#ffffff', '#dfe7f1', '#172b43', '#52657c', '#216bc4', '#216bc4', '#167347', '#b32243'),
}


def preferences_path():
    return user_data_dir() / 'appearance.json'


def load_theme(path=None):
    try:
        name = json.loads((Path(path) if path else preferences_path()).read_text(encoding='utf-8'))['theme']
        return name if name in PALETTES else '深海蓝'
    except (OSError, ValueError, KeyError, TypeError):
        return '深海蓝'


def save_theme(name, path=None):
    if name not in PALETTES:
        raise ValueError('未知主题')
    target = Path(path) if path else preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({'theme': name}, stream, ensure_ascii=False)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def apply_theme(root, name='深海蓝'):
    if name not in PALETTES:
        name = '深海蓝'
    BACKGROUND, SURFACE, RAISED, TEXT, MUTED, ACCENT, SELECTED, SUCCESS, ERROR = PALETTES[name]
    root._serverlook_theme = name

    options = getattr(root, '_serverlook_options', {})
    scale = options.get('global_scale', 100) / 100
    if not hasattr(root, '_serverlook_base_scaling'):
        root._serverlook_base_scaling = float(root.tk.call('tk', 'scaling'))
    root.tk.call('tk', 'scaling', root._serverlook_base_scaling * scale)
    FONT = ('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', options.get('font_size', 10))
    button_font = (FONT[0], options.get('button_font', 10))
    padding = {'紧凑': (9, 4), '标准': (12, 7), '宽松': (16, 10)}[options.get('button_size', '紧凑')]
    style = ttk.Style(root)
    if style.theme_use() != 'clam':
        style.theme_use('clam')
    root.configure(background=BACKGROUND)
    for font_name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
        tkfont.nametofont(font_name, root=root).configure(family=FONT[0], size=FONT[1])
    # Classic Text widgets do not inherit ttk styles.
    for key, value in {'background': SURFACE, 'foreground': TEXT,
                       'insertBackground': TEXT, 'selectBackground': '#246399',
                       'selectForeground': '#ffffff', 'relief': 'flat',
                       'borderWidth': 0, 'highlightThickness': 1,
                       'highlightBackground': RAISED, 'highlightColor': ACCENT,
                       'padX': 12, 'padY': 10}.items():
        root.option_add('*Text.' + key, value)
    style.configure('.', background=BACKGROUND, foreground=TEXT, font=FONT,
                    bordercolor=RAISED, lightcolor=RAISED, darkcolor=RAISED)
    style.configure('TFrame', background=BACKGROUND)
    style.configure('Header.TFrame', background=SURFACE)
    style.configure('TLabel', background=BACKGROUND, foreground=TEXT)
    style.configure('Title.TLabel', background=SURFACE, foreground=TEXT,
                    font=('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 20, 'bold'))
    style.configure('Subtitle.TLabel', background=SURFACE, foreground=MUTED)
    style.configure('Muted.TLabel', foreground=MUTED)
    style.configure('Brand.TLabel', font=(FONT[0], 13, 'bold'), foreground=MUTED)
    style.configure('Summary.TLabel', background=SURFACE, foreground=MUTED, padding=(8, 3))
    style.configure('Tooltip.TLabel', background=RAISED, foreground=TEXT)
    style.configure('ConnectionPending.TLabel', foreground=ACCENT if name == '云雾白' else '#8dd9ff', font=(FONT[0], 10, 'bold'))
    style.configure('ConnectionSuccess.TLabel', foreground=SUCCESS, font=(FONT[0], 10, 'bold'))
    style.configure('ConnectionError.TLabel', foreground=ERROR, font=(FONT[0], 10, 'bold'))
    style.configure('Card.TLabel', padding=(16, 13), background=RAISED,
                    foreground=ACCENT if name == '云雾白' else '#8dd9ff', font=('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 11, 'bold'))
    style.configure('TButton', width=0, font=button_font, padding=padding, background=RAISED, foreground=TEXT,
                    borderwidth=1, relief='flat', focusthickness=1, focuscolor='#70c9ff')
    style.map('TButton', background=[('disabled', SURFACE), ('pressed', SELECTED), ('active', SELECTED)],
              foreground=[('disabled', MUTED)])
    style.configure('Nav.TButton', padding=(7, 3), borderwidth=0, background=BACKGROUND)
    style.map('Nav.TButton', background=[('active', RAISED), ('pressed', SELECTED)])
    images = getattr(root, '_serverlook_capsule_images', None)
    if images is None:
        images = [tk.PhotoImage(master=root, width=40, height=30) for _ in range(4)]
        root._serverlook_capsule_images = images
    for image, color in zip(images, (RAISED, SURFACE, ACCENT, SELECTED)):
        image.blank()
        for y in range(30):
            inset = math.ceil(15 - math.sqrt(225 - (y - 14.5) ** 2))
            image.put(color, to=(inset, y, 40 - inset, y + 1))
    if 'Capsule.border' not in style.element_names():
        style.element_create('Capsule.border', 'image', images[0], ('disabled', images[1]),
                             ('pressed', images[2]), ('active', images[3]), border=(15, 0, 15, 0), sticky='nsew')
    style.layout('Capsule.TButton', [('Capsule.border', {'sticky': 'nsew', 'children': [
        ('Button.focus', {'sticky': 'nsew', 'children': [('Button.padding', {'sticky': 'nsew', 'children': [
            ('Button.label', {'sticky': 'nsew'})]})]})]})])
    style.configure('Capsule.TButton', padding=(12, 4), background=BACKGROUND)
    style.map('Capsule.TButton', background=[('disabled', BACKGROUND), ('active', BACKGROUND), ('!active', BACKGROUND)])
    style.layout('View.TRadiobutton', [('Button.border', {'sticky': 'nsew', 'children': [
        ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
    style.configure('View.TRadiobutton', padding=(8, 6), background=RAISED, font=button_font)
    style.map('View.TRadiobutton', background=[('selected', ACCENT), ('active', SELECTED)],
              foreground=[('selected', '#ffffff')])
    style.configure('Accent.TButton', background=ACCENT, foreground='#ffffff')
    style.map('Accent.TButton', background=[('disabled', RAISED), ('pressed', '#0759a8'), ('active', '#319dff')])
    style.configure('Danger.TButton', background='#f8dfe5' if name == '云雾白' else '#482c3c', foreground=ERROR)
    style.map('Danger.TButton', background=[('disabled', SURFACE), ('active', '#f1c4cf' if name == '云雾白' else '#6b3449')],
              foreground=[('disabled', MUTED)])
    style.configure('TEntry', padding=7, fieldbackground=SURFACE, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=RAISED)
    style.map('TEntry', bordercolor=[('focus', '#40b7ff')],
              fieldbackground=[('readonly', SURFACE), ('disabled', BACKGROUND)],
              foreground=[('disabled', MUTED)])
    checkbox_indicator(root, style, scale, RAISED, ACCENT, MUTED)
    style.configure('TCheckbutton', background=BACKGROUND, foreground=TEXT, padding=4)
    style.map('TCheckbutton', background=[('active', BACKGROUND)],
              foreground=[('disabled', MUTED)],
              indicatorbackground=[('selected', ACCENT), ('!selected', RAISED)])
    style.configure('TNotebook', background=BACKGROUND, borderwidth=0, tabmargins=(0, 10, 0, 0))
    # Clam expands selected tabs by default. Explicit identical metrics prevent jumping.
    style.configure('TNotebook.Tab', padding=(14, 8), background=SURFACE,
                    foreground=MUTED, font=FONT, borderwidth=0)
    style.map('TNotebook.Tab', background=[('selected', ACCENT), ('active', SELECTED)],
              foreground=[('selected', '#ffffff'), ('active', '#ffffff')],
              expand=[('selected', (0, 0, 0, 0)), ('!selected', (0, 0, 0, 0))],
              padding=[('selected', (14, 8)), ('!selected', (14, 8))],
              font=[('selected', FONT), ('!selected', FONT)])
    style.configure('Server.TNotebook.Tab', padding=(18, 9), font=('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 11, 'bold'))
    for notebook_style in ('Content.TNotebook', 'Solo.Server.TNotebook', 'Server.TNotebook'):
        style.configure(notebook_style, tabmargins=0)
        style.layout(notebook_style + '.Tab', [])
    style.map('Server.TNotebook.Tab', padding=[('selected', (18, 9)), ('!selected', (18, 9))],
              font=[('selected', ('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 11, 'bold')),
                    ('!selected', ('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 11, 'bold'))])
    style.configure('Treeview', rowheight=max(30, FONT[1] * 2 + 10), background=SURFACE, fieldbackground=SURFACE,
                    foreground=TEXT, borderwidth=0)
    style.configure('Treeview.Heading', padding=(10, 11), background=RAISED,
                    foreground=TEXT, relief='flat', font=('Helvetica' if sys.platform == 'darwin' else 'Microsoft YaHei UI', 10, 'bold'))
    style.map('Treeview.Heading', background=[('active', SELECTED)])
    style.map('Treeview', background=[('selected', SELECTED)], foreground=[('selected', '#ffffff')])
    style.configure('TScrollbar', background=RAISED, troughcolor=BACKGROUND,
                    arrowcolor=MUTED, borderwidth=0)
    style.map('TScrollbar', background=[('active', SELECTED)])
    style.configure('TPanedwindow', background=BACKGROUND)

    style.configure('TCombobox', padding=7, fieldbackground=SURFACE, background=RAISED,
                    foreground=TEXT, arrowcolor=TEXT, insertcolor=TEXT)
    style.map('TCombobox', fieldbackground=[('readonly', SURFACE)], foreground=[('readonly', TEXT)],
              selectbackground=[('readonly', SELECTED)], selectforeground=[('readonly', '#ffffff')])
    style.configure('TLabelframe', background=BACKGROUND, bordercolor=RAISED, relief='solid', borderwidth=1)
    style.configure('TLabelframe.Label', background=BACKGROUND, foreground=MUTED, font=(FONT[0], 10, 'bold'))
    style.configure('TProgressbar', background=ACCENT, troughcolor=SURFACE, borderwidth=0)
    for option, value in {'background': SURFACE, 'foreground': TEXT,
                          'selectBackground': SELECTED, 'selectForeground': '#ffffff'}.items():
        root.option_add('*TCombobox*Listbox.' + option, value)

    # Existing classic widgets need explicit updates when the theme changes.
    def recolor(widget):
        if isinstance(widget, tk.Toplevel):
            widget.configure(background=BACKGROUND)
        if isinstance(widget, tk.Text):
            font_size = max(FONT[1], getattr(widget, '_serverlook_min_font_size', 0))
            widget.configure(font=(monospace(), font_size), background=SURFACE, foreground=TEXT, insertbackground=TEXT,
                             selectbackground=SELECTED, selectforeground='#ffffff',
                             highlightbackground=RAISED, highlightcolor=ACCENT)
        elif isinstance(widget, tk.Menu):
            widget.configure(background=SURFACE, foreground=TEXT, activebackground=SELECTED,
                             activeforeground='#ffffff', disabledforeground=MUTED)
        if isinstance(widget, ttk.Treeview):
            widget.tag_configure('warning', foreground='#795000' if name == '云雾白' else '#ffdc99',
                                 background='#fff0c7' if name == '云雾白' else '#3b342a')
            widget.tag_configure('critical', foreground=ERROR,
                                 background='#f8dfe5' if name == '云雾白' else '#442b3b')
        if hasattr(widget, '_serverlook_icon'):
            from server_look.ui.ui_icons import update_icon
            update_icon(widget, '#ffffff' if widget.cget('style') == 'Accent.TButton' else TEXT)
        for child in widget.winfo_children():
            recolor(child)
    recolor(root)

    from server_look.ui.scaling import scale_layout
    scale_layout(root, style, scale)


def checkbox_indicator(root, style, scale, background, accent, muted):
    """Use a real tick for selected; keep ttk variable, focus and keyboard behavior."""
    images = getattr(root, '_serverlook_check_images', None)
    if images is None:
        images = [tk.PhotoImage(master=root) for _ in range(4)]
        root._serverlook_check_images = images
        style.element_create('ServerLook.Check.indicator', 'image', images[0],
                             ('disabled', 'selected', images[3]), ('selected', images[1]),
                             ('disabled', images[2]), sticky='')
        style.layout('TCheckbutton', [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
            ('ServerLook.Check.indicator', {'side': 'left', 'sticky': ''}),
            ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                ('Checkbutton.label', {'sticky': 'nswe'})]})]})])
    size = max(14, round(18 * scale))
    for index, photo in enumerate(images):
        photo.configure(width=size + round(5 * scale), height=size)
        photo.blank()
        selected = index in (1, 3)
        border = muted if index >= 2 else accent
        photo.put(border, to=(0, 0, size, size))
        photo.put(accent if selected and index < 2 else background, to=(1, 1, size - 1, size - 1))
        if selected:
            # Two connected strokes form a check mark, never a cross.
            for start, end in [((.22, .51), (.43, .73)), ((.43, .73), (.80, .27))]:
                steps = size * 2
                for step in range(steps + 1):
                    x = round(size * (start[0] + (end[0] - start[0]) * step / steps))
                    y = round(size * (start[1] + (end[1] - start[1]) * step / steps))
                    width = max(1, round(scale))
                    photo.put(muted if index >= 2 else '#ffffff', to=(x, y, x + width + 1, y + width + 1))
