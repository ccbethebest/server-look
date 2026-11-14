"""Direct pane transfers; stage files only when exporting to Windows Explorer."""
from pathlib import Path
import queue
import tempfile
import threading
from server_look.localization.localized_ui import tk
from server_look.localization.localized_ui import ttk, messagebox

from server_look.files.file_transfer import Transfer, local_name


class RemoteDrag:
    def __init__(self, local):
        self.local = local
        self.remote = local.resources
        self.feedback = None
        self.origin = None
        self.dragging = False
        self.ready_key = None
        self.paths = ()
        tree = self.remote.files
        tree.bind('<ButtonPress-1>', self.press, add='+')
        tree.bind('<B1-Motion>', self.motion, add='+')
        tree.bind('<ButtonRelease-1>', self.release, add='+')
        tree.bind('<Destroy>', lambda event: self.clear_feedback(), add='+')
        tree.bind('<Escape>', self.cancel_drag, add='+')
        # Ordinary Tk roots used by unit tests do not load the native extension.
        if not tree.tk.call('info', 'commands', 'tkdnd::drag_source'):
            return
        from tkinterdnd2 import DND_FILES
        tree.drag_source_register(1, DND_FILES)
        # Choose internal transfer or native export after the pointer moves.
        tags = tree.bindtags()
        tree.bindtags(tuple(tag for tag in tags if tag != 'TkDND_Drag1'))
        tree.dnd_bind('<<DragInitCmd>>', self.begin)
        tree.dnd_bind('<<DragEndCmd>>', self.end)
        local.files.drop_target_register(DND_FILES)
        local.files.dnd_bind('<<Drop>>', self.drop)
        local.files.bind('<ButtonPress-1>', lambda event: self.press(event, local.files), add='+')
        local.files.drag_source_register(1, DND_FILES)
        tags = local.files.bindtags()
        local.files.bindtags(('TkDND_Drag1',) + tuple(tag for tag in tags if tag != 'TkDND_Drag1'))
        local.files.dnd_bind('<<DragInitCmd>>', self.begin_local)
        tree.drop_target_register(DND_FILES)
        tree.dnd_bind('<<Drop>>', self.upload)

    def press(self, event, tree=None):
        tree = tree if tree is not None else self.remote.files
        if tree is self.remote.files:
            self.origin = (event.x_root, event.y_root)
            self.dragging = False
        row = tree.identify_row(event.y)
        selection = tree.selection()
        # Preserve an existing multi-selection when starting a plain drag.
        if row in selection and not event.state & 0x0005:
            tree.focus(row)
            return 'break'

    def local_destination(self, x, y):
        tree = self.local.files
        if not (tree.winfo_rootx() <= x < tree.winfo_rootx() + tree.winfo_width()
                and tree.winfo_rooty() <= y < tree.winfo_rooty() + tree.winfo_height()):
            return None
        row = tree.identify_row(y - tree.winfo_rooty())
        target = self.local.items.get(row)
        return target if target and target.is_dir() else self.local.current

    def clear_feedback(self):
        if self.feedback is not None:
            self.feedback.destroy()
            self.feedback = None
        if self.remote.files.winfo_exists():
            self.remote.files.configure(cursor='')

    def cancel_drag(self, event=None):
        self.origin = None
        self.dragging = False
        self.clear_feedback()

    def show_feedback(self, event, destination):
        tree = self.remote.files
        tree.configure(cursor='hand2' if destination is not None else 'fleur')
        if self.feedback is None:
            self.feedback = tk.Toplevel(self.local.page.root)
            self.feedback.overrideredirect(True)
            self.feedback.attributes('-topmost', True)
            ttk.Label(self.feedback, text=f'下载 {len(tree.selection())} 项',
                      style='Tooltip.TLabel', padding=(10, 5)).pack()
        self.feedback.geometry(f'+{event.x_root + 18}+{event.y_root + 22}')

    def motion(self, event):
        if self.origin is None:
            return
        if max(abs(event.x_root - self.origin[0]), abs(event.y_root - self.origin[1])) < 7:
            return
        if not self.remote.files.selection():
            return
        self.dragging = True
        destination = self.local_destination(event.x_root, event.y_root)
        self.show_feedback(event, destination)
        if destination is not None:
            self.local.status.set(f'松开鼠标下载到：{destination}')
            return 'break'
        root = self.local.page.root.winfo_toplevel()
        inside = (root.winfo_rootx() <= event.x_root < root.winfo_rootx() + root.winfo_width()
                  and root.winfo_rooty() <= event.y_root < root.winfo_rooty() + root.winfo_height())
        tree = self.remote.files
        if not inside and tree.tk.call('info', 'commands', 'tkdnd::_init_drag'):
            self.clear_feedback()
            self.origin = None
            tree.tk.call('tkdnd::_init_drag', 1, str(tree), event.state,
                         event.x_root, event.y_root, event.x, event.y)
        return 'break'

    def release(self, event):
        self.clear_feedback()
        dragging = self.dragging and self.origin is not None
        self.origin = None
        self.dragging = False
        if dragging:
            destination = self.local_destination(event.x_root, event.y_root)
            if destination is not None:
                self.download_to(destination)
            return 'break'

    def download_to(self, destination):
        local = self.local
        if local.active or not local.page.connection:
            local.status.set('请先连接服务器并等待当前传输结束')
            return
        sources = [self.remote.entries[i]['path'] for i in self.remote.files.selection()
                   if i in self.remote.entries]
        if not sources:
            return
        if not messagebox.askyesno('拖拽下载',
                f'下载 {len(sources)} 项到：\n{destination}\n同名文件覆盖，文件夹合并。继续？',
                default='no', parent=local.page.root):
            return
        connection = local.page.connection
        transfer = local.transfer = Transfer()
        local.launch(lambda: transfer.run_many_connection(connection, 'download', sources,
                     Path(destination).as_posix()), f'下载 {len(sources)} 项')

    def begin_local(self, event):
        local = self.local
        if local.active:
            local.status.set('请等待当前传输结束')
            return 'refuse_drop'
        paths = tuple(str(local.items[row]) for row in local.files.selection() if row in local.items)
        if not paths or not all(Path(path).exists() for path in paths):
            return 'refuse_drop'
        return ('copy', 'DND_Files', paths)

    def upload(self, event):
        local = self.local
        if local.active or not local.page.connection or local.page.readonly.get():
            local.status.set('请连接服务器、关闭只读模式并等待当前传输结束')
            return 'refuse_drop'
        tree = self.remote.files
        try:
            paths = tuple(Path(p) for p in tree.tk.splitlist(event.data))
            if not paths or not all(p.is_absolute() and p.exists() for p in paths):
                raise ValueError('拖入项必须是存在的本地文件或文件夹')
        except (ValueError, OSError, tk.TclError) as exc:
            local.status.set(str(exc))
            return 'refuse_drop'
        row = tree.identify_row(event.y_root - tree.winfo_rooty())
        entry = self.remote.entries.get(row)
        destination = entry['path'] if entry and entry.get('is_dir') else self.remote.current
        if not destination:
            local.status.set('请先打开服务器目录')
            return 'refuse_drop'
        if not messagebox.askyesno('拖拽上传',
                f'服务器：{local.page.connected_address}\n上传 {len(paths)} 项到：\n{destination}\n\n同名文件覆盖，文件夹合并。中断可能留下部分文件。继续？',
                default='no', parent=local.page.root):
            return 'refuse_drop'
        transfer = Transfer()
        connection = local.page.connection
        local.transfer = transfer
        local.launch(lambda: transfer.run_many_connection(connection, 'upload',
                     [p.as_posix() for p in paths], destination), f'上传 {len(paths)} 项')
        return 'copy'

    def begin(self, event):
        local = self.local
        if local.active or not local.page.connection:
            local.status.set('请先连接服务器并等待当前传输结束')
            return 'refuse_drop'
        entries = [self.remote.entries[i] for i in self.remote.files.selection() if i in self.remote.entries]
        if not entries:
            return 'refuse_drop'
        key = (local.page.generation, tuple((e['path'], e.get('size'), e.get('modified')) for e in entries))
        if key != self.ready_key or not all(Path(p).exists() for p in self.paths):
            if not self.prepare(entries, key):
                return 'refuse_drop'
        local.status.set(f'可拖出 {len(self.paths)} 项；若已松开鼠标，请再次拖动（无需重新下载）')
        return ('copy', 'DND_Files', self.paths)

    def prepare(self, entries, key):
        """Keep Tk responsive during initial download; never export partial files."""
        local = self.local
        connection = local.page.connection
        try:
            names = [local_name(Path(e['path']).name) for e in entries]
            if len({n.casefold() for n in names}) != len(names):
                raise ValueError('选中项含 Windows 下重名的文件')
            folder = Path(tempfile.mkdtemp(prefix='server-look-drag-'))
        except (ValueError, OSError) as exc:
            local.status.set(str(exc))
            return False
        transfer = Transfer()
        local.transfer = transfer
        local.active = True
        result = queue.Queue()
        window = tk.Toplevel(local.page.root)
        window.title('正在下载拖拽文件')
        window.transient(local.page.root)
        window.geometry('510x165')
        ttk.Label(window, text=f'正在下载 {len(entries)} 项到临时目录…\n完成后可拖到 Windows 资源管理器。\n若等待时已松开鼠标，请完成后再次拖动。', padding=16).pack(fill='x')
        progress = ttk.Progressbar(window, mode='indeterminate')
        progress.pack(fill='x', padx=16)
        progress.start()
        ttk.Button(window, text='取消', command=transfer.cancel).pack(pady=10)
        window.protocol('WM_DELETE_WINDOW', transfer.cancel)
        local.status.set('首次拖拽：正在下载文件，可在弹窗中取消')

        def work():
            try:
                transfer.run_many_connection(connection, 'download', [e['path'] for e in entries], folder.as_posix())
                transfer.check()
                result.put(None)
            except Exception as exc:
                result.put(str(exc))

        success = False

        def poll():
            nonlocal success
            if not window.winfo_exists():
                transfer.cancel()
                return
            try:
                error = result.get_nowait()
            except queue.Empty:
                window.after(80, poll)
                return
            local.active = False
            local.transfer = None
            if error or local.page.generation != key[0]:
                local.status.set('拖拽未完成：' + (error or '服务器连接已更改'))
            else:
                self.paths = tuple(str(folder / name) for name in names)
                self.ready_key = key
                success = True
            progress.stop()
            window.destroy()

        threading.Thread(target=work, daemon=True).start()
        window.after(80, poll)
        window.wait_window()
        return success

    def end(self, event):
        # Windows may still be reading these paths after the OLE drop returns.
        # Keep staging files in TEMP instead of deleting them on app close.
        if self.paths:
            self.local.status.set('拖拽结束；临时文件保留在 ' + str(Path(self.paths[0]).parent))

    def drop(self, event):
        local = self.local
        if local.active:
            return 'refuse_drop'
        paths = tuple(Path(p) for p in local.files.tk.splitlist(event.data))
        if not paths:
            return 'refuse_drop'
        row = local.files.identify_row(event.y_root - local.files.winfo_rooty())
        item = local.items.get(row)
        destination = item if item and item.is_dir() else local.current
        if not messagebox.askyesno('复制到本地', f'复制 {len(paths)} 项到：\n{destination}\n\n同名文件覆盖，文件夹合并。继续？',
                                  default='no', parent=local.page.root):
            return 'refuse_drop'
        transfer = Transfer()
        local.transfer = transfer
        local.launch(lambda: transfer.copy_local(paths, destination), f'复制 {len(paths)} 项到本地')
        return 'copy'
