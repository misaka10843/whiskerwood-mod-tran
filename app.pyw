import os
import json
import sqlite3
import subprocess
import sys
import tkinter as tk
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app_paths import bundled, data_directory, default_workshop, migrate_data
from localization import (TARGET_ID, decode, export_text, game_text, import_text, is_option,
                          scan, translated_mod_list, validate, write_translations)
from runtime_settings import RuntimeSettings, atomic_write, detect_game
from option_catalog import option_key
from pak_text import repak_path


DATA = data_directory()
BG, PANEL, INK, MUTED, ACCENT = "#f6f7f9", "#ffffff", "#242933", "#5d6674", "#2458b4"
RULE, HOVER, SELECTED = "#dee2e8", "#eef1f5", "#e7effd"
STATUSES = ("全部状态", "未翻译", "待写入", "已有译文")


def prepare_bundled_tools(data):
    if not bundled():
        return
    resources = Path(__file__).resolve().parent / "release-assets"
    files = {
        "repak.bin": "repak-0.2.3.exe",
        "repak-LICENSE-MIT.txt": "repak-LICENSE-MIT.txt",
        "repak-LICENSE-APACHE.txt": "repak-LICENSE-APACHE.txt",
    }
    for source, filename in files.items():
        target = data / "tools" / filename
        content = (resources / source).read_bytes()
        if not target.is_file() or target.read_bytes() != content:
            atomic_write(target, content)


class Drafts:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("""CREATE TABLE IF NOT EXISTS draft (
            project TEXT, key TEXT, mod TEXT, source TEXT, value TEXT,
            PRIMARY KEY (project, key, mod, source)
        )""")

    def load(self, project, entries):
        rows = self.db.execute("SELECT key, mod, source, value FROM draft WHERE project = ?", (project,))
        return {key: value for key, mod, source, value in rows
                if key in entries and (mod, source) == (entries[key].mod, entries[key].source)}

    def save(self, project, entries, values):
        with self.db:
            self.db.executemany("""INSERT INTO draft VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (project, key, mod, source) DO UPDATE SET value = excluded.value""",
                [(project, key, entries[key].mod, entries[key].source, value) for key, value in values.items()])

    def remove(self, project, entry):
        with self.db:
            self.db.execute("DELETE FROM draft WHERE project=? AND key=? AND mod=? AND source=?",
                            (project, entry.key.casefold(), entry.mod, entry.source))


