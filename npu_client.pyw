"""Windows GUI entry point. Implementation lives in normal importable modules."""
from server_look.app.desktop_app import main


if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    main()
