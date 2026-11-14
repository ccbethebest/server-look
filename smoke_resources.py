"""Read-only hardware, mounts and persistent SSH navigation verification."""
import time

from client_core import Connection
from settings import DEFAULT_SERVERS


def main():
    for host in DEFAULT_SERVERS:
        connection = Connection(host, 'root', 22)
        try:
            data = connection.request()
            assert data['hardware']['CPU 架构']
            assert int(data['hardware']['NPU 数量']) > 0
            assert data['disks'], data['resource_errors']
            print(host, 'hardware and disks OK;', len(data['disks']), 'mounts')
            connection.request('list_directory', path='/')
            process = connection.directory.process
            for path in ['/mnt', '/', '/mnt']:
                start = time.perf_counter()
                result = connection.request('list_directory', path=path)
                assert result['path'] == path
                assert connection.directory.process is process
                print(f'  {path}: {(time.perf_counter()-start)*1000:.0f} ms, SSH pid={process.pid}')
        finally:
            connection.close()


if __name__ == '__main__':
    main()
