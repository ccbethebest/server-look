"""Stable resource locations in source checkouts and PyInstaller bundles."""
from pathlib import Path
import os
import sys


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def user_data_dir():
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'ServerLook'
    return Path(os.environ.get('APPDATA', Path.home())) / 'ServerLook'
