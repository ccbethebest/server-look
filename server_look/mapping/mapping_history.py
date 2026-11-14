"""Saved mapping browser; deletion only changes configuration."""
from server_look.localization.localized_ui import tk, messagebox, ttk
from server_look.mapping.directory_mapping import save_mappings
from server_look.mapping.mapping_rows import direction_label


def show_history(owner):
    existing = getattr(owner, 'history_window', None)
    if existing is not None and existing.winfo_exists():
        existing.deiconify()
        existing.lift()
        return
    win = owner.history_window = tk.Toplevel(owner.window)
    win.title('历史映射查看')
    win.transient(owner.window)
    width = min(1180,win.winfo_screenwidth()-80)
    height = min(650,win.winfo_screenheight()-120)
    win.geometry(f'{width}x{height}')
    win.minsize(min(900,width),min(500,height))
    tree = ttk.Treeview(win, columns=('direction', 'source', 'target'), show='headings', selectmode='extended', height=12)
    for key, title, width in [('direction','方向',220),('source','来源目录',300),('target','目标目录',300)]:
        tree.heading(key,text=title)
        tree.column(key,width=width)
    tree.pack(fill='both',expand=True,padx=12,pady=12)
    scroll = ttk.Scrollbar(tree,command=tree.yview)
    scroll.pack(side='right',fill='y')
    tree.configure(yscrollcommand=scroll.set)
    def populate():
        tree.delete(*tree.get_children())
        for record in owner.records:
            tree.insert('', 'end', iid=record['id'], values=(direction_label(record),
                record['locations'][0]['path'],record['locations'][1]['path']))
    def remove(all_records=False):
        selected = set(tree.get_children() if all_records else tree.selection())
        if not selected or not messagebox.askyesno('删除历史映射',
                f'删除 {len(selected)} 条历史记录？不会删除实际文件。',parent=win):
            return
        records = [record for record in owner.records if record['id'] not in selected]
        try:
            save_mappings(records)
        except OSError as exc:
            messagebox.showerror('历史映射',str(exc),parent=win)
            return
        owner.records = records
        owner.refresh_history()
        populate()
    def use():
        selected = set(tree.selection())
        for record in owner.records:
            if record['id'] in selected:
                owner.add_history(record)
    def context(event):
        item = tree.identify_row(event.y)
        if item and item not in tree.selection():
            tree.selection_set(item)
        menu = tk.Menu(win,tearoff=False)
        menu.add_command(label='添加到当前映射',command=use)
        menu.add_command(label='删除选中历史记录',command=remove)
        menu.tk_popup(event.x_root,event.y_root)
    tree.bind('<Button-3>',context)
    tree.bind('<Delete>',lambda event:remove())
    tree.bind('<Double-1>',lambda event:use())
    ttk.Button(win,text='添加选中映射',command=use).pack(side='left',padx=12,pady=8)
    ttk.Button(win,text='删除选中记录',command=remove).pack(side='left',pady=8)
    ttk.Button(win,text='全部删除',command=lambda:remove(True)).pack(side='right',padx=12,pady=8)
    populate()
    owner.app.retheme()
