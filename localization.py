import codecs
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pak_text import read_pak, repak_path
from option_catalog import RUNTIME_KEY
from app_paths import LOCALIZATION_MOD_ID


TARGET_ID = LOCALIZATION_MOD_ID
KEY = re.compile(r"[\w.\-/:]+")
TOKEN = re.compile(
    r"\{[^{}\r\n]+\}|%(?:\d+\$)?[-+#0 .\d]*[sdif]|%%|"
    r"<[/!]?[A-Za-z][^<>\r\n]*>|</>|\\[nrt]"
)


def decode(data):
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16")
    return data.decode("utf-8-sig")


def read_rows(content, filename, delimiter=None):
    rows = {}
    meaningful = [
        (number, line.strip())
        for number, line in enumerate(content.splitlines(), 1)
        if line.strip() and not line.lstrip().startswith(("#", "//", "[["))
    ]
    fixed_delimiter = delimiter
    delimiter = delimiter or ","
    if meaningful:
        first = meaningful[0][1]
        candidate = re.split(r"\s*([,|;\t])\s*", first, maxsplit=1)
        if len(candidate) == 3 and not fixed_delimiter:
            delimiter = candidate[1]
            if (candidate[0].casefold(), candidate[2].casefold()) in {
                ("key", "value"), ("id", "text"), ("string id", "translated text")
            }:
                meaningful.pop(0)
    for number, line in meaningful:
        key, separator, value = line.partition(delimiter)
        key, value = key.strip(), value.strip()
        if not separator or not KEY.fullmatch(key) or not value:
            raise ValueError(f"{filename}:{number} 无法识别文本键或内容")
        folded = key.casefold()
        if folded in rows:
            raise ValueError(f"{filename}:{number} 重复的键 {key}")
        rows[folded] = (key, value)
    return rows


@dataclass(frozen=True)
class Entry:
    mod: str
    key: str
    source: str
    current: str = ""
    origin: str = "外置文件"


def scan(root):
    target = root / TARGET_ID / "zh.txt"
    if not target.is_file() or not (target.parent / "zhLocalization.pak").is_file():
        raise ValueError(f"未找到汉化 Mod 的 zh.txt 或 zhLocalization.pak：{target.parent}")
    overrides = read_rows(decode(target.read_bytes()), target, ",")
    entries, issues = {}, []
    repak = repak_path()
    if not repak:
        issues.append("未找到 repak.exe，PAK 未扫描。可将 repak.exe 放入 PATH。")
    without_source = 0
    hardcoded_options = set()
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not folder.name.isdecimal() or folder.name == TARGET_ID:
            continue
        plugins = sorted(folder.rglob("*.uplugin"))
        sources = sorted({
            path for directory in {folder, *(plugin.parent for plugin in plugins)}
            for name in ("en.txt", "en.csv", "strings.txt", "strings.csv")
            if (path := directory / name).is_file()
        })
        loose_keys = set()
        for path in sources:
            plugin = next((p for p in plugins if p.parent == path.parent), None)
            mod = f"{plugin.stem if plugin else folder.name} ({folder.name})"
            try:
                local = path.parent / "zh.txt"
                native = read_rows(decode(local.read_bytes()), local) if local.is_file() else {}
                for folded, (key, source) in read_rows(decode(path.read_bytes()), path).items():
                    current = overrides.get(folded, native.get(folded, ("", "")))[1]
                    entries.setdefault(folded, set()).add(Entry(mod, key, source, current))
                    loose_keys.add(folded)
            except (OSError, ValueError) as exc:
                issues.append(str(exc))
        found_pak_text = False
        if repak:
            for pak in sorted(folder.rglob("*.pak")):
                try:
                    options = None if any((p.parent / "ModOptions.txt").is_file() for p in plugins) else hardcoded_options
                    for key, source, chinese in read_pak(repak, pak, read_rows, decode, options):
                        folded = key.casefold()
                        found_pak_text = True
                        if folded in loose_keys:
                            continue
                        current = overrides.get(folded, ("", chinese))[1]
                        mod = f"{pak.stem} ({folder.name})"
                        origin = "UE4SS" if key.startswith(RUNTIME_KEY) else "PAK"
                        entries.setdefault(folded, set()).add(Entry(mod, key, source, current, origin))
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    issues.append(f"{pak.name}：{exc}")
        if not loose_keys and not found_pak_text:
            without_source += 1
    result = []
    for folded, candidates in entries.items():
        if len(candidates) == 1:
            result.append(next(iter(candidates)))
        else:
            issues.append(f"文本键冲突，已跳过：{folded}（{', '.join(sorted({e.mod for e in candidates}))}）")
    if hardcoded_options:
        issues.append("以下 Mod 直接注册设置文本，需要 UE4SS："
                      + "、".join(sorted(hardcoded_options)))
    return target, sorted(result, key=lambda e: (e.mod, e.key.casefold())), without_source, issues


