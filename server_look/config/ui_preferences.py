"""Validated desktop preferences, independent of encrypted connection history."""
import json
import os
from pathlib import Path
import tempfile
from server_look.ui.shortcut_capture import valid_shortcut

SHORTCUTS = {'服务器': '<Control-n>', '连接': '<Control-Return>', '刷新': '<F5>', '断开': '<Control-d>', '搜索': '<Control-f>', '设置': '<Control-comma>', '帮助': '<F1>'}
FILE_ACTIONS = {'新建文件夹': 'mkdir', '拷贝文件': 'copy', '粘贴文件': 'paste', '删除文件': 'delete', '重命名文件': 'rename', '压缩文件': 'compress', '解压文件': 'extract'}
SHORTCUTS.update(dict(zip(FILE_ACTIONS, ('<Control-Shift-N>', '<Control-c>', '<Control-v>', '<Delete>', '<F2>', '无', '无'))))
KEY_CHOICES = ('无', '<Control-n>', '<Control-Return>', '<F5>', '<Control-d>', '<Control-f>', '<Control-comma>', '<F1>', '<F3>', '<F4>', '<F6>', '<F7>', '<F8>', '<F9>', '<F10>', '<Control-g>', '<Control-h>', '<Control-j>', '<Control-k>', '<Control-l>', '<Control-r>', '<Control-s>')
KEY_CHOICES = tuple(dict.fromkeys((*KEY_CHOICES, *SHORTCUTS.values())))
DEFAULTS = {'language': 'zh_CN', 'readonly': False, 'font_size': 10, 'button_font': 10, 'button_size': '紧凑', 'navigation': '顶部横排', 'window': '普通窗口', 'shortcuts': SHORTCUTS}

def validate(values):
    result = dict(DEFAULTS, **values)
    for key in ('font_size', 'button_font'):
        if type(result[key]) is not int or not 8 <= result[key] <= 18:
            raise ValueError('字号必须为 8–18')
    for key, choices in {'button_size': ('紧凑', '标准', '宽松'), 'navigation': ('顶部横排', '左侧竖排'), 'window': ('普通窗口', '最大化')}.items():
        if result[key] not in choices:
            raise ValueError('未知布局选项')
    if type(result['readonly']) is not bool:
        raise ValueError('只读设置无效')
    if result['language'] not in ('zh_CN', 'en'):
        raise ValueError('未知语言')
    keys = dict(SHORTCUTS, **result['shortcuts'])
    if set(keys) != set(SHORTCUTS) or any(not valid_shortcut(k) for k in keys.values()):
        raise ValueError('快捷键无效')
    active = [k for k in keys.values() if k != '无']
    if len(active) != len(set(active)):
        raise ValueError('快捷键不能重复，请调整或选择“无”')
    result['shortcuts'] = keys
    return {key: result[key] for key in DEFAULTS}

def preferences_path():
    return Path(os.environ.get('APPDATA', Path.home())) / 'ServerLook' / 'ui-settings.json'

def load_preferences(path=None):
    try:
        return validate(json.loads((Path(path) if path else preferences_path()).read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError, KeyError):
        return validate({})

def save_preferences(values, path=None):
    values = validate(values)
    target = Path(path) if path else preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(values, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
