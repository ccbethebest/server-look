"""Record keyboard shortcuts without allowing mouse events or Tcl scripts."""
import re

_MODIFIERS = {'Control_L', 'Control_R', 'Shift_L', 'Shift_R', 'Alt_L', 'Alt_R',
              'Meta_L', 'Meta_R', 'Super_L', 'Super_R', 'Caps_Lock', 'Num_Lock'}
_PATTERN = re.compile(r'<(?:(?:Control|Shift|Alt)-)*(?:[a-zA-Z0-9]|F(?:[1-9]|[12][0-9]|3[0-5])|Return|Tab|space|Escape|Delete|BackSpace|Insert|Home|End|Prior|Next|Left|Right|Up|Down|comma|period|slash|backslash|semicolon|apostrophe|minus|equal|bracketleft|bracketright|grave)>')


def valid_shortcut(value):
    return isinstance(value, str) and (value == '无' or bool(_PATTERN.fullmatch(value)))


def key_sequence(event):
    key = event.keysym
    if key in _MODIFIERS:
        return None
    if len(key) == 1 and key.isalpha():
        key = key.upper() if event.state & 1 else key.lower()
    modifiers = []
    for mask, name in ((4, 'Control'), (1, 'Shift'), (0x20008, 'Alt')):
        if event.state & mask:
            modifiers.append(name)
    sequence = '<' + '-'.join((*modifiers, key)) + '>'
    return sequence if valid_shortcut(sequence) else None


def shortcut_control(parent, variable):
    from server_look.localization.localized_ui import ttk
    frame = ttk.Frame(parent)
    button = ttk.Button(frame, textvariable=variable, width=23, takefocus=True)
    button.pack(side='left')
    recording = False

    def stop(event=None):
        nonlocal recording
        recording = False
        button.configure(textvariable=variable)

    def start():
        nonlocal recording
        recording = True
        button.configure(textvariable='', text='请按下快捷键…')
        button.focus_set()

    def press(event):
        if not recording:
            return
        if event.keysym == 'Escape':
            stop()
        else:
            sequence = key_sequence(event)
            if sequence:
                variable.set(sequence)
                stop()
        return 'break'

    button.configure(command=start)
    button.bind('<KeyPress>', press)
    button.bind('<FocusOut>', stop)
    ttk.Button(frame, text='清除', width=7, command=lambda: (variable.set('无'), stop())).pack(side='left', padx=(4, 0))
    return frame
