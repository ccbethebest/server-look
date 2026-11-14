"""Read-only verification of simultaneous SSH sessions in separate pages."""
import time
import tkinter as tk

from desktop_app import MultiServerApp


root = tk.Tk()
app = MultiServerApp(root)
try:
    pages = list(app.pages.values())
    for page in pages:
        page.readonly.set(True)
    app.connect_all()
    deadline = time.monotonic() + 50
    while not all(page.fresh for page in pages) and time.monotonic() < deadline:
        root.update()
        time.sleep(0.05)
    for page in pages:
        assert page.fresh, f'{page.host.get()}: {page.status.get()}'
        assert page.data['containers']
        assert page.tasks.get_children()
        assert page.host.get() in app.notebook.tab(page.root, 'text')
        print(f"PASS {page.host.get()}: {len(page.data['containers'])} containers, "
              f"{len(page.tasks.get_children())} tasks")
    pages[0].disconnect()
    assert pages[1].fresh and pages[1].connection
    assert pages[1].tasks.get_children()
    print('PASS: disconnecting one page preserves the other server state')
finally:
    app.close()
