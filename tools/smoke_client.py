"""Read-only end-to-end desktop check against the configured server."""
import time
import sys
import tkinter as tk

from server_look.app.server_page import ServerPage

root = tk.Tk()
app = ServerPage(root)
if len(sys.argv) > 1:
    app.host.set(sys.argv[1])
app.readonly.set(True)
app.connect()
deadline = time.monotonic() + 45
while not app.fresh and time.monotonic() < deadline:
    root.update()
    time.sleep(0.05)
assert app.fresh, app.status.get()
assert app.data['containers']
assert app.tasks.get_children(), 'Default view should show container processes even when NPU is idle'
assert '加速卡任务' in app.summary.get()
app.all_tasks.set(True)
app.render()
assert app.tasks.get_children()
app.tasks.selection_set(app.tasks.get_children()[0])
root.update()
assert str(app.term_button['state']) == 'disabled'
app.tabs.select(1)
app.containers.selection_set(app.containers.get_children()[0])
root.update()
assert str(app.stop_button['state']) == 'disabled'
assert 'mounts' in app.details.get('1.0', 'end')
print('PASS: real SSH, GUI render, container details, all tasks, read-only action guards')
app.close()
