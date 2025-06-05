import hashlib
import os


def get_sigs(path: str):
    items = []
    with os.scandir(path) as entries:
        for entry in entries:
            if entry.is_file() and entry.name.endswith(".py"):
                stat_info = entry.stat()
                items.append(f"{entry.path}:{stat_info.st_size}:{stat_info.st_mtime}")
            if entry.is_dir() and entry.name not in [".venv", "venv", "__pycache__"]:
                items.extend(get_sigs(entry.path))
    return items


def get_context_hash(path: str):
    sig = "empty"
    if os.path.isfile(path):
        s = os.stat(path)
        sig = f"{path}:{s.st_size}:{s.st_mtime}"
    elif os.path.isdir(path):
        sig = "".join(get_sigs(path=path))
    return f"{hashlib.md5(sig.encode('utf-8')).hexdigest()}"
