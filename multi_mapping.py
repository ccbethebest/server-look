"""Recursive mapping between local paths and any connected SSH endpoints."""
from contextlib import ExitStack
from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import tempfile
import time
import uuid

from directory_mapping import DirectoryMapping
from file_transfer import local_name
from mapping_direct import direct_copy


def migrate_record(record):
    if 'locations' in record:
        return record
    upload = record['direction'] == '本地 → 服务器'
    return dict(name=record['name'], locations=[dict(server='local',path=record['local']),
        dict(server=record['server'],path=record['remote'])], source=0 if upload else 1,
        targets=[1 if upload else 0], overwrite=record.get('overwrite',False),
        relay='', direct=True, minimum_mbps=1.0)


class Location:
    def __init__(self, record, sftp=None, connection=None):
        self.server, self.sftp, self.connection = record['server'], sftp, connection
        self.root = Path(record['path']) if self.server == 'local' else PurePosixPath(record['path'])
        if not self.root.is_absolute() or '..' in self.root.parts:
            raise ValueError('映射目录必须为不含 .. 的绝对路径')

    def info(self, path):
        try:
            return self.sftp.lstat(str(path)) if self.sftp else path.lstat()
        except FileNotFoundError:
            return None

    def directory(self, path, create=False):
        for parent in reversed((path, *path.parents)):
            info = self.info(parent)
            if info is None and create:
                self.sftp.mkdir(str(parent)) if self.sftp else parent.mkdir()
            elif info is None or not stat.S_ISDIR(info.st_mode) or self.link(parent):
                raise ValueError(f'目录不存在、不是目录或包含链接：{parent}')

    def link(self, path):
        return not self.sftp and (path.is_symlink() or path.is_junction())

    def children(self, path):
        if not self.sftp:
            return list(path.iterdir())
        names = [item.filename for item in self.sftp.listdir_attr(str(path))]
        if any(name in ('', '.', '..') or '/' in name or '\\' in name for name in names):
            raise ValueError('来源包含不安全文件名')
        return [path / name for name in names]

    def open(self, path, mode):
        return self.sftp.open(str(path), 'wx' if mode == 'xb' else mode) if self.sftp else path.open(mode)

    def remove(self, path):
        self.sftp.remove(str(path)) if self.sftp else path.unlink(missing_ok=True)

    def replace(self, source, target):
        self.sftp.posix_rename(str(source),str(target)) if self.sftp else os.replace(source,target)


