"""Scale pixel layout metrics without accumulating changes on theme refresh."""
import tkinter as tk
from tkinter import ttk


def scale_layout(root, style, factor):
    def pixels(value):
        return tuple(round(float(v) * factor) for v in (value if isinstance(value, (tuple, list)) else root.tk.splitlist(str(value))))

    # These styles are restored to their logical metrics by apply_theme first.
    names = ('.', 'TButton', 'Nav.TButton', 'Capsule.TButton', 'View.TRadiobutton',
             'TEntry', 'TCombobox', 'TCheckbutton', 'TNotebook', 'TNotebook.Tab',
             'Server.TNotebook.Tab', 'Treeview', 'Treeview.Heading', 'Card.TLabel', 'Summary.TLabel')
    for name in names:
        for option in ('padding', 'rowheight', 'tabmargins'):
            value = style.configure(name, option)
            if value:
                style.configure(name, **{option: pixels(value)})
        mapping = style.map(name, 'padding')
        if mapping:
            style.map(name, padding=[(*entry[:-1], pixels(entry[-1])) for entry in mapping])
    style.configure('TScrollbar', arrowsize=max(8, round(14 * factor)))

    def walk(widget):
        cache = getattr(widget, '_serverlook_layout_metrics', {})
        for manager in ('pack', 'grid'):
            if widget.winfo_manager() == manager:
                info = getattr(widget, manager + '_info')()
                updates = {}
                for option in ('padx', 'pady', 'ipadx', 'ipady'):
                    if option not in info:
                        continue
                    raw = info[option]
                    current = tuple(float(v) for v in (raw if isinstance(raw, (tuple, list)) else root.tk.splitlist(str(raw))))
                    key = (manager, option)
                    base, previous = cache.get(key, (current, current))
                    if current != previous:
                        base = current
                    value = pixels(base)
                    updates[option] = value
                    cache[key] = (base, value)
                getattr(widget, manager + '_configure')(**updates)
        if isinstance(widget, ttk.Frame):
            value = widget.cget('padding')
            if value:
                base = cache.setdefault('padding', value)
                widget.configure(padding=pixels(base))
        if isinstance(widget, ttk.Treeview):
            for column in ('#0', *widget['columns']):
                base = cache.setdefault(('column', column), widget.column(column, 'width'))
                widget.column(column, width=max(1, round(base * factor)))
        if isinstance(widget, tk.Canvas):
            for option in ('width', 'height'):
                base = cache.setdefault(option, widget.cget(option))
                widget.configure(**{option: max(1, round(float(base) * factor))})
        widget._serverlook_layout_metrics = cache
        for child in widget.winfo_children():
            walk(child)
    walk(root)