class App:
    def __init__(self, window, data=DATA):
        self.window, self.data = window, data
        self.store = Drafts(data / "drafts.sqlite3")
        self.workshop_directory = data / "workshop-directory.txt"
        self.runtime_directory = data / "game-directory.txt"
        self.runtime_executor = None
        self.target = self.active = None
        self.entries, self.drafts = {}, {}
        self.mods = []
        self.mod = ""
        self.issues = []
        self.no_source = 0
        saved_workshop = (self.workshop_directory.read_text(encoding="utf-8").strip()
                          if self.workshop_directory.is_file() else "")
        self.root_path = tk.StringVar(value=saved_workshop or str(default_workshop() or ""))
        self.query = tk.StringVar()
        self.state_filter = tk.StringVar(value=STATUSES[0])
        self.origin = tk.StringVar(value="全部来源")
        self.options_only = tk.BooleanVar()
        self.summary, self.status, self.details, self.check = (tk.StringVar() for _ in range(4))
        self.window.title("Whiskerwood 翻译工作台")
        self.window.geometry("1280x800")
        self.window.minsize(1020, 660)
        self.window.configure(bg=BG)
        self.build()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Control-s>", self.save_shortcut)
        self.window.bind("<Control-f>", lambda _event: self.search.focus_set())
        self.window.bind("<Alt-Left>", lambda _event: self.move(-1))
        self.window.bind("<Alt-Right>", lambda _event: self.move(1))
        first_run = not self.workshop_directory.is_file()
        expected = Path(self.root_path.get()) / TARGET_ID
        if first_run and not (expected / "zh.txt").is_file():
            self.refresh()
            self.status.set("请选择 Steam 创意工坊目录")
            self.window.after_idle(self.initial_setup)
        else:
            self.reload()

    def initial_setup(self):
        messagebox.showinfo("首次设置", "请选择 Steam 创意工坊的 2489330 目录。"
                            "\n请先订阅简中文本小修 Mod（3643964887）。", parent=self.window)
        self.project_settings()

    def build(self):
        style = ttk.Style(self.window)
        style.theme_use("clam")
        style.configure(".", font=("Microsoft YaHei UI", 10), background=BG, foreground=INK,
                        bordercolor=RULE, lightcolor=RULE, darkcolor=RULE, focuscolor=ACCENT)
        style.configure("TButton", padding=(10, 5), background=PANEL, relief="flat")
        style.map("TButton", background=[("active", HOVER)])
        style.configure("Primary.TButton", background=ACCENT, foreground="white", bordercolor=ACCENT,
                        lightcolor=ACCENT, darkcolor=ACCENT)
        style.map("Primary.TButton", background=[("disabled", HOVER), ("active", "#1e4a98")],
                  foreground=[("disabled", MUTED)])
        style.configure("Filter.TButton", padding=(9, 4), background=BG, bordercolor=BG,
                        lightcolor=BG, darkcolor=BG)
        style.configure("Selected.Filter.TButton", background=SELECTED, foreground=ACCENT,
                        bordercolor=SELECTED, lightcolor=SELECTED, darkcolor=SELECTED)
        style.map("Selected.Filter.TButton", background=[("active", SELECTED)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, rowheight=32, borderwidth=0)
        style.configure("Treeview.Heading", padding=(7, 6), background=BG, foreground=MUTED, relief="flat")
        style.map("Treeview", background=[("selected", SELECTED)], foreground=[("selected", INK)])
        style.configure("Vertical.TScrollbar", arrowsize=11, width=10, background=RULE, troughcolor=BG)

        header = tk.Frame(self.window, bg=PANEL, padx=20, pady=13)
        header.pack(fill="x")
        tk.Label(header, text="Whiskerwood 翻译", bg=PANEL, fg=INK,
                 font=("Microsoft YaHei UI", 14, "bold")).pack(side="left")
        self.apply_button = ttk.Button(header, text="写入汉化 Mod", style="Primary.TButton", command=self.apply)
        self.apply_button.pack(side="right")
        exports = ttk.Menubutton(header, text="导出")
        menu = tk.Menu(exports, tearoff=False)
        menu.add_command(label="筛选结果 TXT…", command=self.export_file)
        menu.add_command(label="已翻译 Mod 清单…", command=self.export_mod_list)
        exports.configure(menu=menu)
        exports.pack(side="right", padx=7)
        ttk.Button(header, text="导入译文 TXT", command=self.import_file).pack(side="right")
        ttk.Button(header, text="分享译文", command=self.share_translations).pack(side="right", padx=7)

        ttk.Button(header, text="项目设置", command=self.project_settings).pack(side="right", padx=(0, 7))

        main = tk.Frame(self.window, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=(12, 8))
        rail = tk.Frame(main, bg=PANEL, padx=11, pady=12, width=210,
                        highlightbackground=RULE, highlightthickness=1)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        tk.Label(rail, text="Mod", bg=PANEL, fg=MUTED, anchor="w",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", pady=(0, 9))
        mod_list = tk.Frame(rail, bg=PANEL)
        mod_list.pack(fill="both", expand=True)
        self.components = tk.Listbox(mod_list, bg=PANEL, fg=INK, font=("Microsoft YaHei UI", 11),
                                     selectbackground=SELECTED, selectforeground=ACCENT, exportselection=False,
                                     activestyle="none", highlightthickness=0, borderwidth=0)
        rail_scroll = ttk.Scrollbar(mod_list, command=self.components.yview)
        self.components.configure(yscrollcommand=rail_scroll.set)
        rail_scroll.pack(side="right", fill="y")
        self.components.pack(side="left", fill="both", expand=True)
        self.components.bind("<<ListboxSelect>>", self.select_mod)
        ttk.Button(rail, text="扫描报告", command=self.report).pack(anchor="w", pady=(8, 0))

        work = ttk.Frame(main, padding=(14, 0, 0, 0))
        work.pack(side="left", fill="both", expand=True)
        filters = ttk.Frame(work)
        filters.pack(fill="x", pady=(0, 8))
        ttk.Label(filters, text="搜索").pack(side="left")
        self.search = ttk.Entry(filters, textvariable=self.query, width=32)
        self.search.pack(side="left", fill="x", expand=True, padx=8)
        self.combo(filters, self.origin, ("全部来源", "PAK", "外置文件", "UE4SS"), 12)
        ttk.Checkbutton(filters, text="仅设置文本", variable=self.options_only, command=self.refresh).pack(side="left")
        self.query.trace_add("write", lambda *_: self.refresh())
        states = ttk.Frame(work)
        states.pack(fill="x", pady=(0, 8))
        self.state_buttons = {}
        for state in STATUSES:
            button = ttk.Button(states, style="Filter.TButton",
                                command=lambda chosen=state: self.select_state(chosen))
            button.pack(side="left", padx=(0, 5))
            self.state_buttons[state] = button

        split = ttk.Panedwindow(work, orient="vertical")
        split.pack(fill="both", expand=True)
        listing = ttk.Frame(split)
        split.add(listing, weight=2)
        self.tree = ttk.Treeview(listing, columns=("status", "key", "source", "translation"),
                                 show="headings", selectmode="browse", height=7)
        for column, label, width in zip(self.tree["columns"],
                                       ("状态", "文本键", "英文原文", "简中译文"), (78, 260, 300, 290)):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, minwidth=65, stretch=column != "status")
        self.tree.tag_configure("待写入", foreground="#1657ab")
        self.tree.tag_configure("未翻译", foreground="#92530f")
        scroll = ttk.Scrollbar(listing, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_entry)

        edit = ttk.Frame(split, padding=(0, 8, 0, 0))
        split.add(edit, weight=3)
        ttk.Label(edit, textvariable=self.details, font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        texts = ttk.Panedwindow(edit, orient="horizontal")
        texts.pack(fill="both", expand=True, pady=(7, 6))
        source = ttk.Frame(texts)
        texts.add(source, weight=1)
        ttk.Label(source, text="英文原文").pack(anchor="w", pady=(0, 4))
        self.source = self.text_box(source)
        self.source.configure(state="disabled")
        editor = ttk.Frame(texts)
        texts.add(editor, weight=1)
        ttk.Label(editor, text="简中译文").pack(anchor="w", pady=(0, 4))
        self.translation = self.text_box(editor)
        self.translation.bind("<<Modified>>", self.on_modified)
        controls = ttk.Frame(edit)
        controls.pack(fill="x")
        ttk.Button(controls, text="上一条", command=lambda: self.move(-1)).pack(side="left")
        ttk.Button(controls, text="下一条", command=lambda: self.move(1)).pack(side="left", padx=6)
        ttk.Button(controls, text="还原译文", command=self.restore).pack(side="right")
        ttk.Button(controls, text="保存草稿 · Ctrl+S", style="Primary.TButton",
                   command=self.save_and_refresh).pack(side="right", padx=6)
        ttk.Label(edit, textvariable=self.check, foreground=MUTED).pack(anchor="w", pady=(6, 0))
        footer = ttk.Frame(self.window, padding=(16, 0, 16, 8))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=self.summary).pack(side="left")
        ttk.Label(footer, textvariable=self.status, foreground=MUTED).pack(side="right")

    def combo(self, parent, variable, values, width):
        combo = ttk.Combobox(parent, textvariable=variable, values=values, width=width, state="readonly")
        combo.pack(side="left", padx=(0, 6))
        combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

    def text_box(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        widget = tk.Text(frame, height=8, width=25, wrap="word", undo=True, bg=PANEL, fg=INK,
                         padx=12, pady=9, relief="flat", insertbackground=INK, font=("Microsoft YaHei UI", 11))
        scroll = ttk.Scrollbar(frame, command=widget.yview)
        widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        widget.pack(fill="both", expand=True)
        return widget

    @property
    def project(self):
        return os.path.normcase(str(self.target.resolve()))

    def project_settings(self):
        settings = tk.Toplevel(self.window)
        settings.title("项目设置")
        settings.transient(self.window)
        settings.resizable(False, False)
        panel = ttk.Frame(settings, padding=16)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="创意工坊目录").pack(anchor="w")
        path = tk.StringVar(value=self.root_path.get())
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=8)
        ttk.Entry(row, textvariable=path, width=66).pack(side="left", padx=(0, 8))
        def browse():
            chosen = filedialog.askdirectory(parent=settings, initialdir=path.get())
            if chosen:
                path.set(chosen)

        def rescan():
            self.root_path.set(path.get())
            settings.destroy()
            self.reload()

        ttk.Button(row, text="浏览…", command=browse).pack(side="left")
        ttk.Button(panel, text="扫描目录", style="Primary.TButton", command=rescan).pack(anchor="e")
        ttk.Separator(panel).pack(fill="x", pady=12)
        ttk.Button(panel, text="UE4SS 设置汉化…", command=lambda: self.runtime_dialog(settings)).pack(anchor="w")
        settings.grab_set()

    def runtime_dialog(self, settings):
        dialog = tk.Toplevel(settings)
        dialog.title("UE4SS 设置汉化")
        dialog.transient(settings)
        dialog.resizable(False, False)
        panel = ttk.Frame(dialog, padding=16)
        panel.pack(fill="both", expand=True)
        folder = tk.StringVar(value=str(self.game_directory() or ""))
        status = tk.StringVar()
        ttk.Label(panel, text="Whiskerwood 游戏目录").pack(anchor="w")
        row = ttk.Frame(panel)
        row.pack(fill="x", pady=8)
        path_entry = ttk.Entry(row, textvariable=folder, width=65)
        path_entry.pack(side="left", padx=(0, 8))

        def refresh():
            try:
                runtime = RuntimeSettings(Path(folder.get().strip()), self.data)
                status.set(runtime.status())
            except (OSError, ValueError) as exc:
                status.set(str(exc))

        def browse():
            path = filedialog.askdirectory(parent=dialog, initialdir=folder.get())
            if path:
                folder.set(path)
                refresh()

        browse_button = ttk.Button(row, text="浏览…", command=browse)
        browse_button.pack(side="left")
        path_entry.bind("<FocusOut>", lambda _event: refresh())
        ttk.Label(panel, textvariable=status, wraplength=540).pack(anchor="w", pady=(2, 4))
        ttk.Label(panel, text="汉化设置名称和说明。安装、停用或卸载前请退出游戏。",
                  foreground=MUTED, wraplength=540).pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        buttons = [path_entry, browse_button]

        def perform(action, title, confirm=None):
            try:
                game = Path(folder.get().strip()).resolve()
                runtime = RuntimeSettings(game, self.data)
                runtime.ensure_game_closed()
            except (OSError, ValueError) as exc:
                messagebox.showerror(title, str(exc), parent=dialog)
                return
            if confirm and not messagebox.askyesno(title, confirm, parent=dialog):
                return
            for button in buttons:
                button.state(["disabled"])
            status.set(f"{title}中…")
            executor = ThreadPoolExecutor(max_workers=1)
            self.runtime_executor = executor
            future = executor.submit(action, runtime)

            def finish():
                if not future.done():
                    dialog.after(100, finish)
                    return
                executor.shutdown(wait=False)
                self.runtime_executor = None
                for button in buttons:
                    button.state(["!disabled"])
                try:
                    result = future.result()
                    atomic_write(self.runtime_directory, str(game).encode("utf-8"))
                    self.reload()
                    if result:
                        messagebox.showinfo(title, "保留了以下已被修改的文件\n\n" + "\n".join(result),
                                            parent=dialog)
                except Exception as exc:
                    messagebox.showerror(title, str(exc), parent=dialog)
                refresh()

            dialog.after(100, finish)

        options = (
            ("安装并启用", RuntimeSettings.install,
             "从官方 GitHub 发布下载并校验 UE4SS，随后安装设置汉化。继续安装？"),
            ("启用汉化", lambda runtime: runtime.enable(True), None),
            ("停用汉化", lambda runtime: runtime.enable(False), None),
            ("卸载 UE4SS", RuntimeSettings.uninstall,
             "移除翻译工具安装且内容未被修改的 UE4SS 文件和汉化插件。继续卸载？"),
        )
        for index, (label, operation, prompt) in enumerate(options):
            button = ttk.Button(actions, text=label, style="Primary.TButton" if index == 0 else "TButton",
                                command=lambda op=operation, t=label, p=prompt: perform(op, t, p))
            button.pack(side="left", padx=(0, 7))
            buttons.append(button)

        def close_dialog():
            if self.runtime_executor is None:
                dialog.destroy()
                settings.grab_set()

        dialog.protocol("WM_DELETE_WINDOW", close_dialog)
        dialog.grab_set()
        refresh()

    def game_directory(self):
        if self.runtime_directory.is_file():
            configured = self.runtime_directory.read_text(encoding="utf-8").strip()
            if configured:
                return Path(configured)
        workshop = self.root_path.get().strip()
        return detect_game(Path(workshop) if workshop else None)

    def reload(self):
        if not self.save_current():
            return
        self.status.set("正在扫描创意工坊…")
        self.window.update_idletasks()
        try:
            target, entries, self.no_source, self.issues = scan(Path(self.root_path.get().strip()).resolve())
        except (OSError, ValueError) as exc:
            self.status.set("扫描失败")
            messagebox.showerror("扫描失败", str(exc))
            return
        self.target = target
        try:
            atomic_write(self.workshop_directory, str(target.parent.parent).encode("utf-8"))
        except OSError as exc:
            messagebox.showerror("无法保存项目路径", str(exc))
        try:
            translations = RuntimeSettings(self.game_directory(), self.data).translations()
        except (OSError, ValueError):
            translations = {}
        self.entries = {}
        for entry in entries:
            if entry.origin == "UE4SS":
                option, field = option_key(entry.key)
                entry = replace(entry, current=translations.get(option, {}).get(field, ""))
            self.entries[entry.key.casefold()] = entry
        self.drafts = self.store.load(self.project, self.entries)
        self.active = None
        self.update_components()
        self.refresh()
        self.status.set("扫描完成" if not self.issues else f"扫描完成 · {len(self.issues)} 条提示")

    def update_components(self):
        mods = list(dict.fromkeys(entry.mod for entry in self.entries.values()))
        self.mods = ["", *mods]
        if self.mod not in self.mods:
            self.mod = ""
        self.components.delete(0, "end")
        self.components.insert("end", "全部 Mod")
        names = [mod.rsplit(" (", 1)[0] for mod in mods]
        for mod, name in zip(mods, names):
            self.components.insert("end", mod if names.count(name) > 1 else name)
        self.sync_component()

    def sync_component(self):
        self.components.selection_clear(0, "end")
        self.components.selection_set(self.mods.index(self.mod))

    def select_state(self, state):
        self.state_filter.set(state)
        self.refresh()

    def select_mod(self, _event=None):
        selection = self.components.curselection()
        if selection:
            mod = self.mods[selection[0]]
            if mod == self.mod:
                return
            if self.save_current():
                self.mod = mod
                self.refresh()
            else:
                self.sync_component()

    def value(self, key):
        return self.drafts.get(key, self.entries[key].current)

    def entry_status(self, key):
        value = self.value(key)
        if not value:
            return "未翻译"
        rendered = value if self.entries[key].origin == "UE4SS" else game_text(value)
        if key in self.drafts and rendered != self.entries[key].current:
            return "待写入"
        return "已有译文"

    def refresh(self, preferred=None):
        dirty = self.active is not None and self.editor_value() != self.value(self.active)
        if dirty and self.save_current(quiet=True):
            dirty = False
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().strip().casefold()
        state_filter, origin = self.state_filter.get(), self.origin.get()
        counts = dict.fromkeys(STATUSES[1:], 0)
        for key, entry in self.entries.items():
            state, value = self.entry_status(key), self.value(key)
            if self.mod and self.mod != entry.mod or origin != "全部来源" and origin != entry.origin:
                continue
            if self.options_only.get() and not is_option(entry):
                continue
            if query and not any(query in item.casefold() for item in (entry.mod, entry.key, entry.source, value)):
                continue
            counts[state] += 1
            if state_filter != STATUSES[0] and state != state_filter:
                continue
            self.tree.insert("", "end", iid=key, tags=(state,), values=(
                state, entry.key, " ".join(entry.source.split()), " ".join(value.split())))
        visible = self.tree.get_children()
        selected = preferred or self.active
        if selected not in visible:
            selected = visible[0] if visible else None
        if self.active != selected and dirty:
            selected = self.active
        if selected in visible:
            self.tree.selection_set(selected)
            self.tree.see(selected)
        if self.active != selected or selected is None:
            self.show_entry(selected)
        for state, button in self.state_buttons.items():
            count = sum(counts.values()) if state == STATUSES[0] else counts[state]
            label = "全部" if state == STATUSES[0] else state
            button.configure(text=f"{label}  {count}",
                             style="Selected.Filter.TButton" if state == state_filter else "Filter.TButton")
        self.summary.set(f"{len(visible)} 条 · {self.mod.rsplit(' (', 1)[0] if self.mod else '全部 Mod'}")
        self.apply_button.configure(state="normal" if self.target else "disabled")

    def select_entry(self, _event=None):
        selected = self.tree.selection()
        if not selected or selected[0] == self.active:
            return
        if not self.save_current():
            if self.active and self.tree.exists(self.active):
                self.tree.selection_set(self.active)
            return
        self.show_entry(selected[0])
        self.refresh(selected[0])

    def show_entry(self, key):
        self.active = key
        entry = self.entries.get(key)
        self.details.set(f"{entry.mod}  /  {entry.origin}  /  {entry.key}" if entry else "没有符合筛选条件的条目")
        self.set_text(self.source, entry.source if entry else "", readonly=True)
        self.set_text(self.translation, self.value(key) if entry else "", readonly=not entry)
        self.update_check()

    @staticmethod
    def set_text(widget, value, readonly=False):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.edit_reset()
        widget.edit_modified(False)
        if readonly:
            widget.configure(state="disabled")

    def editor_value(self):
        return self.translation.get("1.0", "end-1c")

    def on_modified(self, _event):
        if self.translation.edit_modified():
            self.translation.edit_modified(False)
            self.update_check()

    def update_check(self):
        if not self.active:
            self.check.set("")
            return
        value = self.editor_value()
        if not value:
            self.check.set("等待翻译")
            return
        try:
            validate(self.entries[self.active], value)
        except ValueError as exc:
            self.check.set(str(exc))
            return
        self.check.set("校验通过" if value == self.value(self.active) else "草稿尚未保存")

    def save_current(self, quiet=False):
        if not self.active or self.editor_value() == self.value(self.active):
            return True
        try:
            value = validate(self.entries[self.active], self.editor_value())
            self.store.save(self.project, self.entries, {self.active: value})
        except (sqlite3.Error, ValueError) as exc:
            if not quiet:
                messagebox.showerror("无法保存草稿", f"{exc}\n可修正译文，或用「还原已写入译文」退出本次编辑。")
            return False
        self.drafts[self.active] = value
        if self.editor_value() != value:
            self.set_text(self.translation, value)
        self.update_check()
        self.status.set("草稿已保存")
        return True

    def save_shortcut(self, _event):
        self.save_and_refresh()
        return "break"

    def save_and_refresh(self):
        if self.save_current():
            self.refresh()

    def restore(self):
        if not self.active or not messagebox.askyesno("还原译文", "清除当前条目的本地草稿并恢复扫描到的译文？"):
            return
        try:
            self.store.remove(self.project, self.entries[self.active])
        except sqlite3.Error as exc:
            messagebox.showerror("还原失败", str(exc))
            return
        self.drafts.pop(self.active, None)
        self.show_entry(self.active)
        self.refresh()

    def move(self, step):
        visible = self.tree.get_children()
        if not visible:
            return
        index = visible.index(self.active) + step if self.active in visible else 0
        if 0 <= index < len(visible):
            self.tree.selection_set(visible[index])
            self.tree.see(visible[index])

    def report(self):
        details = "\n".join(self.issues) or "扫描未报告错误。"
        messagebox.showinfo("扫描报告", f"共 {len(self.entries)} 条文本，"
                            f"其中 {sum(e.origin == 'PAK' for e in self.entries.values())} 条来自 PAK。\n"
                            f"{self.no_source} 个 Mod 未提取到文本。\n\n{details}")

    def export_file(self):
        if not self.save_current():
            return
        self.refresh()
        keys = self.tree.get_children()
        if not keys:
            messagebox.showinfo("导出", "当前筛选没有文本。")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="whiskerwood-translation.txt",
                                               filetypes=[("文本文件", "*.txt")])
        if filename:
            try:
                path = Path(filename).resolve()
                if path.is_relative_to(self.target.parent.parent):
                    raise ValueError("请将翻译交换文件保存到创意工坊目录之外。")
                path.write_text(export_text(replace(self.entries[k], current=self.value(k)) for k in keys),
                                encoding="utf-8")
            except (OSError, ValueError) as exc:
                messagebox.showerror("导出失败", str(exc))
                return
            self.status.set(f"已导出 {len(keys)} 条")

    def export_mod_list(self):
        if not self.target or not self.save_current():
            return
        entries = (replace(entry, current=self.value(key)) for key, entry in self.entries.items())
        text = translated_mod_list(self.target.parent.parent, entries)
        if not text:
            messagebox.showinfo("导出清单", "没有已翻译的 Mod。")
            return
        filename = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="whiskerwood-mods.txt",
                                               filetypes=[("文本文件", "*.txt")])
        if not filename:
            return
        try:
            path = Path(filename).resolve()
            if path.is_relative_to(self.target.parent.parent):
                raise ValueError("请将清单保存到创意工坊目录之外。")
            path.write_text(text, encoding="utf-8")
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self.status.set(f"已导出 {len(text.splitlines())} 个 Mod")

    def share_translations(self):
        if not self.target or not self.save_current():
            return
        self.refresh()
        entries = [replace(self.entries[key], current=self.value(key)) for key in self.tree.get_children()
                   if self.value(key)]
        if not entries:
            messagebox.showinfo("分享译文", "当前筛选内没有译文可分享。")
            return
        if not messagebox.askokcancel(
            "分享译文",
            f"复制当前筛选中的 {len(entries)} 条译文及原文，并打开 GitHub Gist？\n\n"
            "登录后将文本贴到 whiskerwood-translation.txt，创建 Gist 即可拿到链接。"
            "选择 Secret Gist 时，知道链接的人可以查看。"
        ):
            return
        self.window.clipboard_clear()
        self.window.clipboard_append(export_text(entries))
        self.status.set(f"已复制 {len(entries)} 条译文")
        if not webbrowser.open("https://gist.github.com/"):
            messagebox.showinfo("译文已复制", "浏览器未打开，请访问 gist.github.com 粘贴并创建 Gist。")

    def import_file(self):
        if not self.target or not self.save_current():
            return
        filename = filedialog.askopenfilename(filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")])
        if not filename:
            return
        try:
            values = import_text(decode(Path(filename).read_bytes()), self.entries)
            self.store.save(self.project, self.entries, values)
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror("导入失败", str(exc))
            return
        self.drafts.update(values)
        self.show_entry(self.active)
        self.refresh()
        self.status.set(f"已导入并保存 {len(values)} 条")
        multiline = sum(game_text(value) != value for key, value in values.items()
                        if self.entries[key].origin != "UE4SS")
        messagebox.showinfo("导入完成", f"已保存 {len(values)} 条译文。"
                            f"\n其中 {multiline} 条将在写入时合并为单行。")

    def apply(self):
        if not self.target or not self.save_current():
            return
        pending = {key: value for key, value in self.drafts.items() if self.entry_status(key) == "待写入"}
        if not pending:
            messagebox.showinfo("写入汉化 Mod", "没有待写入译文。")
            return
        keyed, runtime_entries = {}, {}
        for key, value in pending.items():
            entry = self.entries[key]
            if entry.origin == "UE4SS":
                option, field = option_key(entry.key)
                runtime_entries.setdefault(option, {})[field] = value
            else:
                keyed[key] = value
        multiline = sum(game_text(value) != value for value in keyed.values())
        if not messagebox.askyesno("写入汉化 Mod", f"将写入 {len(pending)} 条，自动备份原文件。"
                                   f"\n{sum(map(len, runtime_entries.values()))} 条通过 UE4SS，"
                                   f"{multiline} 条将合并为单行。"):
            return
        try:
            if runtime_entries:
                RuntimeSettings(self.game_directory(), self.data).apply_translations(runtime_entries)
            backup = write_translations(self.target, self.entries, keyed, self.data / "backups")
        except (OSError, ValueError) as exc:
            messagebox.showerror("写入失败", str(exc))
            return
        self.root_path.set(str(self.target.parent.parent))
        self.reload()
        messagebox.showinfo("写入完成", "重启游戏后查看译文。" + (f"\n\n备份：{backup}" if backup else ""))

    def close(self):
        if self.runtime_executor is not None:
            return
        if self.save_current() or messagebox.askyesno("退出", "放弃当前未通过校验的修改并退出？"):
            self.store.db.close()
            self.window.destroy()


def smoke_test():
    prepare_bundled_tools(DATA)
    tool = DATA / "tools" / "repak-0.2.3.exe"
    if repak_path() != str(tool):
        raise RuntimeError("未找到 EXE 内置的 repak")
    info = subprocess.run([str(tool), "--version"], check=True, capture_output=True,
                          text=True, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()
    with (Path(__file__).resolve().parent / "ue4ss_settings.lua").open(encoding="utf-8") as script:
        if "RegisterModOptions" not in script.read():
            raise RuntimeError("缺少 UE4SS Lua 脚本")
    window = tk.Tk()
    window.withdraw()
    tcl = window.tk.call("info", "patchlevel")
    window.destroy()
    drafts = Drafts(DATA / "drafts.sqlite3")
    drafts.db.close()
    atomic_write(DATA / "smoke-test.json", json.dumps({"repak": info, "tcl": tcl}).encode("utf-8"))


if __name__ == "__main__":
    if sys.argv[1:] == ["--smoke-test"]:
        smoke_test()
    else:
        window = tk.Tk()
        try:
            migrate_data(DATA)
            prepare_bundled_tools(DATA)
            App(window)
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror("启动失败", f"请将程序放到可写目录，例如桌面。\n\n{exc}", parent=window)
            window.destroy()
            raise SystemExit(1) from exc
        window.mainloop()
