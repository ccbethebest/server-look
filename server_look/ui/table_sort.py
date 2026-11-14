"""Reusable three-state sorting for flat Treeviews, including refreshed rows."""
import re


def sort_key(value):
    text = str(value).strip().replace(',', '').removesuffix('（不完整）')
    match = re.fullmatch(r'([\d.]+)\s*(B|KiB|MiB|GiB|TiB|PiB|%)?', text)
    if match:
        try:
            return (0, float(match[1]) * (1024 ** ('B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB').index(match[2]) if match[2] not in (None, '%') else 1))
        except ValueError:
            pass
    return (1, tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in re.split(r'(\d+)', text)))


class TableSort:
    def __init__(self, tree):
        self.tree, self.column, self.direction = tree, None, 0
        self.original = []
        self.labels = {}
        for column in ('#0', *tree['columns']):
            label = getattr(tree, '_headings', {}).get(column, tree.heading(column, 'text'))
            if label:
                self.labels[column] = label
                tree.heading(column, command=lambda c=column: self.toggle(c))

    def toggle(self, column):
        self.direction = (self.direction + 1) % 3 if self.column == column else 1
        self.column = column
        self.apply()

    def refreshed(self):
        self.original = list(self.tree.get_children())
        self.apply()

    def apply(self):
        tree = self.tree
        rows = list(tree.get_children())
        original = set(self.original)
        rows = [row for row in self.original if tree.exists(row)] + [row for row in rows if row not in original]
        if self.direction:
            # Always start from the incoming order, so equal values remain stable.
            rows.sort(key=lambda row: sort_key(tree.item(row, 'text') if self.column == '#0' else tree.set(row, self.column)), reverse=self.direction == 2)
        for index, row in enumerate(rows):
            tree.move(row, '', index)
        for column, label in self.labels.items():
            suffix = (' ↑' if self.direction == 1 else ' ↓') if column == self.column and self.direction else ''
            tree.heading(column, text=label + suffix)


def enable_sort(tree):
    tree.sorting = TableSort(tree)
    return tree.sorting
