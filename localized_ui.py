"""Small Tk presentation adapters; original variables remain the source of truth.

Only captions, prompts and explicitly selected display cells are translated.
Entries, file names, commands, server addresses and protocol values are untouched.
"""
import tkinter as _tk
from tkinter import ttk as _ttk, messagebox as _messagebox, filedialog as _filedialog, simpledialog as _simpledialog
from i18n import tr, subscribe


class _Localized:
    def __init__(self, *args, **options):
        self._captions = {}
        self._source_variable = self._display_variable = None
        self._traces = []
        self._syncing = False
        super().__init__(*args, **self._options_language(options))
        subscribe(self)
        self.bind('<Destroy>', self._dispose_language, add='+')

    def _options_language(self, options):
        options = dict(options)
        for key in ('text', 'label', 'values'):
            if key in options:
                self._captions[key] = options[key]
                options[key] = self._translated(key, options[key])
        if 'textvariable' in options and isinstance(self, (_ttk.Label, _ttk.Combobox, _ttk.Button, _ttk.Checkbutton, _ttk.Radiobutton)):
            for variable, trace in self._traces:
                variable.trace_remove('write', trace)
            self._traces.clear()
            self._source_variable = self._display_variable = None
            source = options['textvariable']
            if isinstance(source, _tk.Variable):
                self._source_variable = source
                self._display_variable = _tk.StringVar(master=source._root)
                self._traces.append((source, source.trace_add('write', self._source_changed)))
                self._traces.append((self._display_variable, self._display_variable.trace_add('write', self._display_changed)))
                self._source_changed()
                options['textvariable'] = self._display_variable
        return options

    @staticmethod
    def _translated(key, value):
        return tuple(tr(v) for v in value) if key == 'values' else tr(value)

    def _source_changed(self, *_):
        if self._syncing:
            return
        self._syncing = True
        try:
            self._display_variable.set(tr(self._source_variable.get()))
        finally:
            self._syncing = False

    def _display_changed(self, *_):
        if self._syncing or not isinstance(self, _ttk.Combobox):
            return
        displayed = self._display_variable.get()
        raw = next((v for v in self._captions.get('values', ()) if tr(v) == displayed), displayed)
        self._syncing = True
        try:
            self._source_variable.set(raw)
        finally:
            self._syncing = False

    def configure(self, cnf=None, **options):
        if isinstance(cnf, dict):
            options = dict(cnf, **options)
            cnf = None
        return super().configure(cnf, **self._options_language(options))

    config = configure

    def refresh_language(self):
        if self.winfo_exists():
            super().configure(**{k:self._translated(k,v) for k,v in self._captions.items()})
            if self._source_variable is not None:
                self._source_changed()

    def _dispose_language(self, event):
        if event.widget is self:
            for variable, trace in self._traces:
                variable.trace_remove('write', trace)
            self._traces.clear()


class _Notebook(_Localized, _ttk.Notebook):
    def __init__(self, *args, **kw):
        self._tab_captions = {}
        super().__init__(*args, **kw)

    def add(self, child, **kw):
        if 'text' in kw:
            self._tab_captions[str(child)] = kw['text']
            kw['text'] = tr(kw['text'])
        return super().add(child, **kw)

    def tab(self, tab_id, option=None, **kw):
        if 'text' in kw:
            self._tab_captions[self.tabs()[self.index(tab_id)]] = kw['text']
            kw['text'] = tr(kw['text'])
        return super().tab(tab_id, option, **kw)

    def refresh_language(self):
        super().refresh_language()
        for tab in self.tabs():
            if tab in self._tab_captions:
                super().tab(tab, text=tr(self._tab_captions[tab]))


