"""Compatibility for terminal queries unsupported by pyte's base screen."""
from pyte import HistoryScreen
from pyte import modes


class TerminalScreen(HistoryScreen):
    def report_device_status(self, mode, private=False):
        if not private:
            return super().report_device_status(mode)
        if mode == 6:
            row = self.cursor.y + 1
            if modes.DECOM in self.mode and self.margins:
                row -= self.margins.top
            self.write_process_input(f'\x1b[?{row};{self.cursor.x + 1}R')
