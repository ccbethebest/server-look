"""Native text editing actions for the command entry and Python editor."""
from server_look.localization.localized_ui import tk, Menu
import sys


def has_selection(widget):
    return bool(widget.tag_ranges('sel')) if isinstance(widget, tk.Text) else widget.selection_present()


def delete_selection(widget):
    if has_selection(widget):
        widget.delete('sel.first', 'sel.last')
    return 'break'


def bind_text_menu(widget):
    menu = Menu(widget, tearoff=False)
    menu.add_command(label='复制', command=lambda: widget.event_generate('<<Copy>>'))
    menu.add_command(label='粘贴', command=lambda: widget.event_generate('<<Paste>>'))
    menu.add_command(label='删除选中文字', command=lambda: delete_selection(widget))
    def right_click(event):
        widget.focus_set()
        if not has_selection(widget):
            widget.event_generate('<<Paste>>')
        else:
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        return 'break'
    widget.bind('<Button-3>', right_click)
    if sys.platform == 'darwin':
        widget.bind('<Button-2>', right_click)
    return menu
