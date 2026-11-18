"""Xterm keyboard sequences for the embedded SSH terminal."""
import sys


def encode_key(key, char='', state=0, application_cursor=False):
    # Tk/Windows uses Mod1 (8) for Num Lock, and 0x20000 for Alt.
    alt_mask = 0x20000 if sys.platform == 'win32' else (16 if sys.platform == 'darwin' else 8)
    alt = bool(state & alt_mask)
    modifier = 1 + bool(state & 1) + 2 * alt + 4 * bool(state & 4)
    cursor = {'Up': 'A', 'Down': 'B', 'Right': 'C', 'Left': 'D', 'Home': 'H', 'End': 'F'}
    if key in cursor:
        final = cursor[key]
        if modifier > 1:
            return f'\x1b[1;{modifier}{final}'
        return ('\x1bO' if application_cursor else '\x1b[') + final
    function = {'F1': 'P', 'F2': 'Q', 'F3': 'R', 'F4': 'S'}
    if key in function:
        return (f'\x1b[1;{modifier}' if modifier > 1 else '\x1bO') + function[key]
    tilde = {'Insert': 2, 'Delete': 3, 'Prior': 5, 'Next': 6,
             'F5': 15, 'F6': 17, 'F7': 18, 'F8': 19, 'F9': 20, 'F10': 21, 'F11': 23, 'F12': 24}
    if key in tilde:
        return f'\x1b[{tilde[key]}' + (f';{modifier}' if modifier > 1 else '') + '~'
    if key in ('Tab', 'ISO_Left_Tab') and (state & 1 or key == 'ISO_Left_Tab'):
        return '\x1b[Z'
    if state & 4 and len(key) == 1 and 'a' <= key.lower() <= 'z':
        return chr(ord(key.lower()) - 96)
    value = {'Return': '\r', 'BackSpace': '\x7f', 'Tab': '\t', 'Escape': '\x1b'}.get(key, char)
    return ('\x1b' if alt and value else '') + value
