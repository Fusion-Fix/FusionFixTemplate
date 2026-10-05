"""
FusionFix Project Setup Wizard
================================
Run this script once after cloning FusionFixTemplate to configure your new project.
It will substitute all {{TOKEN}} placeholders across the repository, manage git
submodules, and optionally make an initial commit.

After applying changes this script deletes itself.

Requirements: Python 3.9+ and a modern web browser. The GUI runs locally.
"""

import json
import os
import setup_emulators
from setup_licenses import LICENSES
import re
import shutil
import subprocess
from pathlib import Path

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

LICENSE_TEXTS = {spdx: spdx for spdx in LICENSES}

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
# Configuration and generation
# ---------------------------------------------------------------------------

def configuration(values: dict) -> dict:
    """Translate the GUI form into generator configuration."""
    defaults = load_defaults()
    def value(name, default=""):
        return str(values.get(name, default)).strip()
    target = value("target", "windows")
    if target not in {"windows", "psp", "pcsx2"}:
        raise ValueError("Choose Windows ASI, PSP PRX, or PCSX2F ELF.")
    language = value("language", "C")
    if language not in {"C", "C++"}:
        raise ValueError("Choose C or C++.")
    arch = value("architecture", defaults.get("architecture", "x64"))
    if arch not in {"x86", "x64"}:
        raise ValueError("Choose x86 or x64.")
    _, platform, ual_tag, ual_filename = ARCH_PRESETS[_arch_label(arch)]
    vs = value("premake_version", defaults.get("premake_vs_version", "vs2026"))
    if vs not in PREMAKE_VERSIONS:
        raise ValueError("Choose a supported Visual Studio version.")
    license_name = value("license", defaults.get("license_spdx", "MIT"))
    license_name = {"GPL-3.0 license": "GPL-3.0-only", "GPL-3.0": "GPL-3.0-only"}.get(license_name, license_name)
    if license_name not in LICENSE_TEXTS:
        raise ValueError("Choose a supported license.")
    repo = value("repo_url").rstrip("/")
    tokens = dict(PROJECT_NAME=value("project_name"), REPO_URL=repo,
                  GITHUB_REPO_PATH=_repo_path_from_url(repo), LICENSE_SPDX=LICENSE_TEXTS[license_name],
                  DEFAULT_BRANCH=value("branch", "main"), ARCHITECTURE=arch,
                  MSBUILD_PLATFORM=platform, OUTPUT_KIND="SharedLib", TARGET_EXTENSION=".asi",
                  PREMAKE_VS_VERSION=vs, SOLUTION_EXTENSION="slnx" if vs == "vs2026" else "sln",
                  UAL_TAG=ual_tag, UAL_FILENAME=ual_filename)
    submodules = []
    for sm in values.get("submodules", []):
        if sm.get("enabled", True):
            submodules.append({key: str(sm.get(key, "")).strip() for key in ("name", "path", "url")})
    cfg = dict(tokens=tokens, submodules=submodules,
               plugin_sdk_game=value("plugin_sdk_game", "GTA III"),
               game_exe=value("game_exe"), steam_app_id=value("steam_app_id"),
               game_path=value("game_path"), script_subdir=value("script_subdir", "plugins/"),
               extra_paths=value("extra_paths"))
    for name, default in [("run_git_sm", True), ("run_commit", True), ("enable_signing", False),
                          ("has_embpdb", True)]:
        cfg[name] = bool(values.get(name, default))
    return setup_emulators.configure(cfg, target, language, value("game_module"),
                                     value("disc_ids"), value("crcs"), "")


def validate_configuration(cfg: dict) -> list[str]:
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
        sdk = next((g for g in PLUGIN_SDK_GAMES if g[0] == cfg["plugin_sdk_game"]), None)
        if sdk is None:
            return errors + ["Choose a supported plugin-sdk game."]
        expected = "x64" if sdk[5] == "x64" else "x86"
        if t["ARCHITECTURE"] != expected:
            errors.append(f"Selected plugin-sdk game requires {expected} architecture.")
    if cfg.get("steam_app_id") and not cfg["steam_app_id"].isdigit():
        errors.append("Steam App ID must contain digits only.")
    subdir = cfg["script_subdir"].replace("\\", "/")
    if cfg["target"] == "windows" and subdir and (not re.fullmatch(r"[A-Za-z0-9_ ./-]+", subdir) or ".." in subdir.split("/") or subdir.startswith("/")):
        errors.append("Plugin subdirectory must be a relative folder within the game directory.")
    exe = cfg.get("game_exe", "")
    if any(c in exe for c in '\"\r\n'):
        errors.append("Executable path cannot contain quotes or newlines.")
    if not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", t["REPO_URL"]):
        errors.append("Enter a GitHub repository URL with an owner and repository name.")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", t["DEFAULT_BRANCH"]):
        errors.append("Default branch must use letters, numbers, dots, slashes, underscores or hyphens.")
    seen = set()
    for sm in cfg["submodules"]:
        path = sm["path"].replace("\\", "/")
        if not path.startswith("external/") or not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or any(part in {"", ".", ".."} for part in path.split("/")):
            errors.append("Submodule paths must be folders inside external/: " + sm["path"])
        if path.casefold() in seen:
            errors.append("Duplicate submodule path: " + path)
        seen.add(path.casefold())
        if not re.fullmatch(r"https://[^\s]+", sm["url"]):
            errors.append("Enter an HTTPS Git URL for " + sm["name"] + ".")
    errors.extend(setup_emulators.validate(cfg))
    return errors



