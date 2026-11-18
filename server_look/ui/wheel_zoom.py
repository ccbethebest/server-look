"""Handle Ctrl+wheel before widget scrolling, including newly opened dialogs."""
from server_look.config.ui_preferences import save_preferences
from server_look.localization.localized_ui import messagebox


class WheelZoom:
    def __init__(self, app):
        self.app = app
        self.pending_save = None
        self.tag = 'ServerLookWheelZoom'
        root = app.root
        for event in ('<Control-MouseWheel>', '<Control-Button-4>', '<Control-Button-5>'):
            root.bind_class(self.tag, event, self.on_wheel)
        root.bind_all('<Map>', lambda event: self.attach(event.widget), add='+')
        self.attach(root)

    def attach(self, widget):
        tags = widget.bindtags()
        if self.tag not in tags:
            widget.bindtags((self.tag, *tags))
        for child in widget.winfo_children():
            self.attach(child)

    def on_wheel(self, event):
        delta = getattr(event, 'delta', 0)
        number = getattr(event, 'num', None)
        if not delta and number not in (4, 5):
            return 'break'
        direction = 1 if delta > 0 or number == 4 else -1
        values = self.app.preferences
        scale = max(50, min(200, values['global_scale'] + direction * 10))
        if scale != values['global_scale']:
            self.app.preferences = dict(values, global_scale=scale)
            self.app.root._serverlook_options = self.app.preferences
            self.app.retheme()
            if self.pending_save:
                self.app.root.after_cancel(self.pending_save)
            self.pending_save = self.app.root.after(350, self.persist)
        return 'break'

    def persist(self):
        if self.pending_save:
            self.app.root.after_cancel(self.pending_save)
            self.pending_save = None
        try:
            save_preferences(self.app.preferences)
        except OSError as exc:
            messagebox.showwarning('设置', str(exc), parent=self.app.root)
