"""Read-only Linux hardware, mount and directory collection; standard library only."""
import datetime
import os
import platform
import re
import subprocess
import shutil
import stat


def delete_entries(path, names):
    """Delete direct children only; never follow a selected symlink/junction."""
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path:
        raise ValueError('请输入绝对目录路径')
    if not isinstance(names, list) or not names:
        raise ValueError('请选择删除项')
    for name in names:
        if (not isinstance(name, str) or not name or name in ('.', '..')
                or any(c in name for c in '/\\\x00') or os.path.splitdrive(name)[0]):
            raise ValueError('删除项必须是当前目录的直接子项')
    parent = os.path.realpath(path)
    for name in dict.fromkeys(names):
        target = os.path.abspath(os.path.join(parent, name))
        if os.path.dirname(target) != parent:
            raise ValueError('删除目标超出当前目录')
        mode = os.lstat(target).st_mode
        if os.path.islink(target):
            os.unlink(target)
        elif getattr(os.path, 'isjunction', lambda p: False)(target):
            os.rmdir(target)
        elif stat.S_ISDIR(mode):
            shutil.rmtree(target)
        else:
            os.unlink(target)


def decode_mount(value):
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match[1], 8)), value)


def read_text(path):
    try:
        with open(path, encoding='utf-8', errors='replace') as stream:
            return stream.read()
    except OSError:
        return ''


def hardware():
    cpu = read_text('/proc/cpuinfo')
    model = re.search(r'^(?:model name|Hardware|Processor)\s*:\s*(.+)', cpu, re.M)
    memory = dict(re.findall(r'^(MemTotal|MemAvailable):\s+(\d+)', read_text('/proc/meminfo'), re.M))
    system = dict(re.findall(r'^(\w+)=(.*)', read_text('/etc/os-release'), re.M))
    result = {
        'CPU 架构': platform.machine(), 'CPU 型号': model[1] if model else platform.processor() or '未知',
        '逻辑 CPU': str(os.cpu_count() or '未知'), '操作系统': system.get('PRETTY_NAME', platform.system()).strip('"'),
        '内核': platform.release(),
        '内存总量': int(memory.get('MemTotal', 0)) * 1024,
        '内存可用': int(memory.get('MemAvailable', 0)) * 1024,
    }
    try:
        cpu_details = subprocess.run(['lscpu'], capture_output=True, text=True, timeout=3,
                                     env=dict(os.environ, LC_ALL='C')).stdout
        for label, title in [('Model name', 'CPU 型号'), ('Socket(s)', 'CPU 插槽'),
                             ('Core(s) per socket', '每插槽核心数'), ('Thread(s) per core', '每核心线程数')]:
            match = re.search(r'^' + re.escape(label) + r':\s*(.+)', cpu_details, re.M)
            if match:
                result[title] = match[1]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return result


