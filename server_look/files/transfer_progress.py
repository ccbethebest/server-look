"""Shared byte-based progress presentation for transfer panes and drag export."""


def format_size(size):
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB', 'PB'):
        if value < 1000 or unit == 'PB':
            return f'{value:.2f} {unit}' if unit != 'B' else f'{int(value)} B'
        value /= 1000


def update_progress(bar, update):
    total, done = update.get('bytes_total'), update.get('bytes_done', 0)
    items = f"{update['completed']}/{update['total']} 项"
    if total is None:
        return ('正在统计总大小… · ' if update.get('phase') != 'transferring'
                else '此连接不提供实时字节进度 · ') + items
    percentage = min(100, done / total * 100) if total else (100 if update['completed'] == update['total'] else 0)
    if str(bar.cget('mode')) != 'determinate':
        bar.stop()
        bar.configure(mode='determinate', maximum=100)
    bar.configure(value=percentage)
    return f'已传输 {format_size(done)} / 总计 {format_size(total)} · {percentage:.1f}% · {items}'
