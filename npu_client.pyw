"""Desktop GUI entry point. Implementation lives in normal importable modules."""
from server_look.app.launcher import run


if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(run())
