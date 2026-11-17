"""A non-editable gutter drawing only the text widget's visible line numbers."""
import tkinter as tk
from tkinter import font


class LineNumbers(tk.Canvas):
    def __init__(self, master, text, scrollbar):
        super().__init__(master, width=32, background='#f1f3f5',
                         highlightthickness=0, borderwidth=0, takefocus=False)
        self.text = text
        self.scrollbar = scrollbar
        self.pending = None
        text.configure(yscrollcommand=self.on_scroll)
        text.bind('<<Modified>>', self.schedule, add='+')
        text.bind('<Configure>', self.schedule, add='+')
        self.bind('<Destroy>', self.on_destroy)
        self.schedule()

    def on_scroll(self, first, last):
        self.scrollbar.set(first, last)
        self.schedule()

    def schedule(self, event=None):
        if self.pending is None:
            self.pending = self.after_idle(self.redraw)

    def redraw(self):
        self.pending = None
        text_font = font.Font(root=self.text, font=self.text.cget('font'))
        digits = len(self.text.index('end-1c').split('.')[0])
        width = text_font.measure('9' * digits) + 16
        if int(self.cget('width')) != width:
            self.configure(width=width)
        self.delete('all')
        index = self.text.index('@0,0')
        while True:
            position = self.text.dlineinfo(index)
            if position is None:
                break
            self.create_text(width - 8, position[1], anchor='ne',
                             text=index.split('.')[0], font=self.text.cget('font'),
                             fill='#626b73')
            index = self.text.index(index + '+1line')

    def on_destroy(self, event):
        if self.pending is not None:
            self.after_cancel(self.pending)
            self.pending = None
