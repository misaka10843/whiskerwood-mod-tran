"""Read keyed Whiskerwood strings from cooked Blueprint exports."""

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path

from app_paths import data_directory
from option_catalog import OPTIONS, RUNTIME_KEY, option_labels

ENTRYPOINTS = {"BP_Startup.uexp", "BP_MainMenuLoad.uexp", "BP_MapLoad.uexp"}
ENTRYPOINTS = {name.casefold() for name in ENTRYPOINTS}
LOOSE_SOURCES = {"en.txt", "en.csv", "strings.txt", "strings.csv"}
LOCALIZATION_KEY = re.compile(r"[\w-]+(?:\.[\w-]+)+")
STRING_CONST = re.compile(rb"\x1f([^\x00]{1,16000})\x00")
# This cooked Blueprint form builds a one-entry map using consecutive
# key and value conversion calls, then submits it to AddNewStrings.
INLINE_PAIR = re.compile(
    rb"\x68(.{4})\x21(.{4})\x00{4}\x16\x0f"
    rb".{33}\x68(.{4})\x1f([^\x00]{1,16000})\x00\x16",
    re.DOTALL,
)
HOME_OPTION = re.compile(
    rb"\x68\xed\xff\xff\xff(?:\x1f([^\x00]+)\x00|"
    rb"\x34((?:(?!\x00\x00)..)+)\x00\x00)"
    rb"\x16\x0f.{33}\x68\xf0\xff\xff\xff\x1f"
    rb"(setting\.HomeNearWork\.Enabled\.(?:name|description))\x00", re.DOTALL,
)


def repak_path():
    tools = data_directory() / "tools"
    for filename in ("repak-0.2.3.exe", "repak.exe"):
        if (tools / filename).is_file():
            return str(tools / filename)
    return shutil.which("repak")


def _run(repak, action, pak, *args):
    result = subprocess.run(
        [repak, action, str(pak), *args], capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip() or f"repak {action} 失败")
    return result.stdout


def _int(data, offset):
    return struct.unpack_from("<i", data, offset)[0]


def _fstring(data, offset):
    length = _int(data, offset)
    width = 2 if length < 0 else 1
    size = abs(length) * width
    end = offset + 4 + size
    if not size or size > 32000 or end > len(data) or data[end-width:end] != bytes(width):
        raise ValueError("无效 FString")
    encoding = "utf-16-le" if width == 2 else "utf-8"
    return data[offset+4:end-width].decode(encoding), end


def _names(asset):
    start = asset.find(b"/Game/Mods/", 40, 320)
    if start < 0:
        raise ValueError("无法识别已烹制资源的包头")
    package, end = _fstring(asset, start - 4)
    if not package.startswith("/Game/Mods/"):
        raise ValueError("无效的包名")
    if end + 12 > len(asset):
        raise ValueError("包头不完整")
    count, cursor = struct.unpack_from("<ii", asset, end + 4)
    if not 0 < count < 50000 or not end < cursor < len(asset):
        raise ValueError("无效的名称表")
    names = []
    for _ in range(count):
        if cursor + 4 > len(asset):
            raise ValueError("名称表不完整")
        name, cursor = _fstring(asset, cursor)
        names.append(name)
        cursor += 4  # serialized name hashes
    return names


def _clean(data):
    value = data.decode("utf-8", "strict")
    if not value.strip() or any(ord(c) < 32 and c not in "\r\n\t" for c in value):
        raise ValueError("非显示文本")
    return value


def _inline_pairs(names, data):
    if "AddNewStrings" not in names:
        return
    for match in INLINE_PAIR.finditer(data):
        left, index, right, raw = match.groups()
        index = _int(index, 0)
        if _int(left, 0) != _int(right, 0) + 1 or not 0 <= index < len(names):
            continue
        key = names[index]
        if LOCALIZATION_KEY.fullmatch(key):
            try:
                yield key, _clean(raw)
            except ValueError:
                continue


def _serialized_maps(names, data, prefix):
    for index, key in enumerate(names):
        if not key.startswith(prefix) or not LOCALIZATION_KEY.fullmatch(key):
            continue
        pattern = struct.pack("<ii", index, 0)
        for match in re.finditer(re.escape(pattern), data):
            try:
                value, end = _fstring(data, match.end())
                if value and value.isprintable():
                    yield match.start(), end, key, value
            except (ValueError, struct.error):
                continue


def _map_runs(names, data, prefix):
    runs = []
    for start, end, key, value in sorted(_serialized_maps(names, data, prefix)):
        if not runs or start != runs[-1][-1][1]:
            runs.append([])
        runs[-1].append((start, end, key, value))
    return [[(key, value) for _, _, key, value in run] for run in runs
            if len(run) >= 2 and run[0][0] >= 4 and _int(data, run[0][0] - 4) == len(run)]


