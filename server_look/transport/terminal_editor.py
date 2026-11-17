"""Session-local vi/vim bridge; no shell profiles or remote files are changed."""
import json
import ntpath
import posixpath
import shlex


def editor_setup(token):
    # printf is a shell builtin: editing must also work without remote Python.
    # eval prevents existing vi/vim aliases from rewriting definitions.
    functions = []
    for name in ('vi', 'vim'):
        functions.append(f'{name}() {{ if [ "$#" -eq 1 ] && [ -n "$1" ]; then '
                         f'case "$1" in -*) command {name} "$@" ;; *) '
                         'case "$1" in /*) local_path=$1 ;; *) local_path=${PWD%/}/$1 ;; esac; '
                         f"printf '\\033]777;server-look;{token};!%s|%s|%s|%s|%s\\007' "
                         '"$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)" '
                         '"$(readlink /proc/$$/ns/mnt 2>/dev/null)" "$(id -u)" "$(id -g)" "$local_path" ;; esac; '
                         f'else command {name} "$@"; fi; }}')
    for name in ('python', 'python3'):
        functions.append(f'{name}() {{ if [ "$#" -eq 0 ]; then '
                         f"printf '\\033]777;server-look;{token};?python\\007'; "
                         f'command {name} -u -i -q; '
                         f"printf '\\033]777;server-look;{token};?end\\007'; "
                         f'else command {name} "$@"; fi; }}')
    return 'unalias vi vim python python3 2>/dev/null || :; eval ' + shlex.quote('; '.join(functions))


def editor_command(command, token):
    """Reinstall the bridge for a simple edit command after shell reinitialization."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return command
    if ((len(words) == 2 and words[0] in ('vi', 'vim') and not words[1].startswith('-'))
            or (len(words) == 1 and words[0] in ('python', 'python3'))):
        return editor_setup(token) + '; ' + command
    return command


class EditorBridge:
    def __init__(self, token):
        self.token = token
        self.prefix = '\x1b]777;server-look;' + token + ';'
        self.pending = ''

    def feed(self, text):
        events = self.feed_events(text)
        return (''.join(value for kind, value in events if kind == 'text'),
                [value for kind, value in events if kind == 'editor'])

    def feed_events(self, text):
        data = self.pending + text
        self.pending = ''
        events = []
        while data:
            start = data.find(self.prefix)
            if start < 0:
                keep = next((n for n in range(min(len(data), len(self.prefix)), 0, -1)
                             if data.endswith(self.prefix[:n])), 0)
                events.append(('text', data[:-keep] if keep else data))
                self.pending = data[-keep:] if keep else ''
                break
            events.append(('text', data[:start]))
            data = data[start:]
            end = data.find('\x07', len(self.prefix))
            if end < 0:
                if len(data) < 8192:
                    self.pending = data
                else:
                    events.append(('text', data))
                break
            try:
                payload = data[len(self.prefix):end]
                if payload in ('?python', '?end'):
                    events.append(('python', payload == '?python'))
                    data = data[end + 1:]
                    continue
                context = None
                if payload.startswith('!'):
                    boot, namespace, uid, gid, path = payload[1:].split('|', 4)
                    context = dict(boot=boot, namespace=namespace, uid=uid, gid=gid)
                    payload = '@' + path
                path = posixpath.normpath(payload[1:]) if payload.startswith('@/') else json.loads(payload)
                if (isinstance(path, str) and '\x00' not in path and
                        (posixpath.isabs(path) or ntpath.isabs(path))):
                    events.append(('editor', dict(path=path, context=context) if context is not None else path))
            except (ValueError, TypeError):
                pass
            data = data[end + 1:]
        return events
