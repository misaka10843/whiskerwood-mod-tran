import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from app_paths import steam_game_directories, steam_libraries
from option_catalog import DEFAULTS


APP_ID = "WhiskerwoodSettingsZh"
PROXY = "dwmapi.dll"
CORE = "ue4ss/UE4SS.dll"
PLUGIN = f"ue4ss/Mods/{APP_ID}"
SCRIPT = f"{PLUGIN}/Scripts/main.lua"
FLAG = f"{PLUGIN}/enabled.txt"
STRINGS = f"{PLUGIN}/translations.json"
SHIPPING = "Whiskerwood-Win64-Shipping.exe"
VERSION = "v4.0.0"
RELEASE = f"https://github.com/UE4SS-RE/RE-UE4SS/releases/download/{VERSION}/"
ARCHIVES = {
    f"UE4SS_{VERSION}.zip": "251ad0d1381a241750e036f5918cbf2b5d7ec58ebc608cb2dd09d459d0c81e45",
    "zCustomGameConfigs.zip": "1fd90a875138534cc11a7aee802bfb4b4f08e8614ff1709796fb363e2dab9c2d",
}
SIGNATURE_PATH = "ue4ss/UE4SS_Signatures/StaticConstructObject.lua"
SIGNATURE = ("48 89 5C 24 10 48 89 6C 24 18 56 57 41 54 41 56 41 57 48 81 EC "
             "? ? ? ? 48 8B 05 ? ? ? ? 48 33 C4 48 89 84 24 ? ? ? ? 48 8B 29 33 DB 4C 8B 79 08")

def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        file.write(data)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def binaries(game):
    return next((p for p in (game / "Whiskerwood/Binaries/Win64", game / "Binaries/Win64", game)
                 if (p / SHIPPING).is_file()), None)


def detect_game(workshop):
    libraries = [root / "steamapps" for root in steam_libraries()]
    if workshop and workshop.parent.name.casefold() == "content" and workshop.parent.parent.name.casefold() == "workshop":
        libraries.insert(0, workshop.parent.parent.parent)
    for steamapps in dict.fromkeys(libraries):
        for candidate in steam_game_directories(steamapps):
            if binaries(candidate):
                return candidate
    return None


