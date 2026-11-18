import sys
"""Bounded, cancellable filename search isolated from the GUI process (stdlib only)."""
from collections import deque
import fnmatch
import multiprocessing
import os
import re
import time

MODES = ('包含', '完全匹配', '近似匹配', '通配符', '正则表达式')

def subsequence(needle, name):
    """Approximate matching: characters occur in order, with gaps allowed."""
    characters = iter(name)
    return all(any(character == wanted for character in characters) for wanted in needle)


def matches_name(name, needle, mode, expression=None):
    if expression:
        return bool(expression.search(name))
    if mode == '包含':
        return needle in name
    if mode == '完全匹配':
        return needle == name
    if mode == '近似匹配':
        return subsequence(needle, name)
    return fnmatch.fnmatchcase(name, needle)


def validate_search(path, pattern, mode='包含', case_sensitive=False, recursive=True, kind='全部'):
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path:
        raise ValueError('请输入绝对搜索目录')
    if not isinstance(pattern, str) or not pattern or len(pattern) > 512:
        raise ValueError('请输入 1–512 字符的搜索条件')
    if mode not in MODES or kind not in ('全部', '文件', '文件夹'):
        raise ValueError('未知匹配模式或类型')
    if mode == '正则表达式':
        re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)
    return dict(path=path, pattern=pattern, mode=mode, case_sensitive=bool(case_sensitive), recursive=bool(recursive), kind=kind)

def directory_size(path, limit=100000):
    """Count regular files without following links; report incomplete totals explicitly."""
    pending, total, scanned, complete = [path], 0, 0, True
    while pending:
        try:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    scanned += 1
                    if scanned > limit:
                        return total, False
                    try:
                        if entry.is_symlink() or getattr(os.path, 'isjunction', lambda p: False)(entry.path):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        complete = False
        except OSError:
            complete = False
    return total, complete


def _search_worker(pipe, options, limit, scan_limit):
    """Send batches so cancellation/timeout can still return partial matches."""
    try:
        root, pattern, mode = options['path'], options['pattern'], options['mode']
        if not os.path.isdir(root):
            raise ValueError('搜索目录不存在或不是文件夹')
        if not os.access(root, os.R_OK):
            raise PermissionError('没有读取搜索目录的权限')
        sensitive = options['case_sensitive']
        expression = re.compile(pattern, 0 if sensitive else re.IGNORECASE) if mode == '正则表达式' else None
        needle = pattern if sensitive else pattern.casefold()
        pending, batch = deque([root]), []
        sent_at = time.monotonic()
        scanned = matched = skipped = 0
        reason = '完成'
        while pending:
            directory = pending.popleft()
            try:
                with os.scandir(directory) as entries:
                    for item in entries:
                        scanned += 1
                        try:
                            folder = item.is_dir(follow_symlinks=False)
                            junction = folder and getattr(os.path, 'isjunction', lambda p: False)(item.path)
                            if folder and options['recursive'] and not junction and not item.is_symlink():
                                pending.append(item.path)
                            name = item.name if sensitive else item.name.casefold()
                            matches = matches_name(item.name if expression else name, needle, mode, expression)
                            if matches and (options['kind'] == '全部' or (options['kind'] == '文件夹') == folder):
                                metadata = item.stat(follow_symlinks=False)
                                size, complete = (None, True) if folder else (metadata.st_size, True)
                                if folder and options.get('directory_sizes') and not junction and not item.is_symlink():
                                    size, complete = directory_size(item.path)
                                batch.append({'name': item.name, 'path': item.path, 'directory': folder,
                                              'size': size, 'size_complete': complete, 'modified': metadata.st_mtime})
                                matched += 1
                        except OSError:
                            skipped += 1
                        if batch and (len(batch) >= 100 or time.monotonic() - sent_at >= 0.1):
                            pipe.send(('batch', batch))
                            batch = []
                            sent_at = time.monotonic()
                        if matched >= limit or scanned >= scan_limit:
                            reason = '达到结果上限' if matched >= limit else '达到扫描上限'
                            pending.clear()
                            break
            except OSError:
                skipped += 1
        if batch:
            pipe.send(('batch', batch))
        pipe.send(('done', {'scanned': scanned, 'skipped': skipped, 'reason': reason}))
    except Exception as exc:
        pipe.send(('error', str(exc)))
    finally:
        pipe.close()

def run_search(path, pattern, mode='包含', case_sensitive=False, recursive=True, kind='全部', cancel=None, seconds=15, limit=1000, scan_limit=100000, on_batch=None, directory_sizes=False):
    options = validate_search(path, pattern, mode, case_sensitive, recursive, kind)
    options['directory_sizes'] = bool(directory_sizes)
    # Isolation also bounds pathological regular expressions. Linux remote source uses fork;
    # Windows frozen clients use spawn and freeze_support in the executable entry point.
    context = multiprocessing.get_context('fork' if sys.platform.startswith('linux') else 'spawn')
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=_search_worker, args=(send, options, limit, scan_limit), daemon=True)
    results, meta = [], {'scanned': None, 'skipped': None, 'reason': '超时，返回已完成批次'}
    started = time.monotonic()
    try:
        process.start()
        send.close()
        while time.monotonic() - started < seconds:
            if cancel is not None and cancel.is_set():
                meta['reason'] = '已停止，返回已完成批次'
                break
            if receive.poll(0.05):
                try:
                    event, data = receive.recv()
                except EOFError:
                    raise RuntimeError('搜索进程提前退出')
                if event == 'batch':
                    results.extend(data)
                    if on_batch:
                        on_batch(data)
                elif event == 'error':
                    raise ValueError(data)
                else:
                    meta = data
                    break
            elif not process.is_alive():
                raise RuntimeError('搜索进程提前退出')
    finally:
        if process.pid:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
        receive.close()
        send.close()
    return dict(results=results, **meta, elapsed=round(time.monotonic() - started, 2))
