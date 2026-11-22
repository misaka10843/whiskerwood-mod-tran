import os
import re
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path


STEAM_APP_ID = "2489330"
LOCALIZATION_MOD_ID = "3643964887"


def bundled():
    try:
        return __compiled__ is not None
    except NameError:
        return False


def legacy_data():
    return Path(os.environ["LOCALAPPDATA"]) / "WhiskerwoodModTranslator"


def data_directory():
    return Path(sys.argv[0]).resolve().parent / "data" if bundled() else legacy_data()


def migrate_data(destination):
    """Copy the existing development version's settings into a new portable folder."""
    if not bundled() or (destination / ".portable").exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    previous = legacy_data()
    database = previous / "drafts.sqlite3"
    backup = destination / database.name
    if database.is_file() and not backup.exists():
        temporary = backup.with_suffix(".migrating")
        try:
            with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(temporary)) as target:
                    source.backup(target)
            temporary.replace(backup)
        finally:
            temporary.unlink(missing_ok=True)
    for file in [previous / "game-directory.txt", previous / "workshop-directory.txt",
                 *previous.glob("ue4ss-*.json"), *(previous / "backups").glob("zh-*.txt")]:
        copied = destination / file.relative_to(previous)
        if file.is_file() and not copied.exists():
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, copied)
    (destination / ".portable").touch()


def steam_libraries():
    import winreg

    candidates = [(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                  (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")]
    roots = [Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Steam"]
    for hive, key, value in candidates:
        try:
            with winreg.OpenKey(hive, key) as handle:
                path, _ = winreg.QueryValueEx(handle, value)
                roots.insert(0, Path(path))
        except OSError:
            continue
    for root in dict.fromkeys(roots):
        yield root
        library_file = root / "steamapps/libraryfolders.vdf"
        try:
            vdf = library_file.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue
        for path in re.findall(r'"path"\s*"((?:\\.|[^"\\])*)"', vdf):
            yield Path(path.replace("\\\\", "\\"))


def default_workshop():
    folders = [root / "steamapps/workshop/content" / STEAM_APP_ID for root in steam_libraries()]
    for folder in folders:
        mod = folder / LOCALIZATION_MOD_ID
        if (mod / "zh.txt").is_file() and (mod / "zhLocalization.pak").is_file():
            return folder
    return next((folder for folder in folders if folder.is_dir()), None)


def steam_game_directories(steamapps):
    manifest = steamapps / f"appmanifest_{STEAM_APP_ID}.acf"
    try:
        content = manifest.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        content = ""
    match = re.search(r'"installdir"\s*"([^"\\/:]+)"', content)
    if match and match[1] not in {".", ".."}:
        yield steamapps / "common" / match[1]
    yield steamapps / "common/Whiskerwood"