class RuntimeSettings:
    def __init__(self, game, data):
        if game is None:
            raise ValueError("未找到 Whiskerwood，请选择游戏目录。")
        self.bin = binaries(game)
        if self.bin is None:
            raise ValueError("目录中找不到 Whiskerwood-Win64-Shipping.exe")
        self.bin = self.bin.resolve()
        self.cache = data / "tools"
        identity = digest(os.path.normcase(str(self.bin)).encode("utf-8"))
        self.manifest = data / f"ue4ss-{identity[:16]}.json"

    def managed(self):
        return json.loads(self.manifest.read_text(encoding="utf-8")) if self.manifest.exists() else {}

    def path(self, name):
        relative = PurePosixPath(name)
        path = self.bin.joinpath(*relative.parts)
        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(self.bin):
            raise ValueError(f"安装路径无效：{name}")
        return path

    def status(self):
        if self.path(PROXY).is_file() and self.path(CORE).is_file():
            if self.path(FLAG).is_file() and self.path(SCRIPT).is_file():
                return "UE4SS 已安装 · 设置汉化已启用"
            return "UE4SS 已安装 · 设置汉化已停用"
        return "UE4SS 未安装"

    @staticmethod
    def ensure_game_closed():
        result = subprocess.run(["tasklist.exe", "/FI", f"IMAGENAME eq {SHIPPING}", "/NH"],
                                capture_output=True, check=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if SHIPPING.casefold().encode("ascii") in result.stdout.lower():
            raise ValueError("请先关闭 Whiskerwood，再修改 UE4SS。")

    def archive(self, name):
        local = self.cache / name
        data = local.read_bytes() if local.is_file() else b""
        if digest(data) != ARCHIVES[name]:
            with urllib.request.urlopen(RELEASE + name, timeout=30) as response:
                data = response.read(64 * 1024 * 1024 + 1)
            if digest(data) != ARCHIVES[name]:
                raise ValueError(f"UE4SS 下载校验失败：{name}")
            atomic_write(local, data)
        return ZipFile(io.BytesIO(data))

    def set_files(self, payload):
        recorded = self.managed()
        for name, data in payload.items():
            path = self.path(name)
            if path.exists() and (name not in recorded or digest(path.read_bytes()) != recorded[name]):
                raise ValueError(f"已有文件或文件已被修改，未覆盖：{path}")
        for name, data in payload.items():
            path = self.path(name)
            if path.is_file() and path.read_bytes() == data:
                continue
            previous = recorded.get(name)
            recorded[name] = digest(data)
            self.save_manifest(recorded)
            try:
                atomic_write(path, data)
            except OSError:
                if previous is None:
                    recorded.pop(name)
                else:
                    recorded[name] = previous
                self.save_manifest(recorded)
                raise

    def save_manifest(self, files):
        if files:
            atomic_write(self.manifest, json.dumps(files, indent=2).encode("utf-8"))
        else:
            self.manifest.unlink(missing_ok=True)

    def install(self):
        self.ensure_game_closed()
        payload = {}
        owns_signature = SIGNATURE_PATH in self.managed()
        if not (self.path(PROXY).is_file() and self.path(CORE).is_file()):
            with self.archive(f"UE4SS_{VERSION}.zip") as release:
                for name in (PROXY, CORE, "ue4ss/LICENSE", "ue4ss/UE4SS-settings.ini"):
                    payload[name] = release.read(name)
            with self.archive("zCustomGameConfigs.zip") as configs:
                path = "UE4SS_Signatures/FText_Constructor.lua"
                payload[f"ue4ss/{path}"] = configs.read(f"Whiskerwood/{path}")
            payload["ue4ss/Mods/mods.txt"] = b"; Local mods may use enabled.txt.\r\n"
            owns_signature = True
        if owns_signature:
            pattern = b"".join(b"." if token == "?" else re.escape(bytes.fromhex(token))
                               for token in SIGNATURE.split())
            matches = re.finditer(pattern, self.path(SHIPPING).read_bytes(), re.DOTALL)
            if next(matches, None) is None or next(matches, None) is not None:
                raise ValueError("当前 Whiskerwood 版本与已验证的 UE4SS 静态签名不匹配。")
            payload[SIGNATURE_PATH] = (
                f'function Register() return "{SIGNATURE}" end\n'
                'function OnMatchFound(address) return address end\n'
            ).encode("ascii")
        payload.update(self.plugin_payload())
        self.ensure_game_closed()
        self.set_files(payload)

    def translations(self):
        path = self.path(STRINGS)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def plugin_payload(self, overrides=None):
        existing = self.translations()
        custom = overrides or {}
        translations = {option: fields | existing.get(option, {}) | custom.get(option, {})
                        for option, fields in DEFAULTS.items()}
        lines = ["local translations = {"]
        for option, fields in translations.items():
            values = ", ".join(f"{key} = {json.dumps(value, ensure_ascii=False)}"
                               for key, value in fields.items() if key in {"name", "description"})
            lines.append(f'    ["{option}"] = {{{values}}},')
        lines.extend(("}", ""))
        template = Path(__file__).with_name("ue4ss_settings.lua").read_text(encoding="utf-8")
        return {STRINGS: json.dumps(translations, ensure_ascii=False, indent=2).encode("utf-8"),
                SCRIPT: ("\n".join(lines) + template).encode("utf-8"), FLAG: b""}

    def apply_translations(self, overrides):
        self.ensure_game_closed()
        if not all(self.path(name).is_file() for name in (PROXY, CORE, FLAG, SCRIPT)):
            raise ValueError("请先在项目设置中启用 UE4SS 设置汉化。")
        self.set_files(self.plugin_payload(overrides))

    def enable(self, enabled):
        self.ensure_game_closed()
        if enabled:
            if not (self.path(PROXY).is_file() and self.path(CORE).is_file()):
                raise ValueError("请先安装 UE4SS。")
            self.set_files(self.plugin_payload())
        else:
            self.remove_files({FLAG})

    def remove_files(self, names):
        recorded = self.managed()
        kept = []
        for name in sorted(names.intersection(recorded)):
            path = self.path(name)
            if path.is_file():
                if digest(path.read_bytes()) != recorded[name]:
                    kept.append(str(path))
                    continue
                path.unlink()
            recorded.pop(name)
            self.save_manifest(recorded)
            for directory in path.parents:
                if directory == self.bin:
                    break
                try:
                    directory.rmdir()
                except OSError:
                    break
        return kept

    def uninstall(self):
        self.ensure_game_closed()
        owned = set(self.managed())
        if not owned:
            raise ValueError("此目录没有由本工具安装的 UE4SS 文件。")
        return self.remove_files(owned)
