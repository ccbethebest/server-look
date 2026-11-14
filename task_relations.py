"""Snapshot-based process ancestry and descendants; no inferred application dependencies."""
import tkinter as tk
from tkinter import ttk


def relation_rows(processes, task):
    by_pid = {int(row['pid']): row for row in processes.values()}
    ancestors, seen = [], set()
    current = task
    while current and current['pid'] not in seen:
        seen.add(current['pid'])
        ancestors.append(current)
        current = by_pid.get(current.get('ppid'))
    rows = [(row, '当前任务' if row['pid'] == task['pid'] else '祖先 / 父任务') for row in reversed(ancestors)]
    children = {}
    for row in by_pid.values():
        children.setdefault(row.get('ppid'), []).append(row)
    pending = list(children.get(task['pid'], []))
    while pending:
        row = pending.pop()
        if row['pid'] in seen:
            continue
        seen.add(row['pid'])
        rows.append((row, '子任务' if row.get('ppid') == task['pid'] else '后代任务'))
        pending.extend(children.get(row['pid'], []))
    return rows


def show_relations(parent, processes, task, select):
    window = tk.Toplevel(parent)
    window.title(f"任务关系 · PID {task['pid']}")
    window.geometry('1000x520')
    window.transient(parent.winfo_toplevel())
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='按操作系统父 PID 展示进程关系快照；不代表程序内部的业务依赖。双击可定位任务。').pack(anchor='w', pady=(0, 8))
    tree = ttk.Treeview(frame, columns=('relation', 'started', 'command'), show='tree headings')
    for column, text, width in (('#0', 'PID / 父 PID', 210), ('relation', '关系', 110), ('started', '开始时间', 180), ('command', '命令', 650)):
        tree.heading(column, text=text)
        tree.column(column, width=width)
    tree.pack(side='left', fill='both', expand=True)
    scroll = ttk.Scrollbar(frame, command=tree.yview)
    scroll.pack(side='right', fill='y')
    tree.configure(yscrollcommand=scroll.set)
    rows = relation_rows(processes, task)
    displayed = {}
    for row, label in rows:
        pid, ppid = row['pid'], row.get('ppid')
        displayed[pid] = tree.insert(displayed.get(ppid, ''), 'end', text=f'{pid}  ←  {ppid}',
                                     values=(label, row.get('started', ''), row.get('command', '')), open=True)
    by_iid = {displayed[row['pid']]: row for row, _ in rows}
    def locate(event):
        selection = tree.selection()
        if selection:
            select(by_iid[selection[0]])
    tree.bind('<Double-1>', locate)
    tree.selection_set(displayed[task['pid']])
    tree.see(displayed[task['pid']])
    return window
