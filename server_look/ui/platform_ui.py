"""Native Mac shortcuts without changing SSH Control-key semantics."""
import sys


def command_aliases(widget):
    if sys.platform == 'darwin':
        for sequence in widget.bind():
            if 'Control-' in sequence:
                widget.bind(sequence.replace('Control-', 'Command-'), widget.bind(sequence))
        undo = widget.bind('<Control-z>')
        if undo:
            def redo(event):
                widget.event_generate('<<Redo>>')
                return 'break'
            widget.bind('<Command-Shift-Z>', redo)


def monospace():
    return 'Menlo' if sys.platform == 'darwin' else 'Consolas'


def shortcut_sequences(sequence):
    if sys.platform == 'darwin' and 'Control-' in sequence:
        return (sequence, sequence.replace('Control-', 'Command-'))
    return (sequence,)


def window_mode(root, maximized):
    if sys.platform == 'darwin':
        root.state('normal')
        if maximized:
            root.geometry(f'{root.winfo_screenwidth()}x{root.winfo_screenheight() - 80}+0+25')
    else:
        root.state('zoomed' if maximized else 'normal')
