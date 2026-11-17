"""Compatibility for terminal queries unsupported by pyte's base screen."""
from pyte import HistoryScreen
from pyte import modes


class TerminalScreen(HistoryScreen):
    _screen_fields = ('buffer', 'cursor', 'savepoints', 'history', 'margins', 'tabstops')

    def reset(self):
        self._primary = None
        super().reset()

    def set_mode(self, *values, **kwargs):
        if kwargs.get('private') and any(value in (47, 1047, 1049) for value in values):
            if self._primary is None:
                self._primary = ({name: getattr(self, name) for name in self._screen_fields},
                                 self.columns, self.lines)
                alternate = HistoryScreen(self.columns, self.lines, history=0)
                for name in self._screen_fields:
                    setattr(self, name, getattr(alternate, name))
                self.dirty.update(range(self.lines))
        super().set_mode(*values, **kwargs)

    def reset_mode(self, *values, **kwargs):
        if kwargs.get('private') and any(value in (47, 1047, 1049) for value in values):
            if self._primary is not None:
                columns, lines = self.columns, self.lines
                state, self.columns, self.lines = self._primary
                self._primary = None
                for name, value in state.items():
                    setattr(self, name, value)
                self.resize(lines=lines, columns=columns)
                self.dirty.update(range(self.lines))
        super().reset_mode(*values, **kwargs)

    def report_device_status(self, mode, private=False):
        if not private:
            return super().report_device_status(mode)
        if mode == 6:
            row = self.cursor.y + 1
            if modes.DECOM in self.mode and self.margins:
                row -= self.margins.top
            self.write_process_input(f'\x1b[?{row};{self.cursor.x + 1}R')
