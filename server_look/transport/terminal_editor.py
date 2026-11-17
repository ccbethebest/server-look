"""Session-local vi/vim bridge; no shell profiles or remote files are changed."""
import json
import ntpath
import posixpath
import shlex
import re
import time


def editor_setup(token, visual=True):
    # printf is a shell builtin: editing must also work without remote Python.
    # eval prevents existing vi/vim aliases from rewriting definitions.
    functions = []
    for name in ('vi', 'vim'):
        if not visual:
            functions.append(f'{name}() {{ command {name} "$@"; }}')
            continue
        functions.append(f'{name}() {{ '
                         'local local_path file literal=0 found=0; '
                         'for file in "$@"; do '
                         'if [ "$literal" -eq 0 ]; then case "$file" in '
                         '--) literal=1; continue ;; '
                         '-o|-O|-p) continue ;; '
                         '-*|+*) printf "%s\\n" "可视化编辑不支持该选项，请取消勾选后使用原生 vi/vim" >&2; return 2 ;; '
                         'esac; fi; done; '
                         'literal=0; for file in "$@"; do '
                         'if [ "$literal" -eq 0 ]; then case "$file" in '
                         '--) literal=1; continue ;; -o|-O|-p) continue ;; esac; fi; '
                         '[ -n "$file" ] || continue; found=1; '
                         'case "$file" in /*) local_path=$file ;; *) local_path=${PWD%/}/$file ;; esac; '
                         f"printf '\\033]777;server-look;{token};!%s|%s|%s|%s|%s\\007' "
                         '"$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)" '
                         '"$(readlink /proc/$$/ns/mnt 2>/dev/null)" "$(id -u)" "$(id -g)" "$local_path"; done; '
                         '[ "$found" -eq 1 ] || printf "%s\\n" "请指定文本文件名，例如 vim script.py" >&2; }')
    for name in ('python', 'python3'):
        functions.append(f'{name}() {{ if [ "$#" -eq 0 ]; then '
                         f"printf '\\033]777;server-look;{token};?python\\007'; "
                         f'command {name} -u -i -q; '
                         f"printf '\\033]777;server-look;{token};?end\\007'; "
                         f'else command {name} "$@"; fi; }}')
    source = 'unalias vi vim python python3 2>/dev/null || :; eval ' + shlex.quote('; '.join(functions))
    begin, end = echo_markers(token)
    return begin + source + end


def editor_command(command, token, visual=True):
    """Reinstall the bridge for a simple edit command after shell reinitialization."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        words = list(lexer)
    except ValueError:
        return command
    if ((words and words[0] in ('vi', 'vim') and not any(
            word in (';', '&&', '||', '|', '&', '>', '>>', '<', '(', ')') for word in words))
            or (len(words) == 1 and words[0] in ('python', 'python3'))):
        return editor_setup(token, visual) + command
    return command


def echo_markers(token):
    return f': __SL_BEGIN_{token}__; ', f'; : __SL_END_{token}__; '


class SetupEchoFilter:
    """Hide only a session-marked setup echo; malformed echoes fail open."""
    controls = re.compile(r'\x1b\[[0-?]*[ -/]*(?:[@-~]|$)|[\r\n]')

    def __init__(self, token):
        self.begin, self.end = echo_markers(token)
        self.pending = ''
        self.started = None
        self.hiding = False

    @classmethod
    def plain(cls, data):
        # Keep raw offsets so unrelated terminal controls/output pass unchanged.
        chars, offsets = [], []
        start = 0
        for match in cls.controls.finditer(data):
            chars.extend(data[start:match.start()])
            offsets.extend(range(start, match.start()))
            start = match.end()
        chars.extend(data[start:])
        offsets.extend(range(start, len(data)))
        return ''.join(chars), offsets

    def feed(self, text):
        data = self.pending + text
        self.pending = ''
        if self.started is not None and (time.monotonic() - self.started > 5 or len(data) > 32768):
            self.started = None
            self.hiding = False
            return data
        output = []
        while data:
            plain, offsets = self.plain(data)
            if not self.hiding:
                start = plain.find(self.begin)
                if start < 0:
                    keep = next((n for n in range(min(len(plain), len(self.begin)-1), 0, -1)
                                 if plain.endswith(self.begin[:n])), 0)
                    cut = offsets[len(plain)-keep] if keep else len(data)
                    output.append(data[:cut])
                    self.pending = data[cut:]
                    break
                cut = offsets[start]
                output.append(data[:cut])
                data = data[cut:]
                self.hiding = True
                plain, offsets = self.plain(data)
            end = plain.find(self.end, len(self.begin))
            if end < 0:
                self.pending = data
                break
            data = data[offsets[end + len(self.end)-1] + 1:]
            self.hiding = False
            self.started = None
        if len(self.pending) > 32768:
            output.append(self.pending)
            self.pending = ''
            self.hiding = False
        if self.pending and self.started is None:
            self.started = time.monotonic()
        elif not self.pending:
            self.started = None
        return ''.join(output)


class EditorBridge:
    def __init__(self, token):
        self.token = token
        self.echo_filter = SetupEchoFilter(token)
        self.prefix = '\x1b]777;server-look;' + token + ';'
        self.pending = ''

    def feed(self, text):
        events = self.feed_events(text)
        return (''.join(value for kind, value in events if kind == 'text'),
                [value for kind, value in events if kind == 'editor'])

    def feed_events(self, text):
        data = self.pending + self.echo_filter.feed(text)
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