def disks():
    """df handles local/network mount capacity; timeout bounds unavailable mounts."""
    result = subprocess.run(['df', '-aPT', '-B1'], capture_output=True, text=True, timeout=8,
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode and not result.stdout.strip():
        raise RuntimeError(result.stderr.strip())
    rows = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split(None, 6)
        if len(parts) != 7:
            continue
        device, kind, total, used, available, percent, mount = parts
        if kind in {'tmpfs', 'devtmpfs', 'overlay', 'squashfs', 'proc', 'sysfs', 'cgroup', 'cgroup2',
                    'devpts', 'securityfs', 'debugfs', 'tracefs', 'pstore', 'efivarfs', 'hugetlbfs',
                    'mqueue', 'configfs', 'fusectl', 'bpf', 'autofs', 'rpc_pipefs', 'binfmt_misc'} or not total.isdigit():
            continue
        if not int(total):
            continue
        rows.append(dict(device=decode_mount(device), type=kind, total=int(total), used=int(used),
                         available=int(available), percent=percent, mount=decode_mount(mount)))
    return rows


def npu_configuration(raw):
    """Accept both compact 910B and multi-column 950 npu-smi layouts."""
    cards = re.findall(r'^\|\s*(\d+)\s+(?:\|\s*)?((?:Ascend)?\d+[\w.-]*)\s*\|\s*(\w+)\s*\|', raw, re.M)
    version = re.search(r'npu-smi\s+(\S+)', raw)
    result = {'NPU 数量': str(len(cards)), 'NPU 型号': ', '.join(sorted({card[1] for card in cards})) or '未检测到昇腾设备，详情见 NPU / GPU 状态'}
    if version:
        result['NPU 驱动 / SMI 版本'] = version[1]
    for number, model, health in cards:
        result[f'NPU {number}'] = f'{model} · 健康状态 {health}'
    return result


def accelerator_occupancy(raw, tasks, hardware):
    """Count physical cards, deduplicating processes and chips on the same NPU."""
    devices = {key for key in npu_configuration(raw) if re.fullmatch(r'NPU \d+', key)}
    devices.update(key for key in hardware if re.fullmatch(r'GPU \d+', key))
    occupied = set()
    for allocations in tasks.values():
        for device in allocations:
            match = re.fullmatch(r'(\d+):\d+', device)
            occupied.add('NPU ' + match[1] if match else device)
    errors = []
    if not devices:
        errors.append('未识别到昇腾 NPU 或 NVIDIA GPU，无法判定空闲；请检查驱动、权限及命令路径')
    elif occupied - devices:
        errors.append('部分进程无法关联到物理卡，无法准确判定占用状态（可能为 MIG 设备）')
    used, total = len(occupied & devices), len(devices)
    state = 'idle' if used == 0 else 'full' if used == total else 'partial'
    return dict(state=state, used=used, total=total, idle=not occupied, errors=errors)


def collect_resources(npu=''):
    result = {'hardware': hardware(), 'disks': [], 'resource_errors': []}
    result['hardware'].update(npu_configuration(npu))
    try:
        result['disks'] = disks()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result['resource_errors'].append('磁盘采集失败：' + str(exc))
    return result


def list_directory(path, limit=3000):
    """List one level without shell interpolation, file reads or directory recursion."""
    if not isinstance(path, str) or not os.path.isabs(path) or '\x00' in path:
        raise ValueError('请输入绝对路径')
    path = os.path.realpath(path)
    entries, truncated = [], False
    with os.scandir(path) as iterator:
        for entry in iterator:
            if len(entries) >= limit:
                truncated = True
                break
            try:
                stat = entry.stat(follow_symlinks=False)
                entries.append(dict(name=entry.name, path=entry.path, is_dir=entry.is_dir(),
                                    link=entry.is_symlink(), size=stat.st_size,
                                    modified=datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')))
            except OSError:
                entries.append(dict(name=entry.name, path=entry.path, is_dir=False, link=entry.is_symlink(),
                                    size=None, modified='无法读取'))
    entries.sort(key=lambda item: (not item['is_dir'], item['name'].casefold()))
    return dict(path=path, parent=os.path.dirname(path), entries=entries, truncated=truncated)


def child_name(name):
    """Validate portable direct-child names, including Windows drive syntax."""
    import ntpath
    if (not isinstance(name, str) or not name or name in ('.', '..')
            or any(c in name for c in '/\\\x00\r\n:') or ntpath.splitdrive(name)[0]
            or name.endswith((' ', '.'))):
        raise ValueError('请输入有效的单个文件或文件夹名称')
    return name


def file_operation(path, action, names, **options):
    """Shared local/remote mutations. Refuse overwrite and unsafe archive members."""
    import zipfile
    import tarfile
    import tempfile
    if not os.path.isabs(path):
        raise ValueError('请输入绝对路径')
    parent = os.path.realpath(path)
    if not isinstance(names, list) or not names:
        raise ValueError('请先选择文件或文件夹')
    sources = [os.path.join(parent, child_name(n)) for n in dict.fromkeys(names)]
    for source in sources:
        if not os.path.lexists(source):
            raise FileNotFoundError(source)
    def reserve(target):
        if os.path.lexists(target):
            raise FileExistsError('目标已存在：' + target)
    def check_tree(source):
        if os.path.islink(source) or getattr(os.path, 'isjunction', lambda p: False)(source):
            raise ValueError('此操作暂不支持符号链接或目录联接：' + source)
        if os.path.isdir(source):
            for base, dirs, files in os.walk(source, followlinks=False):
                for name in dirs + files:
                    item = os.path.join(base, name)
                    if os.path.islink(item) or getattr(os.path, 'isjunction', lambda p: False)(item):
                        raise ValueError('目录包含链接：' + item)
                    if not os.path.isdir(item) and not stat.S_ISREG(os.lstat(item).st_mode):
                        raise ValueError('不支持特殊文件：' + item)
        elif not stat.S_ISREG(os.lstat(source).st_mode):
            raise ValueError('不支持特殊文件：' + source)
    if action == 'rename':
        if len(sources) != 1: raise ValueError('每次只能重命名一项')
        target = os.path.join(parent, child_name(options['name']))
        reserve(target)
        os.rename(sources[0], target)
    elif action == 'copy':
        destination = os.path.realpath(options['destination'])
        if not os.path.isdir(destination): raise ValueError('目标目录不存在')
        targets = [os.path.join(destination, os.path.basename(s)) for s in sources]
        for source, target in zip(sources, targets):
            reserve(target)
            if os.path.commonpath([source, target]) == source:
                raise ValueError('不能复制到自身或其子目录')
            check_tree(source)
        for source, target in zip(sources, targets):
            if os.path.isdir(source): shutil.copytree(source, target)
            else:
                with open(source, 'rb') as src, open(target, 'xb') as dst: shutil.copyfileobj(src, dst)
                shutil.copystat(source, target)
    elif action == 'compress':
        target = os.path.join(parent, child_name(options['name']))
        reserve(target)
        if not target.lower().endswith('.zip'): raise ValueError('压缩包名称需要以 .zip 结尾')
        for source in sources: check_tree(source)
        try:
            with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for source in sources:
                    if os.path.isdir(source):
                        for base, dirs, files in os.walk(source):
                            archive.write(base, os.path.relpath(base, parent))
                            for name in files:
                                item = os.path.join(base, name)
                                archive.write(item, os.path.relpath(item, parent))
                    else: archive.write(source, os.path.basename(source))
        except Exception:
            if os.path.isfile(target): os.unlink(target)
            raise
    elif action == 'extract':
        if len(sources) != 1: raise ValueError('每次只能解压一个压缩包')
        check_tree(sources[0])
        target = os.path.join(parent, child_name(options['name']))
        reserve(target)
        # Stage in a fresh directory: existing links cannot redirect extracted files.
        stage = tempfile.mkdtemp(prefix='.extract-', dir=parent)
        def output(name):
            parts = name.replace('\\', '/').rstrip('/').split('/')
            if not parts or any(not p or p in ('.', '..') for p in parts):
                raise ValueError('压缩包包含不安全路径：' + name)
            for part in parts: child_name(part)
            return os.path.join(stage, *parts)
        try:
            if zipfile.is_zipfile(sources[0]):
                with zipfile.ZipFile(sources[0]) as archive:
                    members = [(m, output(m.filename)) for m in archive.infolist()]
                    for member, dest in members:
                        mode = member.external_attr >> 16
                        if stat.S_ISLNK(mode): raise ValueError('不支持解压链接')
                        if member.is_dir(): os.makedirs(dest, exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with archive.open(member) as src, open(dest, 'xb') as dst: shutil.copyfileobj(src, dst)
            else:
                with tarfile.open(sources[0], 'r:*') as archive:
                    members = [(m, output(m.name)) for m in archive.getmembers()]
                    for member, dest in members:
                        if member.isdir(): os.makedirs(dest, exist_ok=True)
                        elif member.isfile():
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            with archive.extractfile(member) as src, open(dest, 'xb') as dst: shutil.copyfileobj(src, dst)
                        else: raise ValueError('不支持解压链接或特殊文件')
            reserve(target)
            os.rename(stage, target)
        finally:
            if os.path.exists(stage): shutil.rmtree(stage)
    else:
        raise ValueError('未知文件操作')