def apply_configuration(cfg: dict, emit):
    """Apply a validated configuration. Runs on the local server worker thread."""
    tokens = cfg["tokens"]
    license_content = _license_content(tokens["LICENSE_SPDX"], emit, tokens["PROJECT_NAME"] + " contributors")
    downloads = None
    if cfg["target"] != "windows":
        downloads = setup_emulators.fetch(cfg["target"], emit)
        setup_emulators.initialize_sdk(SCRIPT_DIR, cfg, run_git, emit)
    elif cfg["run_git_sm"]:
        _initialize_submodules(SCRIPT_DIR, cfg["submodules"], emit)
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
    _write_license_file(SCRIPT_DIR / "license", tokens["LICENSE_SPDX"], emit, license_content)

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

    _remove_redundant_gitkeeps(SCRIPT_DIR, cfg["submodules"], emit)

    # 9. git add + commit
    if cfg["run_commit"]:
        emit("→ Staging and committing…")
        # Delete this script and template.json before committing
        _self_delete(SCRIPT_DIR, emit, deferred=False)
        ok, out = run_git(["add", "-A"], SCRIPT_DIR)
        if not ok:
            raise RuntimeError("Could not stage changes: " + out)
        commit_msg = f"Initial project setup: {tokens['PROJECT_NAME']}"
        ok, out = run_git(["commit", "-m", commit_msg], SCRIPT_DIR)
        if not ok:
            raise RuntimeError("Project files are ready, but Git commit failed: " + out)
        emit(out.strip())
    else:
        _self_delete(SCRIPT_DIR, emit, deferred=False)

    emit("\n✅ Done! You can now open premake5.bat to generate the Visual Studio solution.")



# ---------------------------------------------------------------------------
# Helper functions used during apply
# ---------------------------------------------------------------------------

def _initialize_submodules(root: Path, submodules: list, emit):
    for sm in submodules:
        emit("Initializing " + sm["name"] + "…")
        ok, out = run_git(["ls-files", "--stage", "--", sm["path"]], root)
        if not ok:
            raise RuntimeError(out)
        if not out.startswith("160000 "):
            ok, out = run_git(["submodule", "add", "--", sm["url"], sm["path"]], root)
            if not ok:
                raise RuntimeError("Could not add " + sm["name"] + ": " + out)
        ok, out = run_git(["submodule", "update", "--init", "--recursive", "--", sm["path"]], root)
        if not ok:
            raise RuntimeError("Could not initialize " + sm["name"] + ": " + out)


def _remove_redundant_gitkeeps(root: Path, submodules: list, emit):
    excluded = {str((root / sm["path"]).resolve()).casefold() for sm in submodules}
    for current, directories, filenames in os.walk(root, followlinks=False):
        folder = Path(current)
        directories[:] = [name for name in directories
                          if name not in {".git", "build", "__pycache__"}
                          and not (folder / name).is_symlink()
                          and not (getattr(folder / name, "is_junction", lambda: False)())
                          and str((folder / name).resolve()).casefold() not in excluded
                          and not (folder / name / ".git").exists()]
        if ".gitkeep" in filenames and any(child.name != ".gitkeep" for child in folder.iterdir()):
            (folder / ".gitkeep").unlink()
            emit("  Removed redundant " + str((folder / ".gitkeep").relative_to(root)))


def _license_content(license_spdx: str, emit, holder="Fusion Fix contributors"):
    from datetime import date
    license_info = LICENSES.get(license_spdx)
    if license_info is None:
        raise ValueError("Unsupported license: " + license_spdx)
    text = license_info["body"]
    year = str(date.today().year)
    for placeholder in ("[year]", "[yyyy]"):
        text = text.replace(placeholder, year)
    for placeholder in ("[fullname]", "[name of copyright owner]"):
        text = text.replace(placeholder, holder)
    if license_spdx.endswith(("-only", "-or-later")):
        choice = "This project is licensed under " + license_info["name"]
        choice += " only." if license_spdx.endswith("-only") else "."
        text = "SPDX-License-Identifier: " + license_spdx + "\n\n" + choice + "\n\n" + text
    return text


def _write_license_file(license_path: Path, license_spdx: str, emit, content=None):
    if content is None:
        content = _license_content(license_spdx, emit)
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
    for rel in ["setup_emulators.py", "setup_ui.py", "setup_licenses.py"]:
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
    import setup_ui
    setup_ui.launch(SCRIPT_DIR, load_defaults(), configuration, validate_configuration, apply_configuration,
                    WELL_KNOWN_SUBMODULES, DEFAULT_ENABLED, PLUGIN_SDK_GAMES, LICENSE_TEXTS, PREMAKE_VERSIONS)