class MultiMapping(DirectoryMapping):
    chunk_size = 8 * 1024 * 1024

    progress = None
    confirm_relay = None

    def report_progress(self, count):
        now = time.monotonic()
        elapsed = now - self.progress_time
        if elapsed >= 0.25:
            if self.progress:
                self.progress((count-self.progress_bytes)/elapsed/1024/1024)
            self.progress_time, self.progress_bytes = now, count

    def cancel(self):
        self.stopped.set()

    def run_many(self, connections, record, selected=()):
        self.copied = self.skipped = self.direct_count = self.relay_count = 0
        self.fallback_reason = ''
        self.progress_time, self.progress_bytes = time.monotonic(), 0
        self.record = record
        self.overwrite = record.get('overwrite') is True
        self.direct_unavailable = set()
        with ExitStack() as stack:
            locations = []
            channels = {}
            active = {record['source'], *record['targets']}
            for index, item in enumerate(record['locations']):
                server = item['server']
                connection = None
                if server != 'local' and index in active:
                    connection = connections.get(server)
                    if not connection:
                        raise ValueError('请先连接服务器：' + server.split('|')[-1])
                    if server not in channels:
                        channels[server] = stack.enter_context(self.channel(connection))
                        if hasattr(channels[server], 'get_channel'):
                            transport = channels[server].get_channel()
                            if hasattr(transport, 'settimeout'):
                                transport.settimeout(30)
                locations.append(Location(item,channels.get(server),connection))
            source = locations[record['source']]
            targets = [locations[index] for index in record['targets']]
            if not targets:
                raise ValueError('请至少选择一个目标目录')
            source.directory(source.root)
            for target in targets:
                target.directory(target.root)
                if source.server == target.server and (target.root == source.root or source.root in target.root.parents or target.root in source.root.parents):
                    raise ValueError('来源和目标不能相同或互为子目录')
            paths = [type(source.root)(p) for p in selected] if selected else source.children(source.root)
            if any(not target.sftp for target in targets) and len({str(p.relative_to(source.root)).casefold() for p in paths}) != len(paths):
                raise ValueError('来源包含 Windows 下同名的文件')
            for path in paths:
                relative = path.relative_to(source.root)
                if not relative.parts or '..' in relative.parts:
                    raise ValueError('选中项必须位于源目录内')
                source.directory(path.parent)
                for target in targets:
                    destination = target.root.joinpath(*relative.parts)
                    target.directory(destination.parent,create=True)
                    self.copy_between(source,target,path,destination)
        note = f'；直传 {self.direct_count}，本机中转 {self.relay_count}'
        if self.fallback_reason:
            note += '；直传回退原因：' + self.fallback_reason[-200:]
        return f'映射完成：复制 {self.copied} 个文件，跳过 {self.skipped} 项' + note

    def copy_between(self, source, target, path, destination):
        self.check()
        if not target.sftp:
            local_name(destination.name)
        info, existing = source.info(path), target.info(destination)
        if info is None:
            raise FileNotFoundError(str(path))
        if source.link(path) or stat.S_ISLNK(info.st_mode):
            self.skipped += 1
        elif stat.S_ISDIR(info.st_mode):
            if existing and not stat.S_ISDIR(existing.st_mode):
                self.skipped += 1
                return
            target.directory(destination,create=True)
            children = source.children(path)
            if not target.sftp and len({p.name.casefold() for p in children}) != len(children):
                raise ValueError('来源包含 Windows 下同名的文件：' + str(path))
            for child in children:
                if child.name in ('.','..') or '/' in child.name or '\\' in child.name:
                    raise ValueError('来源包含不安全文件名')
                self.copy_between(source,target,child,destination/child.name)
        elif stat.S_ISREG(info.st_mode):
            if existing and (not self.overwrite or not stat.S_ISREG(existing.st_mode) or target.link(destination)):
                self.skipped += 1
                return
            staging = destination.with_name('.mapping-' + uuid.uuid4().hex)
            with target.open(staging,'xb'):
                pass
            try:
                remote_pair = source.sftp is not None and target.sftp is not None
                pair = (source.server,target.server)
                direct = remote_pair and self.record.get('direct',True) and pair not in self.direct_unavailable
                if direct:
                    self.progress_time, self.progress_bytes = time.monotonic(), 0
                    try:
                        direct_copy(source.connection,target.connection,str(path),str(staging),
                                    info.st_size,self.stopped,float(self.record.get('minimum_mbps',1)),
                                    progress=self.report_progress)
                        self.direct_count += 1
                    except Exception as exc:
                        self.check()
                        if self.confirm_relay and not self.confirm_relay(str(exc)):
                            raise RuntimeError('用户取消本机中转') from exc
                        self.direct_unavailable.add(pair)
                        self.fallback_reason = str(exc)
                        direct = False
                        # A failed direct writer may still be exiting: never reuse its file.
                        target.remove(staging)
                        staging = destination.with_name('.mapping-' + uuid.uuid4().hex)
                        with target.open(staging, 'xb'):
                            pass
                if not direct:
                    self.relay_copy(source,target,path,staging,remote_pair)
                    if remote_pair:
                        self.relay_count += 1
                self.check()
                if self.overwrite:
                    target.replace(staging,destination)
                else:
                    # SFTP rename refuses an existing target; local hard-link is exclusive.
                    if target.sftp:
                        target.sftp.rename(str(staging),str(destination))
                    else:
                        os.link(staging,destination)
                        staging.unlink()
                self.copied += 1
            finally:
                if target.info(staging) is not None:
                    target.remove(staging)
        else:
            self.skipped += 1

    def relay_copy(self, source, target, path, staging, remote_pair):
        self.progress_time, self.progress_bytes = time.monotonic(), 0
        with ExitStack() as stack:
            reader = stack.enter_context(source.open(path,'rb'))
            writer = stack.enter_context(target.open(staging,'wb'))
            spool = None
            if remote_pair:
                relay = Path(self.record.get('relay',''))
                if not self.record.get('relay') or not relay.is_absolute() or not relay.is_dir():
                    raise ValueError('请选择可用的本机中转目录')
                spool = stack.enter_context(tempfile.TemporaryFile(dir=relay,prefix='serverlook-relay-'))
            expected = source.info(path).st_size
            transferred = 0
            while True:
                self.check()
                chunk = reader.read(self.chunk_size)
                if not chunk:
                    break
                if spool:
                    if shutil.disk_usage(relay).free < len(chunk) + 16*1024*1024:
                        raise OSError('本机中转目录剩余空间不足，请选择其他磁盘')
                    spool.seek(0)
                    spool.truncate()
                    spool.write(chunk)
                    spool.flush()
                    spool.seek(0)
                    chunk = spool.read(self.chunk_size)
                writer.write(chunk)
                transferred += len(chunk)
                self.report_progress(transferred)
                if spool:
                    spool.seek(0)
                    spool.truncate()

            if transferred != expected:
                raise OSError('源文件在传输期间发生变化，请重试')
