"""Offline UI translations. Logical settings and user data stay unchanged."""
import re
import weakref
from tkinter import TclError
from translations_en import ENGLISH

LANGUAGES = {'zh_CN': '简体中文', 'en': 'English'}
_language = 'zh_CN'
_listeners = weakref.WeakSet()
# Templates match complete generated messages; captured paths/names stay verbatim.
_templates = []
for source, target in ENGLISH.items():
    if re.search(r'\{\d+\}', source):
        parts = re.split(r'(\{\d+\})', source)
        pattern = ''.join('(.*?)' if re.fullmatch(r'\{\d+\}', part) else re.escape(part) for part in parts)
        _templates.append((re.compile(pattern, re.S), target))


def language():
    return _language


def subscribe(view):
    _listeners.add(view)


def set_language(value):
    global _language
    if value not in LANGUAGES:
        raise ValueError('Unsupported language')
    _language = value
    for view in list(_listeners):
        if hasattr(view, 'winfo_exists'):
            try:
                exists = view.winfo_exists()
            except TclError:
                exists = False
            if not exists:
                _listeners.discard(view)
                continue
        view.refresh_language()


def tr(text):
    if _language == 'zh_CN' or not isinstance(text, str):
        return text
    if text.endswith((' ↑', ' ↓')):
        return tr(text[:-2]) + text[-2:]
    if text in ENGLISH:
        return ENGLISH[text]
    for pattern, target in _templates:
        match = pattern.fullmatch(text)
        if match:
            return target.format(*match.groups())
    # Composite messages are built from translated UI fragments. Replace only
    # authored fragments, never individual words in a user's file or path.
    for source in _fragments:
        if source in text:
            text = text.replace(source, ENGLISH[source])
    return text


_fragments = sorted((s for s in ENGLISH if '{' not in s and (
    s.endswith(('：', '：\n', ' · ', '…', '；', '：已结束', '：未开始'))
    or s.startswith((' · ', '；', '（')))), key=len, reverse=True)
