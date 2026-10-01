"""
FusionFix Project Setup Wizard
================================
Run this script once after cloning FusionFixTemplate to configure your new project.
It will substitute all {{TOKEN}} placeholders across the repository, manage git
submodules, and optionally make an initial commit.

After applying changes this script deletes itself.

Requirements: Python 3.9+ with tkinter
"""

import json
import setup_emulators
import re
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_JSON = SCRIPT_DIR / "template.json"

# Files that contain {{TOKEN}} markers and should be substituted
TEMPLATE_FILES = [
    ".gitignore",
    ".github/workflows/msvc.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/performance.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    "premake5.bat",
    "premake5.lua",
    "release.bat",
    "readme.md",
    "source/resources/Versioninfo.rc",
    "source/resources/VersionInfo.h",
]

# Map from architecture UI label → (architecture token, msbuild_platform, UAL tag, UAL filename)
ARCH_PRESETS = {
    "x86 (Win32)": ("x86", "Win32", "Win32-latest", "dinput8-Win32.zip"),
    "x64":         ("x64", "x64",   "x64-latest",   "dinput8-x64.zip"),
}

LICENSE_TEXTS = {
    "GPL-3.0 license": "GPL-3.0-only",
    "GPL-3.0-or-later": "GPL-3.0-or-later",
    "MIT": "MIT",
    "Unlicense": "Unlicense",
}

GPL_LICENSE_TEMPLATE_PATH = SCRIPT_DIR / "license-templates" / "GPL-3.0.txt"

LICENSE_FILE_CONTENT = {
    "MIT": """MIT License

Copyright (c) {{YEAR}} {{AUTHOR}}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""",
    "Unlicense": """This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this
software, either in source code form or as a compiled binary, for any purpose,
commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain. We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors. We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>
""",
}

OUTPUT_PRESETS = {
    "SharedLib (.asi)": ("SharedLib", ".asi"),
    "SharedLib (.dll)": ("SharedLib", ".dll"),
}

PREMAKE_VERSIONS = ["vs2026", "vs2022", "vs2019"]

# ---------------------------------------------------------------------------
# Per-submodule premake5.lua snippet map
# Each entry is a list of premake lines (without leading indentation — it is
# added when injecting). Lines may reference the submodule's actual path via
# {path} which is filled in at inject time so custom paths work too.
# ---------------------------------------------------------------------------
SUBMODULE_PREMAKE = {
    "injector": [
        'includedirs {{ "{path}/include" }}',
        'includedirs {{ "{path}/safetyhook/include" }}',
        'includedirs {{ "{path}/zydis" }}',
        'files {{ "{path}/safetyhook/include/**.hpp", "{path}/safetyhook/src/**.cpp" }}',
        'files {{ "{path}/zydis/**.h", "{path}/zydis/**.c" }}',
    ],
    "hooking": [
        'includedirs {{ "{path}" }}',
        'files {{ "{path}/Hooking.Patterns.h", "{path}/Hooking.Patterns.cpp" }}',
    ],
    "inireader": [
        'includedirs {{ "{path}" }}',
    ],
    "modupdater": [
        'includedirs {{ "{path}/dist" }}',
        'libdirs {{ "{path}/dist" }}',
        'filter {{ "configurations:Release", "architecture:x86" }}',
        '   links {{ "libmodupdater_release_win32" }}',
        'filter {{ "configurations:Release", "architecture:x86_64" }}',
        '   links {{ "libmodupdater_release_x64" }}',
        'filter {{ "configurations:Debug", "architecture:x86" }}',
        '   links {{ "libmodupdater_debug_win32" }}',
        'filter {{ "configurations:Debug", "architecture:x86_64" }}',
        '   links {{ "libmodupdater_debug_x64" }}',
        'filter {{}}',
    ],
    "spdlog": [
        'includedirs {{ "{path}/include" }}',
    ],
    "filewatch": [
        'includedirs {{ "{path}" }}',
    ],
    "modutils": [
        'includedirs {{ "{path}" }}',
    ],
    # plugin-sdk generates a dedicated sub-project; snippets are built dynamically
    # in _inject_premake_submodules based on the selected game target.
    "plugin-sdk": [],
}

WELL_KNOWN_SUBMODULES = [
    ("injector",   "external/injector",   "https://github.com/ThirteenAG/injector"),
    ("hooking",    "external/hooking",    "https://github.com/ThirteenAG/Hooking.Patterns"),
    ("inireader",  "external/inireader",  "https://github.com/ThirteenAG/IniReader"),
    ("plugin-sdk", "external/plugin-sdk", "https://github.com/DK22Pac/plugin-sdk"),
    ("modupdater", "external/modupdater", "https://github.com/ThirteenAG/modupdater"),
    ("spdlog",     "external/spdlog",     "https://github.com/gabime/spdlog"),
    ("filewatch",  "external/filewatch",  "https://github.com/ThomasMonkman/filewatch"),
    ("modutils",   "external/modutils",   "https://github.com/CookiePLMonster/ModUtils"),
]

# Default enabled submodules
DEFAULT_ENABLED = {"injector", "hooking", "inireader"}