class _Treeview(_Localized, _ttk.Treeview):
    def __init__(self, *args, **kw):
        self._headings = {}
        self._localized_rows = {}
        self._row_captions = {}
        self.localized_columns = ()
        super().__init__(*args, **kw)

    def insert(self, parent, index, iid=None, **kw):
        caption = kw.pop('caption', False)
        columns = kw.pop('caption_columns', self.localized_columns)
        raw_text = kw.get('text', '')
        if caption:
            kw['text'] = tr(raw_text)
        raw = kw.get('values', ())
        if columns and raw:
            kw['values'] = tuple(tr(v) if i in columns else v for i, v in enumerate(raw))
        row = super().insert(parent, index, iid=iid, **kw)
        if columns and raw:
            self._localized_rows[row] = (raw, columns)
        if caption:
            self._row_captions[row] = raw_text
        return row

    def delete(self, *items):
        def forget(row):
            for child in self.get_children(row):
                forget(child)
            self._localized_rows.pop(row, None)
            self._row_captions.pop(row, None)
        for row in items:
            forget(row)
        return super().delete(*items)

    def heading(self, column, option=None, **kw):
        if 'text' in kw:
            self._headings[column] = kw['text']
            kw['text'] = tr(kw['text'])
        return super().heading(column, option, **kw)

    def refresh_language(self):
        super().refresh_language()
        for column, text in self._headings.items():
            super().heading(column, text=tr(text))
        for row, (values, columns) in self._localized_rows.items():
            self.item(row, values=tuple(tr(v) if i in columns else v for i, v in enumerate(values)))
        for row, text in self._row_captions.items():
            self.item(row, text=tr(text))


class _Menu(_tk.Menu):
    def __init__(self, *args, **kw):
        self._labels = {}
        super().__init__(*args, **kw)
        subscribe(self)

    def add(self, itemType, cnf=None, **kw):
        options = dict(cnf or {}, **kw)
        raw = options.get('label')
        if raw is not None:
            options['label'] = tr(raw)
        result = super().add(itemType, **options)
        if raw is not None:
            self._labels[self.index('end')] = raw
        return result

    def delete(self, index1, index2=None):
        first = self.index(index1)
        last = self.index(index2) if index2 is not None else first
        result = super().delete(index1, index2)
        if first is not None and last is not None:
            count = last-first+1
            self._labels = {i if i<first else i-count:v for i,v in self._labels.items() if i<first or i>last}
        return result

    def entryconfigure(self, index, cnf=None, **kw):
        options = dict(cnf or {}, **kw) if isinstance(cnf, (dict,type(None))) else kw
        if 'label' in options:
            self._labels[self.index(index)] = options['label']
            options['label'] = tr(options['label'])
        return super().entryconfigure(index, **options) if options else super().entryconfigure(index, cnf)

    entryconfig = entryconfigure

    def refresh_language(self):
        if self.winfo_exists():
            for index, text in self._labels.items():
                super().entryconfigure(index, label=tr(text))


class _Toplevel(_tk.Toplevel):
    def __init__(self, *args, **kw):
        self._title = ''
        super().__init__(*args, **kw)
        subscribe(self)

    def title(self, value=None):
        if value is None:
            return super().title()
        self._title = value
        return super().title(tr(value))

    def refresh_language(self):
        if self.winfo_exists():
            super().title(tr(self._title))


class _Dialogs:
    def __init__(self, module):
        self.module = module

    def __getattr__(self, name):
        function = getattr(self.module, name)
        def show(*args, **kw):
            args = tuple(tr(value) if isinstance(value,str) else value for value in args)
            for key in ('title','message','detail','prompt'):
                if key in kw:
                    kw[key] = tr(kw[key])
            return function(*args, **kw)
        return show


class _Toolkit:
    def __init__(self, module, overrides):
        self.module, self.overrides = module, overrides

    def __getattr__(self, name):
        return self.overrides.get(name, getattr(self.module, name))


ttk = _Toolkit(_ttk, {name:type(name, (_Localized, getattr(_ttk,name)), {}) for name in
    ('Label','Button','Checkbutton','Radiobutton','Combobox','Labelframe')})
ttk.overrides.update(Notebook=_Notebook,Treeview=_Treeview)
tk = _Toolkit(_tk, {'Toplevel':_Toplevel, 'Menu':_Menu})
messagebox = _Dialogs(_messagebox)
filedialog = _Dialogs(_filedialog)
simpledialog = _Dialogs(_simpledialog)

StringVar = _tk.StringVar
Menu = _Menu