def is_option(entry):
    return bool({"setting", "settings", "option", "options", "education"}.intersection(
        entry.key.casefold().split(".")
    ))


def translated_mod_list(root, entries):
    mods = {}
    for entry in entries:
        if not entry.current:
            continue
        stem, _, workshop_id = entry.mod.removesuffix(")").rpartition(" (")
        if not workshop_id.isdecimal() or workshop_id in mods:
            continue
        plugin = next((root / workshop_id).rglob(f"{stem}.uplugin"), None)
        name = stem
        if plugin:
            try:
                record = json.loads(decode(plugin.read_bytes()))
                title = record.get("Name") if isinstance(record, dict) else None
                if isinstance(title, str) and title.strip():
                    name = " ".join(title.split())
            except (ValueError, OSError):
                pass
        mods[workshop_id] = name
    return "".join(f"{name}\t{workshop_id}\n" for workshop_id, name in
                   sorted(mods.items(), key=lambda pair: (pair[1].casefold(), pair[0])))


def export_text(entries):
    instructions = (
        "# 将 source 翻译成简体中文，填写 translation。已有译文可保留或润色。\n"
        "# 返回纯文本，每行一个 JSON 对象。保留 key、source、mod 字段原样。\n"
        "# 保留占位符和标签。允许保留段落，在 JSON 字符串中用 \\n 表示换行。\n"
    )
    return instructions + "".join(json.dumps({
        "mod": e.mod, "key": e.key, "source": e.source, "translation": e.current
    }, ensure_ascii=False) + "\n" for e in entries)


def validate(entry, value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("译文不能为空或仅包含空白")
    if any((ord(char) < 32 and char not in "\r\n\t") or 127 <= ord(char) <= 159 for char in value):
        raise ValueError("译文包含控制字符")
    if Counter(TOKEN.findall(entry.source)) != Counter(TOKEN.findall(value)):
        raise ValueError("占位符或标签与原文不一致")
    value.encode("utf-8")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def game_text(value):
    """The localization Mod reads one key and value per physical line."""
    paragraphs = re.split(r"(?:\n[ \t]*){2,}", value)
    return "　　".join(" ".join(part.replace("\t", " ").splitlines()).strip() for part in paragraphs)


def import_text(content, entries):
    edits, errors, seen = {}, [], set()
    for number, raw in enumerate(content.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "```")):
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get("key"), str):
                raise ValueError("缺少文本键")
            key = row["key"].casefold()
            entry = entries.get(key)
            if not entry or (row.get("key"), row.get("source"), row.get("mod")) != (
                entry.key, entry.source, entry.mod
            ):
                raise ValueError(f"文本键、原文或 Mod 与扫描结果不匹配：{row['key']}")
            if key in seen:
                raise ValueError(f"重复的文本键：{row['key']}")
            seen.add(key)
            value = row.get("translation")
            if value != "":
                try:
                    edits[key] = validate(entry, value)
                except ValueError as exc:
                    raise ValueError(f"{entry.key} · {exc}") from exc
        except ValueError as exc:
            errors.append(f"第 {number} 行：{exc}")
    if errors:
        raise ValueError("\n".join(errors[:15]) + (f"\n共 {len(errors)} 处错误" if len(errors) > 15 else ""))
    return edits


def write_translations(target, entries, edits, backup_dir):
    if not edits:
        return None
    original = target.read_bytes()
    content = decode(original)
    read_rows(content, target, ",")
    newline = "\r\n" if "\r\n" in content else "\n"
    pending = {key: game_text(validate(entries[key], value)) for key, value in edits.items()}
    lines = []
    for line in content.splitlines(keepends=True):
        key, separator, _ = line.partition(",")
        folded = key.strip().casefold()
        if separator and folded in pending:
            ending = line[len(line.rstrip("\r\n")):]
            line = f"{key},{pending.pop(folded)}{ending}"
        lines.append(line)
    if pending:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines.append(newline)
        lines.extend(f"{entries[key].key},{value}{newline}" for key, value in pending.items())
    updated = "".join(lines)
    bom, encoding = next(
        ((bom, encoding) for bom, encoding in (
            (codecs.BOM_UTF8, "utf-8"), (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be")
        ) if original.startswith(bom)), (b"", "utf-8")
    )
    data = bom + updated.encode(encoding)
    if data == original:
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"zh-{datetime.now():%Y%m%d-%H%M%S-%f}.txt"
    with backup.open("xb") as file:
        file.write(original)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
        temporary = Path(file.name)
        file.write(data)
    try:
        if target.read_bytes() != original:
            raise ValueError("zh.txt 已被其他程序修改，请重试")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return backup