# plugin-sdk: available game targets
# Each entry: (display label, plugin folder, game folder, game define, extra defines, arch)
PLUGIN_SDK_GAMES = [
    ("GTA III",                        "plugin_III",        "game_III",        "GTA3",         ["PLUGIN_SGV_10EN", "RW"],                              "x32"),
    ("GTA Vice City",                  "plugin_vc",         "game_vc",         "GTAVC",         ["PLUGIN_SGV_10EN", "RW"],                              "x32"),
    ("GTA San Andreas",                "plugin_sa",         "game_sa",         "GTASA",         ["PLUGIN_SGV_10US", "RW"],                              "x32"),
    ("GTA IV",                         "plugin_IV",         "game_IV",         "GTAIV",         ["PLUGIN_SGV_CE",   "RAGE"],                            "x32"),
    ("GTA III – Definitive Edition",   "plugin_iii_unreal", "game_iii_unreal", "GTA3_UNREAL",   ["PLUGIN_UNREAL", "UNREAL", "NOASM", "RWINT32FROMFLOAT", "_WIN64"], "x64"),
    ("GTA VC – Definitive Edition",    "plugin_vc_unreal",  "game_vc_unreal",  "GTAVC_UNREAL",  ["PLUGIN_UNREAL", "UNREAL", "NOASM", "RWINT32FROMFLOAT", "_WIN64"], "x64"),
    ("GTA SA – Definitive Edition",    "plugin_sa_unreal",  "game_sa_unreal",  "GTASA_UNREAL",  ["PLUGIN_UNREAL", "UNREAL", "NOASM", "RWINT32FROMFLOAT", "_WIN64"], "x64"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_defaults() -> dict:
    if TEMPLATE_JSON.exists():
        with open(TEMPLATE_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _arch_label(arch: str) -> str:
    for label, (a, *_) in ARCH_PRESETS.items():
        if a == arch:
            return label
    return "x64"


def _output_label(kind: str, ext: str) -> str:
    for label, (k, e) in OUTPUT_PRESETS.items():
        if k == kind and e == ext:
            return label
    return "SharedLib (.asi)"

def _repo_path_from_url(repo_url: str) -> str:
    match = re.match(r"^https?://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", repo_url.strip())
    return match.group(1) if match else ""


def substitute_file(path: Path, tokens: dict) -> None:
    """Replace all {{KEY}} occurrences in a file."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return  # skip binary files
    for key, value in tokens.items():
        text = text.replace("{{" + key + "}}", value)
    path.write_text(text, encoding="utf-8")


def build_gitmodules(submodules: list) -> str:
    lines = []
    for sm in submodules:
        lines.append(f'[submodule "{sm["path"]}"]')
        lines.append(f'\tpath = {sm["path"]}')
        lines.append(f'\turl = {sm["url"]}')
    return "\n".join(lines) + ("\n" if lines else "")


def run_git(args: list, cwd: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        return result.returncode == 0, result.stdout + result.stderr
    except FileNotFoundError:
        return False, "git executable not found in PATH"


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class SetupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FusionFix Project Setup")
        self.resizable(True, True)
        self.minsize(720, 600)

        self._defaults = load_defaults()
        self._custom_submodules: list[dict] = []  # extra rows added in tab 2

        self._build_ui()
        self._load_defaults_into_ui()
        self.update_idletasks()
        # Center on screen
        w, h = 780, 680
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._tab_identity()
        self._tab_submodules()
        self._tab_build_ci()
        self._tab_extra()
        self._tab_emulators()

        # Bottom bar
        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.X, padx=8, pady=(0, 8))

        ttk.Button(bottom, text="Preview Changes", command=self._preview).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(bottom, text="Apply & Initialize", command=self._apply, style="Accent.TButton").pack(side=tk.RIGHT)

    # ---- Tab 1: Identity ------------------------------------------------

    def _tab_identity(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=" Project Identity ")

        frame.columnconfigure(1, weight=1)

        self.var_project_name  = tk.StringVar()
        self.var_repo_url      = tk.StringVar()
        self.var_license       = tk.StringVar()
        self.var_arch          = tk.StringVar()
        self.var_output        = tk.StringVar()
        self.var_branch        = tk.StringVar()

        ttk.Entry(frame, textvariable=self.var_project_name).grid(row=0, column=1, sticky=tk.EW, pady=4)
        ttk.Label(frame, text="Project name").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 10))

        ttk.Label(frame, text="GitHub repository URL").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        ttk.Entry(frame, textvariable=self.var_repo_url).grid(row=1, column=1, sticky=tk.EW, pady=4)

        ttk.Label(frame, text="License (SPDX)").grid(row=2, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        ttk.Combobox(frame, textvariable=self.var_license,
                     values=list(LICENSE_TEXTS.keys()), state="readonly").grid(row=2, column=1, sticky=tk.EW, pady=4)

        ttk.Label(frame, text="Default branch").grid(row=3, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        ttk.Combobox(frame, textvariable=self.var_branch,
                     values=["main", "master"], state="readonly").grid(row=3, column=1, sticky=tk.EW, pady=4)

        ttk.Label(frame, text="Windows architecture").grid(row=4, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.arch_combo = ttk.Combobox(frame, textvariable=self.var_arch,
                     values=list(ARCH_PRESETS.keys()), state="readonly")
        self.arch_combo.grid(row=4, column=1, sticky=tk.EW, pady=4)

        ttk.Label(frame, text="Windows output type").grid(row=5, column=0, sticky=tk.W, pady=4, padx=(0, 10))
        self.output_combo = ttk.Combobox(frame, textvariable=self.var_output,
                     values=list(OUTPUT_PRESETS.keys()), state="readonly")
        self.output_combo.grid(row=5, column=1, sticky=tk.EW, pady=4)

        note = ttk.Label(frame,
            text="Tip: repository path is auto-derived from URL for CI release conditions.",
            wraplength=480, foreground="gray")
        note.grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))

    # ---- Tab 2: Submodules ----------------------------------------------

    def _tab_submodules(self):
        outer = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(outer, text=" Submodules ")

        ttk.Label(outer, text="Select submodules to include in external/:",
                  font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))

        self._sm_vars: dict[str, dict] = {}

        grid = ttk.Frame(outer)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(2, weight=2)

        ttk.Label(grid, text="Enable", font=("", 9, "bold")).grid(row=0, column=0, padx=4)
        ttk.Label(grid, text="Path in repo", font=("", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Label(grid, text="Remote URL", font=("", 9, "bold")).grid(row=0, column=2, sticky=tk.W, padx=4)

        for i, (name, path, url) in enumerate(WELL_KNOWN_SUBMODULES, start=1):
            enabled = tk.BooleanVar(value=(name in DEFAULT_ENABLED))
            path_var = tk.StringVar(value=path)
            url_var = tk.StringVar(value=url)
            self._sm_vars[name] = {"enabled": enabled, "path": path_var, "url": url_var}

            ttk.Checkbutton(grid, variable=enabled).grid(row=i, column=0, padx=4)
            ttk.Entry(grid, textvariable=path_var, width=28).grid(row=i, column=1, sticky=tk.EW, padx=4, pady=2)
            ttk.Entry(grid, textvariable=url_var).grid(row=i, column=2, sticky=tk.EW, padx=4, pady=2)

        # plugin-sdk game selection (shown inline, below the submodule grid)
        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        sdk_frame = ttk.LabelFrame(outer, text="plugin-sdk game target", padding=8)
        sdk_frame.pack(fill=tk.X, pady=(0, 6))
        sdk_frame.columnconfigure(1, weight=1)

        self.var_plugin_sdk_game = tk.StringVar()
        game_labels = [g[0] for g in PLUGIN_SDK_GAMES]
        self.var_plugin_sdk_game.set(game_labels[0])

        ttk.Label(sdk_frame, text="Target game:").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        game_combo = ttk.Combobox(sdk_frame, textvariable=self.var_plugin_sdk_game,
                                  values=game_labels, state="readonly", width=40)
        game_combo.grid(row=0, column=1, sticky=tk.EW)

        note = ttk.Label(sdk_frame,
            text="Only relevant when 'plugin-sdk' is enabled above. "
                 "Determines which game headers are compiled and which preprocessor defines are set.",
            wraplength=480, foreground="gray")
        note.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        ttk.Separator(outer, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(outer, text="Custom submodules:", font=("", 10, "bold")).pack(anchor=tk.W)

        self._custom_sm_frame = ttk.Frame(outer)
        self._custom_sm_frame.pack(fill=tk.X)
        self._custom_sm_frame.columnconfigure(1, weight=1)
        self._custom_sm_frame.columnconfigure(2, weight=2)

        self._custom_sm_rows: list[dict] = []
        ttk.Button(outer, text="+ Add Custom Submodule", command=self._add_custom_sm_row).pack(anchor=tk.W, pady=(6, 0))

    def _tab_emulators(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=" Target ")
        frame.columnconfigure(1, weight=1)
        fields = [("target", "Platform", "windows", ["windows", "psp", "pcsx2"]),
                  ("language", "Emulator source language", "C", ["C", "C++"]),
                  ("game_module", "PSP internal game module", "", None),
                  ("disc_ids", "PSP disc IDs (comma separated)", "", None),
                  ("crcs", "PS2 game CRCs (comma separated)", "", None),
                  ("base", "PS2 load address", "0x02100000", None)]
        for row, (name, label, default, values) in enumerate(fields):
            var = tk.StringVar(value=self._defaults.get(name, default))
            setattr(self, "var_" + name, var)
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky=tk.W, padx=(0, 10), pady=5)
            widget = ttk.Combobox(frame, textvariable=var, values=values, state="readonly") if values else ttk.Entry(frame, textvariable=var)
            widget.grid(row=row, column=1, sticky=tk.EW, pady=5)
        ttk.Label(frame, wraplength=500, text="PSP and PS2 setup downloads helper sources from GitHub and always registers/initializes pspsdk or ps2sdk as a Git submodule. Windows dependencies, architecture, output format, signing and EmbedPDB do not apply. The local game path is the emulator directory.").grid(row=6, column=0, columnspan=2, pady=12)
        self.var_target.trace_add("write", lambda *_: self._target_changed())
        self._target_changed()

    def _target_changed(self):
        native = self.var_target.get() == "windows"
        self.notebook.tab(1, state="normal" if native else "disabled")
        for widget in [self.arch_combo, self.output_combo]:
            widget.configure(state="readonly" if native else "disabled")
        for widget in [self.signing_check, self.embpdb_check]:
            widget.configure(state="normal" if native else "disabled")

    def _add_custom_sm_row(self, path_val="", url_val=""):
        row_idx = len(self._custom_sm_rows)
        frame = self._custom_sm_frame
        path_var = tk.StringVar(value=path_val)
        url_var = tk.StringVar(value=url_val)

        enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, variable=enabled).grid(row=row_idx, column=0, padx=4)
        ttk.Entry(frame, textvariable=path_var, width=28).grid(
            row=row_idx, column=1, sticky=tk.EW, padx=4, pady=2)
        ttk.Entry(frame, textvariable=url_var).grid(
            row=row_idx, column=2, sticky=tk.EW, padx=4, pady=2)

        self._custom_sm_rows.append({"enabled": enabled, "path": path_var, "url": url_var})

    # ---- Tab 3: Build & CI ----------------------------------------------

    def _tab_build_ci(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=" Build & CI ")
        frame.columnconfigure(1, weight=1)

        self.var_premake_version  = tk.StringVar()
        self.var_game_path        = tk.StringVar()
        self.var_game_exe         = tk.StringVar()
        self.var_steam_app_id     = tk.StringVar()
        self.var_script_subdir    = tk.StringVar(value="plugins/")
        self.var_run_git_sm       = tk.BooleanVar(value=True)
        self.var_run_commit       = tk.BooleanVar(value=True)
        self.var_enable_signing   = tk.BooleanVar(value=False)

        entries = [
            ("Premake VS target",          self.var_premake_version, "combobox"),
            ("Game install path (local)", self.var_game_path, "entry"),
            ("Game executable (relative)", self.var_game_exe, "entry"),
            ("Steam App ID (Windows, optional)", self.var_steam_app_id, "entry"),
            ("Windows plugin subdirectory", self.var_script_subdir, "entry"),
        ]

        for i, (label, var, kind) in enumerate(entries):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=4, padx=(0, 10))
            if kind == "combobox":
                ttk.Combobox(frame, textvariable=var, values=PREMAKE_VERSIONS,
                             state="readonly").grid(row=i, column=1, sticky=tk.EW, pady=4)
            else:
                ttk.Entry(frame, textvariable=var).grid(row=i, column=1, sticky=tk.EW, pady=4)

        checks = [
            ("Run `git submodule add` for each selected submodule", self.var_run_git_sm),
            ("Create initial git commit after applying changes",     self.var_run_commit),
            ("Enable code signing step in CI & release.bat",        self.var_enable_signing),
        ]
        for i, (label, var) in enumerate(checks, start=len(entries) + 1):
            check = ttk.Checkbutton(frame, text=label, variable=var)
            check.grid(row=i, column=0, columnspan=2, sticky=tk.W, pady=4)
            if var is self.var_enable_signing:
                self.signing_check = check

        note = ttk.Label(frame,
            text="Game install path is saved in the git-ignored .env file for local debugging "
                 "(copy-on-build). It is NOT committed to the repository.",
            wraplength=480, foreground="gray")
        note.grid(row=len(entries) + len(checks) + 2, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))

    # ---- Tab 4: Extra Assets --------------------------------------------

    def _tab_extra(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(frame, text=" Extra Assets ")

        self.var_has_textures = tk.BooleanVar(value=False)
        self.var_has_embpdb   = tk.BooleanVar(value=True)

        ttk.Label(frame, text="Include skeleton directories in the project:",
                  font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 8))
        ttk.Checkbutton(frame, text="textures/ folder", variable=self.var_has_textures).pack(anchor=tk.W)
        self.embpdb_check = ttk.Checkbutton(frame, text="tools/EmbedPDB/ (PDB embedding helper)", variable=self.var_has_embpdb)
        self.embpdb_check.pack(anchor=tk.W)

        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=12)
        ttk.Label(frame, text="Additional paths to include in release.bat 7z command (one per line):",
                  font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))
        self.extra_paths_text = scrolledtext.ScrolledText(frame, height=6, width=60)
        self.extra_paths_text.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------
    # Load defaults
    # ------------------------------------------------------------------

    def _load_defaults_into_ui(self):
        d = self._defaults

        self.var_project_name.set(d.get("project_name", "GameName.FusionFix"))
        self.var_repo_url.set(d.get("repo_url", "https://github.com/Fusion-Fix/GameName.FusionFix"))
        self.var_branch.set(d.get("default_branch", "main"))
        self.var_premake_version.set(d.get("premake_vs_version", "vs2026"))
        self.var_run_git_sm.set(d.get("run_git_submodule_add", True))
        self.var_run_commit.set(d.get("run_initial_commit", True))
        self.var_enable_signing.set(d.get("enable_code_signing", False))
        self.var_game_exe.set(d.get("game_executable", ""))
        self.var_steam_app_id.set(d.get("steam_app_id", ""))

        license_spdx = d.get("license_spdx", "MIT")
        self.var_license.set(license_spdx if license_spdx in LICENSE_TEXTS else "MIT")

        arch = d.get("architecture", "x64")
        self.var_arch.set(_arch_label(arch))

        kind = d.get("output_kind", "SharedLib")
        ext  = d.get("target_extension", ".asi")
        self.var_output.set(_output_label(kind, ext))

        # Submodules
        for sm in d.get("submodules", []):
            name = sm.get("name", "")
            if name in self._sm_vars:
                self._sm_vars[name]["enabled"].set(sm.get("enabled", False))
                self._sm_vars[name]["path"].set(sm.get("path", self._sm_vars[name]["path"].get()))
                self._sm_vars[name]["url"].set(sm.get("url", self._sm_vars[name]["url"].get()))

        # plugin-sdk game target
        sdk_game = d.get("plugin_sdk_game", "")
        if sdk_game:
            game_labels = [g[0] for g in PLUGIN_SDK_GAMES]
            if sdk_game in game_labels:
                self.var_plugin_sdk_game.set(sdk_game)

    # ------------------------------------------------------------------
    # Collect values
    # ------------------------------------------------------------------

    def _collect(self) -> dict:
        arch_label = self.var_arch.get()
        arch, msbuild_platform, ual_tag, ual_filename = ARCH_PRESETS.get(
            arch_label, ("x64", "x64", "x64-latest", "dinput8-x64.zip"))

        output_label = self.var_output.get()
        output_kind, target_extension = OUTPUT_PRESETS.get(output_label, ("SharedLib", ".asi"))

        project_name  = self.var_project_name.get().strip()
        repo_url      = self.var_repo_url.get().strip().rstrip("/")
        github_repo   = _repo_path_from_url(repo_url)
        license_spdx  = LICENSE_TEXTS.get(self.var_license.get(), "MIT")
        default_branch = self.var_branch.get().strip() or "main"
        premake_ver   = self.var_premake_version.get().strip() or "vs2026"

        submodules = []
        for name, sm in self._sm_vars.items():
            if sm["enabled"].get():
                path = sm["path"].get().strip()
                url  = sm["url"].get().strip()
                if path and url:
                    submodules.append({"name": name, "path": path, "url": url})
        for row in self._custom_sm_rows:
            if row["enabled"].get():
                path = row["path"].get().strip()
                url  = row["url"].get().strip()
                if path and url:
                    name = path.split("/")[-1]
                    submodules.append({"name": name, "path": path, "url": url})

        tokens = {
            "PROJECT_NAME":    project_name,
            "REPO_URL":        repo_url,
            "GITHUB_REPO_PATH": github_repo,
            "LICENSE_SPDX":    license_spdx,
            "DEFAULT_BRANCH":  default_branch,
            "ARCHITECTURE":    arch,
            "MSBUILD_PLATFORM": msbuild_platform,
            "OUTPUT_KIND":     output_kind,
            "TARGET_EXTENSION": target_extension,
            "PREMAKE_VS_VERSION": premake_ver,
            "SOLUTION_EXTENSION": "slnx" if premake_ver == "vs2026" else "sln",
            "UAL_TAG":         ual_tag,
            "UAL_FILENAME":    ual_filename,
        }

        cfg = {
            "game_exe": self.var_game_exe.get().strip(),
            "steam_app_id": self.var_steam_app_id.get().strip(),
            "tokens": tokens,
            "submodules": submodules,
            "plugin_sdk_game": self.var_plugin_sdk_game.get(),
            "run_git_sm": self.var_run_git_sm.get(),
            "run_commit": self.var_run_commit.get(),
            "enable_signing": self.var_enable_signing.get(),
            "has_textures": self.var_has_textures.get(),
            "has_embpdb": self.var_has_embpdb.get(),
            "game_path": self.var_game_path.get().strip(),
            "script_subdir": self.var_script_subdir.get().strip(),
            "extra_paths": self.extra_paths_text.get("1.0", tk.END).strip(),
        }

        return setup_emulators.configure(cfg, self.var_target.get(), self.var_language.get(),
            self.var_game_module.get().strip(), self.var_disc_ids.get().strip(),
            self.var_crcs.get().strip(), self.var_base.get().strip())

    def _validate(self, cfg: dict) -> list[str]:
        errors = []
        t = cfg["tokens"]
        if not t["PROJECT_NAME"] or t["PROJECT_NAME"] == "GameName.FusionFix":
            errors.append("Please set a real project name.")
        if not t["REPO_URL"] or "GameName" in t["REPO_URL"]:
            errors.append("Please set a real GitHub repository URL.")
        if not t["GITHUB_REPO_PATH"] or "/" not in t["GITHUB_REPO_PATH"]:
            errors.append("Repository URL must be in https://github.com/<owner>/<repo> format.")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", t["PROJECT_NAME"]):
            errors.append("Project name must use letters, digits, dots, underscores or hyphens.")
        selected = {sm["name"] for sm in cfg["submodules"]}
        missing = DEFAULT_ENABLED - selected if cfg["target"] == "windows" else set()
        if missing:
            errors.append("Windows starter requires: " + ", ".join(sorted(missing)))
        if "plugin-sdk" in selected:
            sdk = next(g for g in PLUGIN_SDK_GAMES if g[0] == cfg["plugin_sdk_game"])
            expected = "x64" if sdk[5] == "x64" else "x86"
            if t["ARCHITECTURE"] != expected:
                errors.append(f"Selected plugin-sdk game requires {expected} architecture.")
        if cfg.get("steam_app_id") and not cfg["steam_app_id"].isdigit():
            errors.append("Steam App ID must contain digits only.")
        subdir = cfg["script_subdir"].replace("\\", "/")
        if subdir and (not re.fullmatch(r"[A-Za-z0-9_ ./-]+", subdir) or ".." in subdir.split("/") or subdir.startswith("/")):
            errors.append("Plugin subdirectory must be a relative folder within the game directory.")
        exe = cfg.get("game_exe", "")
        if any(c in exe for c in '\"\r\n'):
            errors.append("Executable path cannot contain quotes or newlines.")
        errors.extend(setup_emulators.validate(cfg))
        return errors

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _preview(self):
        cfg = self._collect()
        errors = self._validate(cfg)

        win = tk.Toplevel(self)
        win.title("Preview")
        win.geometry("700x520")
        txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, font=("Courier New", 9))
        txt.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        if errors:
            txt.insert(tk.END, "VALIDATION ERRORS:\n")
            for e in errors:
                txt.insert(tk.END, f"  • {e}\n")
            txt.insert(tk.END, "\n")

        t = cfg["tokens"]
        txt.insert(tk.END, "=== Token substitutions ===\n")
        for k, v in t.items():
            txt.insert(tk.END, f"  {{{{  {k}  }}}} → {v!r}\n")

        txt.insert(tk.END, "\n=== Files to process ===\n")
        for rel in TEMPLATE_FILES:
            p = SCRIPT_DIR / rel
            txt.insert(tk.END, f"  {'EXISTS' if p.exists() else 'MISSING'} {rel}\n")

        txt.insert(tk.END, "\n=== Submodules ===\n")
        for sm in cfg["submodules"]:
            txt.insert(tk.END, f"  {sm['path']} → {sm['url']}\n")
        if not cfg["submodules"]:
            txt.insert(tk.END, "  (none selected)\n")

        sdk_enabled = any(sm["name"] == "plugin-sdk" for sm in cfg["submodules"])
        if sdk_enabled:
            txt.insert(tk.END, f"\n=== plugin-sdk game target ===\n")
            txt.insert(tk.END, f"  {cfg.get('plugin_sdk_game', '(not set)')}\n")

        txt.insert(tk.END, "\n=== .gitmodules content ===\n")
        txt.insert(tk.END, build_gitmodules(cfg["submodules"]))

        txt.insert(tk.END, "\n=== premake5.lua submodule lines to inject ===\n")
        for sm in cfg["submodules"]:
            name = sm.get("name", "")
            path = sm.get("path", "")
            if name == "plugin-sdk":
                txt.insert(tk.END, f"  -- plugin-sdk (game: {cfg.get('plugin_sdk_game', '?')})\n")
                game_label = cfg.get("plugin_sdk_game", "")
                game_info = next((g for g in PLUGIN_SDK_GAMES if g[0] == game_label), None)
                if game_info:
                    _, plugin_folder, game_folder, game_def, extra_defs, _ = game_info
                    lib_name = plugin_folder
                    all_defs = [game_def] + extra_defs
                    txt.insert(tk.END, f'    defines {{ {", ".join(repr(d) for d in all_defs)} }}\n')
                    txt.insert(tk.END, f'    includedirs {{ "{path}/{plugin_folder}", "{path}/shared", ... }}\n')
                    txt.insert(tk.END, f'    libdirs {{ "{path}/output/lib" }}\n')
                    txt.insert(tk.END, f'    links {{ "{lib_name}" }} (Release) / "{lib_name}_d" (Debug)\n')
                    txt.insert(tk.END, f'    [sub-project] build plugin-sdk as StaticLib\n')
            elif cfg["target"] == "windows":
                snippets = SUBMODULE_PREMAKE.get(name)
                if snippets:
                    txt.insert(tk.END, f"  -- {name}\n")
                    for s in snippets:
                        txt.insert(tk.END, f"  {s.format(path=path)}\n")
                else:
                    txt.insert(tk.END, f"  -- {name} (custom)\n")
                    txt.insert(tk.END, f'  includedirs {{ "{path}" }}\n')
        if not cfg["submodules"]:
            txt.insert(tk.END, "  (none)\n")

        txt.insert(tk.END, "\n=== Actions ===\n")
        txt.insert(tk.END, f"  Substitute tokens in {len(TEMPLATE_FILES)} files\n")
        if cfg["target"] == "windows":
            txt.insert(tk.END, "  Configure native dependencies, debugger and CI plugin-sdk steps\n")
        else:
            txt.insert(tk.END, f"  Generate {cfg['target']} {cfg['language']} starter and build scripts\n")
            txt.insert(tk.END, f"  Download helpers from {setup_emulators.BASE_URL}\n")
            for source in setup_emulators.manifest(cfg["target"]).values():
                txt.insert(tk.END, f"    {source}\n")
        txt.insert(tk.END, f"  Write .gitmodules\n")
        if cfg["game_path"]:
            txt.insert(tk.END, f"  Save {t.get('EMULATOR_ENV_KEY', 'GAME_DIR')} in the git-ignored .env file\n")
        if cfg["run_git_sm"] and cfg["submodules"]:
            txt.insert(tk.END, f"  Run `git submodule add` for {len(cfg['submodules'])} submodule(s)\n")
        if not cfg["enable_signing"]:
            txt.insert(tk.END, "  Strip code signing from release.bat and CI workflow\n")
        if cfg["has_textures"]:
            txt.insert(tk.END, "  Create textures/.gitkeep\n")
        if cfg["run_commit"]:
            txt.insert(tk.END, "  Run: git add -A && git commit -m 'Initial project setup: <name>'\n")
        txt.insert(tk.END, "  Delete setup.py and template.json\n")

        txt.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Apply
    # ------------------------------------------------------------------

    def _apply(self):
        cfg = self._collect()
        errors = self._validate(cfg)
        if errors:
            messagebox.showerror("Validation", "\n".join(errors))
            return

        if not messagebox.askyesno(
            "Confirm",
            "This will modify files across the repository, run git commands, "
            "and DELETE setup.py and template.json.\n\nContinue?"
        ):
            return

        log_win = tk.Toplevel(self)
        log_win.title("Applying changes…")
        log_win.geometry("680x440")
        log = scrolledtext.ScrolledText(log_win, wrap=tk.WORD, font=("Courier New", 9))
        log.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        log_win.update()

        def emit(msg: str):
            log.config(state=tk.NORMAL)
            log.insert(tk.END, msg + "\n")
            log.see(tk.END)
            log.config(state=tk.DISABLED)
            log_win.update()

        tokens = cfg["tokens"]

        try:
            downloads = None
            if cfg["target"] != "windows":
                downloads = setup_emulators.fetch(cfg["target"], emit)
                setup_emulators.initialize_sdk(SCRIPT_DIR, cfg, run_git, emit)
            # 1. Substitute template tokens.
            emit("→ Substituting tokens in template files…")
            for rel in TEMPLATE_FILES:
                p = SCRIPT_DIR / rel
                if p.exists():
                    substitute_file(p, tokens)
                    emit(f"  ✓ {rel}")
                else:
                    emit(f"  ⚠ SKIP (not found): {rel}")

            emit("→ Writing license file…")
            _write_license_file(SCRIPT_DIR / "license", tokens["LICENSE_SPDX"], emit)

            # 2. Inject submodule premake lines
            if cfg["target"] == "windows":
                configure_windows(SCRIPT_DIR, cfg)
                _inject_premake_submodules(SCRIPT_DIR / "premake5.lua", cfg["submodules"],
                                          cfg.get("plugin_sdk_game", ""), emit)
            else:
                setup_emulators.generate(SCRIPT_DIR, cfg, downloads)
            _configure_ci_submodules(SCRIPT_DIR / ".github/workflows/msvc.yml",
                                 cfg["submodules"], cfg.get("plugin_sdk_game", ""), emit)


            # 3. Handle code signing toggle
            if not cfg["enable_signing"]:
                emit("→ Stripping code signing calls…")
                _strip_signing(SCRIPT_DIR, emit)

            # 4. Store the local game path in .env
            if cfg["game_path"]:
                emit("→ Saving game path in .env…")
                _inject_game_path(SCRIPT_DIR / "premake5.lua", tokens["PROJECT_NAME"],
                                  cfg["game_path"], cfg["script_subdir"], emit,
                                  env_key=tokens.get("EMULATOR_ENV_KEY", "GAME_DIR"))

            # 5. Handle extra packaging paths in release.bat
            if cfg["extra_paths"]:
                emit("→ Injecting extra release paths…")
                _inject_release_extra_paths(SCRIPT_DIR / "release.bat", cfg["extra_paths"], emit)

            # 6. Extra asset directories
            if cfg["has_textures"]:
                tex_dir = SCRIPT_DIR / "textures"
                tex_dir.mkdir(exist_ok=True)
                (tex_dir / ".gitkeep").touch()
                emit("  ✓ Created textures/.gitkeep")

            if not cfg["has_embpdb"]:
                embpdb_dir = SCRIPT_DIR / "tools" / "EmbedPDB"
                if embpdb_dir.exists():
                    shutil.rmtree(embpdb_dir)
                    # Remove tools/ if now empty
                    tools_dir = SCRIPT_DIR / "tools"
                    if tools_dir.exists() and not any(tools_dir.iterdir()):
                        tools_dir.rmdir()
                    emit("  ✓ Removed tools/EmbedPDB/")

            # 7. Write .gitmodules
            emit("→ Writing .gitmodules…")
            gitmodules_path = SCRIPT_DIR / ".gitmodules"
            gitmodules_path.write_text(build_gitmodules(cfg["submodules"]), encoding="utf-8")
            emit("  ✓ .gitmodules written")

            # 8. git submodule add
            if cfg["target"] == "windows" and cfg["run_git_sm"] and cfg["submodules"]:
                emit("→ Running git submodule add…")
                for sm in cfg["submodules"]:
                    ok, out = run_git(["submodule", "add", sm["url"], sm["path"]], SCRIPT_DIR)
                    status = "✓" if ok else "⚠"
                    emit(f"  {status} {sm['path']}: {out.strip() or 'done'}")

                emit("→ Initializing submodules recursively…")
                ok, out = run_git(["submodule", "update", "--init", "--recursive"], SCRIPT_DIR)
                emit(f"  {'✓' if ok else '⚠'} submodule update: {out.strip() or 'done'}")

            # 9. git add + commit
            if cfg["run_commit"]:
                emit("→ Staging and committing…")
                # Delete this script and template.json before committing
                _self_delete(SCRIPT_DIR, emit, deferred=False)
                ok, out = run_git(["add", "-A"], SCRIPT_DIR)
                emit(f"  {'✓' if ok else '⚠'} git add -A: {out.strip()}")
                commit_msg = f"Initial project setup: {tokens['PROJECT_NAME']}"
                ok, out = run_git(["commit", "-m", commit_msg], SCRIPT_DIR)
                emit(f"  {'✓' if ok else '⚠'} git commit: {out.strip()}")
            else:
                _self_delete(SCRIPT_DIR, emit, deferred=False)

            emit("\n✅ Done! You can now open premake5.bat to generate the Visual Studio solution.")

        except Exception as exc:
            emit(f"\n❌ ERROR: {exc}")
            import traceback
            emit(traceback.format_exc())
            return

        ttk.Button(log_win, text="Close", command=log_win.destroy).pack(pady=6)
        self.after(500, self.destroy)


# ---------------------------------------------------------------------------
# Helper functions used during apply
# ---------------------------------------------------------------------------

def _write_license_file(license_path: Path, license_spdx: str, emit):
    template = LICENSE_FILE_CONTENT.get(license_spdx)
    if template is None:
        emit(f"  ⚠ Unknown license '{license_spdx}', keeping existing license file")
        return
    content = template.replace("{{YEAR}}", "2026").replace("{{AUTHOR}}", "Fusion Fix contributors")
    license_path.write_text(content, encoding="utf-8")
    emit(f"  ✓ license file written ({license_spdx})")

def _inject_release_extra_paths(release_bat: Path, raw_paths: str, emit):
    if not release_bat.exists():
        emit("  ⚠ release.bat not found, skipping extra release paths")
        return

    extra_paths = [line.strip() for line in raw_paths.splitlines() if line.strip()]
    if not extra_paths:
        return

    text = release_bat.read_text(encoding="utf-8")
    # Match after token substitution, for native and emulator release scripts alike.
    match = re.search(r'^7z a [^\n]+', text, re.MULTILINE)
    if match is None:
        emit("  Could not find 7z command, skipping extra release paths")
        return
    additions = " ".join(f'"{p}"' for p in extra_paths)
    command = match.group(0)
    if command.endswith("^"):
        command = command[:-1] + additions + " ^"
    else:
        command += " " + additions
    text = text[:match.start()] + command + text[match.end():]
    release_bat.write_text(text, encoding="utf-8")
    emit(f"  ✓ Added {len(extra_paths)} extra path(s) to release.bat")

def _inject_premake_submodules(premake_lua: Path, submodules: list, plugin_sdk_game: str, emit):
    """Replace the sentinel block in premake5.lua with real includedirs/files lines."""
    if not premake_lua.exists():
        emit("  ⚠ premake5.lua not found, skipping submodule injection")
        return

    text = premake_lua.read_text(encoding="utf-8")

    BEGIN_SENTINEL = "   -- ##BEGIN_EXTERNAL_SUBMODULES##"
    END_SENTINEL   = "   -- ##END_EXTERNAL_SUBMODULES##"

    begin_idx = text.find(BEGIN_SENTINEL)
    end_idx   = text.find(END_SENTINEL)

    if begin_idx == -1 or end_idx == -1:
        emit("  ⚠ Sentinel markers not found in premake5.lua, skipping")
        return

    # Build replacement lines
    generated_lines = []
    sdk_project_lines = []  # appended after workspace block, outside the sentinel

    for sm in submodules:
        name = sm.get("name", "")
        path = sm.get("path", "")

        if name == "plugin-sdk":
            game_info = next((g for g in PLUGIN_SDK_GAMES if g[0] == plugin_sdk_game), None)
            if game_info is None and PLUGIN_SDK_GAMES:
                game_info = PLUGIN_SDK_GAMES[0]
            if game_info:
                _, plugin_folder, game_folder, game_def, extra_defs, sdk_arch = game_info
                lib_name = plugin_folder
                all_defs = [game_def] + extra_defs

                # Lines inside the workspace (consumed by the main project)
                generated_lines.append(f'   -- plugin-sdk ({game_info[0]})')
                for d in all_defs:
                    generated_lines.append(f'   defines {{ "{d}" }}')
                generated_lines.append(f'   includedirs {{ "{path}/{plugin_folder}" }}')
                generated_lines.append(f'   includedirs {{ "{path}/{plugin_folder}/{game_folder}" }}')
                generated_lines.append(f'   includedirs {{ "{path}/{plugin_folder}/{game_folder}/enums" }}')
                generated_lines.append(f'   includedirs {{ "{path}/{plugin_folder}/{game_folder}/rw" }}')
                generated_lines.append(f'   includedirs {{ "{path}/shared" }}')
                generated_lines.append(f'   includedirs {{ "{path}/shared/game" }}')
                generated_lines.append(f'   libdirs {{ "{path}/output/lib" }}')
                generated_lines.append(f'   filter "configurations:Release"')
                generated_lines.append(f'      links {{ "{lib_name}" }}')
                generated_lines.append(f'   filter "configurations:Debug"')
                generated_lines.append(f'      links {{ "{lib_name}_d" }}')
                generated_lines.append(f'   filter {{}}')

                # Sub-project block that builds the SDK static lib
                sdk_arch_str = '"x64"' if sdk_arch == "x64" else '"x86"'
                sdk_project_lines += [
                    f'',
                    f'project "{lib_name}"',
                    f'   kind "StaticLib"',
                    f'   language "C++"',
                    f'   cppdialect "C++latest"',
                    f'   architecture {sdk_arch_str}',
                    f'   characterset "MBCS"',
                    f'   staticruntime "On"',
                    f'   multiprocessorcompile "On"',
                    f'   buildoptions {{ "/sdl-", "/std:c++latest" }}',
                    f'   disablewarnings {{ "4073", "4244", "4267" }}',
                    f'   defines {{ "_CRT_SECURE_NO_WARNINGS", "_CRT_NON_CONFORMING_SWPRINTFS"',
                    f'      , "_SILENCE_CXX17_CODECVT_HEADER_DEPRECATION_WARNING"',
                ]
                for d in all_defs:
                    sdk_project_lines.append(f'      , "{d}"')
                sdk_project_lines += [
                    f'   }}',
                    f'   includedirs {{',
                    f'      "{path}/{plugin_folder}"',
                    f'      , "{path}/{plugin_folder}/{game_folder}"',
                    f'      , "{path}/{plugin_folder}/{game_folder}/enums"',
                    f'      , "{path}/{plugin_folder}/{game_folder}/rw"',
                    f'      , "{path}/shared"',
                    f'      , "{path}/shared/game"',
                    f'      , "{path}/safetyhook"',
                    f'   }}',
                    f'   files {{',
                    f'      "{path}/{plugin_folder}/**.h"',
                    f'      , "{path}/{plugin_folder}/**.cpp"',
                    f'      , "{path}/shared/**.h"',
                    f'      , "{path}/shared/**.cpp"',
                    f'      , "{path}/hooking/**.cpp"',
                    f'      , "{path}/hooking/**.h"',
                    f'      , "{path}/injector/**.hpp"',
                    f'      , "{path}/safetyhook/safetyhook.cpp"',
                    f'      , "{path}/safetyhook/safetyhook.hpp"',
                    f'      , "{path}/safetyhook/Zydis.c"',
                    f'      , "{path}/safetyhook/Zydis.h"',
                    f'   }}',
                    f'   targetdir "{path}/output/lib"',
                    f'   filter "configurations:Release"',
                    f'      objdir "!{path}/output/obj/%{{prj.name}}/Release"',
                    f'      targetname "{lib_name}"',
                    f'      optimize "On"',
                    f'   filter "configurations:Debug"',
                    f'      objdir "!{path}/output/obj/%{{prj.name}}/Debug"',
                    f'      targetname "{lib_name}_d"',
                    f'      symbols "On"',
                    f'      defines "DEBUG"',
                    f'   filter {{}}',
                ]
        else:
            snippets = SUBMODULE_PREMAKE.get(name)
            if snippets:
                generated_lines.append(f"   -- {name}")
                for snippet in snippets:
                    generated_lines.append("   " + snippet.format(path=path))
            else:
                # Unknown submodule — emit a generic includedirs guess
                generated_lines.append(f"   -- {name} (custom)")
                generated_lines.append(f'   includedirs {{ "{path}" }}')

    if generated_lines:
        block = "\n".join(generated_lines)
    else:
        block = "   -- (no external submodules selected)"

    # Replace everything from BEGIN sentinel line through END sentinel line
    end_line_end = text.find("\n", end_idx)
    if end_line_end == -1:
        end_line_end = len(text)
    else:
        end_line_end += 1  # include the newline

    new_text = text[:begin_idx] + block + "\n" + text[end_line_end:]

    # Append the plugin-sdk sub-project after the last line of the file
    if sdk_project_lines:
        new_text = new_text.rstrip("\n") + "\n\n" + "\n".join(sdk_project_lines) + "\n"

    premake_lua.write_text(new_text, encoding="utf-8")
    count = len(generated_lines)
    emit(f"  ✓ Injected {count} premake line(s) for {len(submodules)} submodule(s)")
    if sdk_project_lines:
        emit(f"  ✓ Added plugin-sdk StaticLib sub-project")

def _configure_ci_submodules(workflow: Path, submodules: list, plugin_sdk_game: str, emit):
    """Keep SDK CI steps only for a selected SDK, using its path and game target."""
    if not workflow.exists():
        return
    text = workflow.read_text(encoding="utf-8")
    block = re.search(
        r"^    # ##BEGIN_PLUGIN_SDK##[^\n]*\n(.*?)"
        r"^    # ##END_PLUGIN_SDK##[^\n]*(?:\n|$)", text, re.MULTILINE | re.DOTALL,
    )
    if block is None:
        emit("  ⚠ Plugin-sdk CI markers not found, skipping")
        return
    sdk = next((sm for sm in submodules if sm.get("name") == "plugin-sdk"), None)
    replacement = ""
    if sdk:
        game = next((g for g in PLUGIN_SDK_GAMES if g[0] == plugin_sdk_game), PLUGIN_SDK_GAMES[0])
        replacement = block.group(1)
        values = {
            "PLUGIN_SDK_PATH": sdk["path"].replace("\\", "/").rstrip("/").replace("'", "''"),
            "PLUGIN_SDK_TARGET": game[1],
            "PLUGIN_SDK_PLATFORM": "x64" if game[5] == "x64" else "Win32",
        }
        for key, value in values.items():
            replacement = replacement.replace("{{" + key + "}}", value)
    workflow.write_text(text[:block.start()] + replacement + text[block.end():], encoding="utf-8")
    emit("  ✓ Configured plugin-sdk CI steps" if sdk else "  ✓ Removed plugin-sdk CI steps")


def configure_windows(root: Path, cfg):
    """Apply debugger and packaging choices even without a local install path."""
    exe = json.dumps(cfg.get("game_exe", "").replace("\\", "/"), ensure_ascii=False)
    subdir = cfg.get("script_subdir", "").replace("\\", "/").strip("/") or "plugins"
    lua = root / "premake5.lua"
    text = lua.read_text(encoding="utf-8")
    text = text.replace('setpaths("GAME_DIR", nil, "plugins/")', f'setpaths("GAME_DIR", {exe}, {json.dumps(subdir)})')
    steam = cfg.get("steam_app_id", "")
    if steam:
        text += f'\n   debugenvs {{ "SteamAppId={steam}", "SteamGameId={steam}" }}\n'
    lua.write_text(text, encoding="utf-8")
    release = root / "release.bat"
    text = release.read_text(encoding="utf-8")
    if not cfg.get("has_embpdb", True):
        text = re.sub(r"^.*EmbedPDB.*\n(?:if errorlevel 1 exit /b %errorlevel%\n)?", "", text, flags=re.M)
    text = text.replace("data\\plugins\\", "data\\" + subdir.replace("/", "\\") + "\\")
    release.write_text(text, encoding="utf-8")
    (root / "data" / subdir).mkdir(parents=True, exist_ok=True)


def _strip_signing(root: Path, emit):
    """Remove code-signing lines from release.bat and the CI workflow."""
    release_bat = root / "release.bat"
    if release_bat.exists():
        text = release_bat.read_text(encoding="utf-8")
        text = re.sub(r"^.*sign\.ps1.*\n(?:if errorlevel 1 exit /b %errorlevel%\n)?", "", text, flags=re.M | re.I)
        release_bat.write_text(text, encoding="utf-8")
        emit("  ✓ Removed sign.ps1 call from release.bat")

    workflow = root / ".github" / "workflows" / "msvc.yml"
    if workflow.exists():
        text = workflow.read_text(encoding="utf-8")
        # Remove the code-signing `env:` block from the "Pack binaries" step.
        # It only ever contains CODE_SIGNING_* vars, so drop the `env:` key
        # along with its entries (a dangling `env:` would be invalid YAML).
        text = re.sub(
            r"[ \t]*env:[ \t]*\r?\n"
            r"(?:[ \t]*CODE_SIGNING_[A-Z_]+:.*\r?\n)+",
            "",
            text,
        )
        workflow.write_text(text, encoding="utf-8")
        emit("  ✓ Removed signing env vars from CI workflow")


def _inject_game_path(premake_lua: Path, project_name: str, game_path: str, script_subdir: str, emit, env_key="GAME_DIR"):
    """Save the machine-specific path in .env and configure the plugin subdirectory."""
    if not premake_lua.exists():
        return
    env_file = premake_lua.parent / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    lines = [line for line in lines if not re.match(r"^\s*" + re.escape(env_key) + r"\s*=", line)]
    lines.append(f"{env_key}={game_path}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    text = premake_lua.read_text(encoding="utf-8")
    old = '   setpaths("GAME_DIR", nil, "plugins/")'
    subdir = json.dumps(script_subdir.replace("\\", "/") or "plugins/", ensure_ascii=False)
    text = text.replace(old, f'   setpaths("GAME_DIR", nil, {subdir})')
    premake_lua.write_text(text, encoding="utf-8")
    emit(f"  Local install path saved as {env_key} in .env")


def _self_delete(root: Path, emit, deferred: bool = True):
    setup_py = root / "setup.py"
    template_json = root / "template.json"
    # Only remove template-owned resources within this project.
    for rel in ["setup_emulators.py"]:
        target = (root / rel).resolve()
        if root.resolve() not in target.parents:
            raise ValueError("Template cleanup path escaped the project")
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    if setup_py.exists():
        try:
            setup_py.unlink()
            emit("  ✓ Deleted setup.py")
        except Exception as e:
            emit(f"  ⚠ Could not delete setup.py: {e}")

    if template_json.exists():
        try:
            template_json.unlink()
            emit("  ✓ Deleted template.json")
        except Exception as e:
            emit(f"  ⚠ Could not delete template.json: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = SetupApp()
    app.mainloop()
