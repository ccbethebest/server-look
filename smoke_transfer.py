"""Round-trip only uniquely named /tmp fixtures; remove exactly those fixtures."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import uuid

from client_core import Connection
from file_transfer import Transfer
from settings import DEFAULT_SERVERS


for host in DEFAULT_SERVERS:
    connection = Connection(host, 'root', 22)
    name = 'server-kankan-test-' + uuid.uuid4().hex
    remote = '/tmp/' + name
    try:
        connection.directory.request('/tmp', action='mkdir', name=name)
        process = connection.directory.process
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'example [folder]'
            source.mkdir()
            (source / '中文 file.txt').write_text('roundtrip 中文', encoding='utf-8')
            target = Path(folder) / 'download'
            target.mkdir()
            Transfer().run(connection.args, 'upload', source.as_posix(), remote)
            Transfer().run(connection.args, 'download', remote + '/example [folder]', target.as_posix())
            assert (target / source.name / '中文 file.txt').read_text(encoding='utf-8') == 'roundtrip 中文'
        connection.directory.request(remote)
        assert process is connection.directory.process
        print(host, 'mkdir, recursive upload/download, UTF-8 and SSH reuse OK')
    finally:
        code = ('import os; p=' + repr(remote) + '; '
                'f=p+"/example [folder]/中文 file.txt"; '
                'os.unlink(f) if os.path.exists(f) else None; '
                'os.rmdir(p+"/example [folder]") if os.path.isdir(p+"/example [folder]") else None; '
                'os.rmdir(p) if os.path.isdir(p) else None')
        subprocess.run(connection.args + ['python3 -c ' + shlex.quote(code)], check=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        connection.close()
