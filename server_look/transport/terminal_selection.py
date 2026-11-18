"""Track explicitly typed shell text; never treat arbitrary output as editable."""
from wcwidth import wcswidth


class ShellLine:
    def __init__(self):
        self.clear()

    def clear(self):
        self.row = None
        self.prefix = self.text = ''
        self.cursor = 0

    def record(self, screen, text):
        if text.startswith('\x1b[200~') and text.endswith('\x1b[201~'):
            text = text[6:-6]
        if text and all(char.isprintable() for char in text):
            if self.row is None:
                self.row = screen.cursor.y
                self.prefix = ''.join(screen.buffer[self.row][x].data for x in range(screen.cursor.x))
            self.text = self.text[:self.cursor] + text + self.text[self.cursor:]
            self.cursor += len(text)
        elif self.row is not None and text in ('\x1b[D', '\x1bOD'):
            if self.cursor == 0:
                self.clear()
            else:
                self.cursor -= 1
        elif self.row is not None and text in ('\x1b[C', '\x1bOC'):
            if self.cursor == len(self.text):
                self.clear()
            else:
                self.cursor += 1
        elif self.row is not None and text == '\x7f' and self.cursor:
            self.text = self.text[:self.cursor - 1] + self.text[self.cursor:]
            self.cursor -= 1
        elif self.row is not None and text == '\x1b[3~':
            self.text = self.text[:self.cursor] + self.text[self.cursor + 1:]
        else:
            self.clear()

    def matches(self, screen):
        if self.row is None:
            return False
        # Render the tracked input with the same terminal wrapping rules. The
        # prompt may have scrolled since typing started; anchor at the cursor.
        import pyte
        rendered = self.prefix + self.text
        preview = pyte.Screen(screen.columns, max(screen.lines, len(rendered) + 1))
        pyte.Stream(preview).feed(rendered)
        cursor = pyte.Screen(screen.columns, max(screen.lines, len(rendered) + 1))
        pyte.Stream(cursor).feed(self.prefix + self.text[:self.cursor])
        start = screen.cursor.y - cursor.cursor.y
        return (start >= 0 and start + preview.cursor.y < screen.lines
                and screen.cursor.x == cursor.cursor.x
                and all(screen.display[start + row].rstrip() == preview.display[row].rstrip()
                        for row in range(preview.cursor.y + 1)))

    def deletion(self, screen, start, end):
        """Offsets are Unicode characters in the displayed row, including prompt."""
        start, end = start - len(self.prefix), end - len(self.prefix)
        if (wcswidth(self.prefix + self.text) >= screen.columns
                or not self.matches(screen) or not 0 <= start < end <= len(self.text)):
            return None
        distance = end - self.cursor
        move = '\x1b[C' * distance if distance >= 0 else '\x1b[D' * -distance
        return move + '\x7f' * (end - start), start, end

    def deleted(self, start, end):
        self.text = self.text[:start] + self.text[end:]
        self.cursor = start
