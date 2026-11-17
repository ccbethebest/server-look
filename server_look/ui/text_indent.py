"""Shared four-space indentation for file and Python script editors."""


def bind_indentation(text):
    text.bind('<Tab>', lambda event: indent(text))
    text.bind('<Shift-Tab>', lambda event: indent(text, backwards=True))
    text.bind('<ISO_Left_Tab>', lambda event: indent(text, backwards=True))
    text.bind('<Control-slash>', lambda event: toggle_comment(text))


def indent(text, backwards=False):
    if str(text.cget('state')) == 'disabled':
        return 'break'
    selection = text.tag_ranges('sel')
    start, end = map(str, selection) if selection else (text.index('insert'), text.index('insert'))
    first, last = int(start.split('.')[0]), int(end.split('.')[0])
    if selection and end.endswith('.0') and last > first:
        last -= 1
    # One undo action for the entire block, separate from adjacent typing.
    separators = text.cget('autoseparators')
    text.edit_separator()
    text.configure(autoseparators=False)
    try:
        if not selection and not backwards:
            text.insert('insert', '    ')
        else:
            for line in range(first, last + 1):
                index = str(line) + '.0'
                if backwards:
                    prefix = text.get(index, index + '+4c')
                    count = 1 if prefix.startswith('\t') else len(prefix) - len(prefix.lstrip(' '))
                    if count:
                        text.delete(index, index + '+' + str(count) + 'c')
                else:
                    text.insert(index, '    ')
            if selection:
                text.tag_remove('sel', '1.0', 'end')
                end = text.index(str(last + 1) + '.0')
                if text.compare(end, '>', 'end-1c'):
                    end = text.index('end-1c')
                text.tag_add('sel', str(first) + '.0', end)
    finally:
        text.configure(autoseparators=separators)
        text.edit_separator()
    return 'break'


def toggle_comment(text):
    """Toggle # line comments without changing indentation or blank lines."""
    if str(text.cget('state')) == 'disabled':
        return 'break'
    selection = text.tag_ranges('sel')
    start, end = map(str, selection) if selection else (text.index('insert'), text.index('insert'))
    first, last = int(start.split('.')[0]), int(end.split('.')[0])
    if selection and end.endswith('.0') and last > first:
        last -= 1
    lines = []
    for number in range(first, last + 1):
        line = text.get(str(number) + '.0', str(number) + '.end')
        body = line.lstrip(' \t')
        if body:
            lines.append((number, len(line) - len(body), body))
    uncomment = bool(lines) and all(body.startswith('#') for _, _, body in lines)
    separators = text.cget('autoseparators')
    text.edit_separator()
    text.configure(autoseparators=False)
    try:
        for number, column, body in lines:
            index = str(number) + '.' + str(column)
            if uncomment:
                count = 2 if body.startswith('# ') else 1
                text.delete(index, index + '+' + str(count) + 'c')
            else:
                text.insert(index, '# ')
    finally:
        text.configure(autoseparators=separators)
        text.edit_separator()
    return 'break'
