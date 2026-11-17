"""Session-local vi/vim bridge; no shell profiles or remote files are changed."""
import json
import ntpath
import posixpath
import shlex


def editor_setup(token, python='python3'):
    code = ("import json,os,sys; "
            "print('\\x1b]777;server-look;' + sys.argv[1] + ';' + "
            "json.dumps(os.path.abspath(sys.argv[2]), ensure_ascii=True) + '\\x07', end='', flush=True)")
    invoke = f'{shlex.quote(python)} -c {shlex.quote(code)} {shlex.quote(token)} "$1"'
    functions = []
    for name in ('vi', 'vim'):
        functions.append(f'{name}() {{ if [ "$#" -eq 1 ] && [ -n "$1" ]; then '
                         f'case "$1" in -*) command {name} "$@" ;; *) {invoke} ;; esac; '
                         f'else command {name} "$@"; fi; }}')
    # Shells expand aliases while parsing: remove them on a separate input line.
    return 'unalias vi vim 2>/dev/null || :\n' + '; '.join(functions)


class EditorBridge:
    def __init__(self, token):
        self.token = token
        self.prefix = '\x1b]777;server-look;' + token + ';'
        self.pending = ''

    def feed(self, text):
        data = self.pending + text
        self.pending = ''
        visible, paths = [], []
        while data:
            start = data.find(self.prefix)
            if start < 0:
                keep = next((n for n in range(min(len(data), len(self.prefix)), 0, -1)
                             if data.endswith(self.prefix[:n])), 0)
                visible.append(data[:-keep] if keep else data)
                self.pending = data[-keep:] if keep else ''
                break
            visible.append(data[:start])
            data = data[start:]
            end = data.find('\x07', len(self.prefix))
            if end < 0:
                if len(data) < 8192:
                    self.pending = data
                else:
                    visible.append(data)
                break
            try:
                path = json.loads(data[len(self.prefix):end])
                if (isinstance(path, str) and '\x00' not in path and
                        (posixpath.isabs(path) or ntpath.isabs(path))):
                    paths.append(path)
            except (ValueError, TypeError):
                pass
            data = data[end + 1:]
        return ''.join(visible), paths