def _special_pairs(mod, names, data):
    if mod == "MoreDecoratives" and "Loc Strings" in names:
        strings = list(STRING_CONST.finditer(data))
        for key, value in zip(strings, strings[1:]):
            if key[1].startswith(b"moredecoratives.slotdecorative.") and 100 < value.start() - key.end() < 220:
                yield key[1].decode("ascii"), _clean(value[1]), ""
    elif mod == "Airships" and "SkyLocStrings" in names:
        for run in _map_runs(names, data, ("building.", "error.", "toolbar.", "tooltip.", "vehicle.")):
            for key, value in run:
                yield key, value, ""
    elif mod == "WMR_Housing" and {"en", "fr", "zh"}.issubset(names):
        maps = _map_runs(names, data, "wmrh.")
        # This Blueprint registers its translations in order, with zh
        # immediately before zh-tw and Turkish.
        if len(maps) == 17 and "可容纳" in maps[14][1][1]:
            english, chinese = maps[0], dict(maps[14])
            for key, value in english:
                yield key, value, chinese.get(key, "")
    elif mod == "LongerDays" and "Get Localized Option" in names:
        for period in ("Day", "Night"):
            marker = f"Longer Days: {period} Length (Minutes)".encode()
            offset = data.find(marker)
            if offset >= 4:
                try:
                    title, end = _fstring(data, offset - 4)
                    description, _ = _fstring(data, end)
                except (ValueError, struct.error):
                    continue
                yield f"setting.LongerDays-{period}Length.name", title, ""
                yield f"setting.LongerDays-{period}Length.description", description, ""
    elif mod == "HomeNearWork" and {"GetWordFromKey", "en", "zh"}.issubset(names):
        english, chinese = {}, {}
        for ascii_value, wide_value, key in HOME_OPTION.findall(data):
            dst = english if ascii_value else chinese
            value = ascii_value.decode("utf-8") if ascii_value else wide_value.decode("utf-16-le")
            dst.setdefault(key.decode("ascii"), value)
        for key, value in english.items():
            yield key, value, chinese.get(key, "")


def _runtime_entries(mod, data):
    labels = option_labels(mod)
    matches = []
    for option, (title, _, description) in labels.items():
        # RegisterModOptions takes the ID immediately before the display name;
        # these cooked calls allow either raw FString fields or Kismet literals.
        marker = re.escape(option.encode() + b"\x00") + rb".{0,8}?" + re.escape(title.encode() + b"\x00")
        match = re.search(marker, data, re.DOTALL)
        if match:
            matches.append((match.start(), match.end(), option, title, description))
    matches.sort()
    for index, (_, end, option, title, description) in enumerate(matches):
        yield f"{RUNTIME_KEY}{option}.name", title, ""
        if not description:
            continue
        boundary = matches[index + 1][0] if index + 1 < len(matches) else len(data)
        for match in re.finditer(rb"[ -~\n\r]{12,3000}(?=\x00)", data[end:min(boundary, end + 3500)]):
            source = match[0].decode("ascii").strip()
            if (source not in {"No schooling", "Fresh Copper", "Thought and Approval"}
                    and " " in source and not source.startswith(("/", "NoSupportBeams_", "BigStorage_"))):
                yield f"{RUNTIME_KEY}{option}.description", source, ""
                break


def read_pak(repak, pak, read_rows, decode, hardcoded_options=None):
    names = _run(repak, "list", pak).decode("utf-8").splitlines()
    entries = {}
    assets = set(names)
    for name in names:
        filename = name.rsplit("/", 1)[-1]
        if filename in LOOSE_SOURCES:
            raw = _run(repak, "get", pak, name)
            entries.update({key.casefold(): (key, value, "") for key, value in
                            read_rows(decode(raw), f"{pak.name}/{name}").values()})
        entrypoint = filename.casefold() in ENTRYPOINTS
        option_library = pak.stem in OPTIONS and filename.casefold() == f"bf_{pak.stem}.uexp".casefold()
        if not (entrypoint or option_library):
            continue
        header = name.removesuffix(".uexp") + ".uasset"
        if header not in assets:
            continue
        name_map = _names(_run(repak, "get", pak, header))
        if (hardcoded_options is not None and "RegisterModOptions" in name_map
                and "GetWordFromKey" not in name_map):
            hardcoded_options.add(pak.stem)
        has_localization = "AddNewStrings" in name_map
        has_runtime = pak.stem in OPTIONS and ("RegisterModOptions" in name_map or option_library)
        if not (has_localization or has_runtime):
            continue
        data = _run(repak, "get", pak, name)
        if has_localization:
            for key, value in _inline_pairs(name_map, data):
                entries[key.casefold()] = (key, value, "")
            for key, value, chinese in _special_pairs(pak.stem, name_map, data):
                entries[key.casefold()] = (key, value, chinese)
        if has_runtime:
            for key, value, chinese in _runtime_entries(pak.stem, data):
                entries[key.casefold()] = (key, value, chinese)
    return entries.values()
