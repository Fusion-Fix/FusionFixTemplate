"""Emulator setup: generated build files and GitHub helper downloads."""
import re
from urllib.request import urlopen

REVISION = "dd22c3ad31c1f796f7bbc1e1dc06b2d88e5336f5"
BASE_URL = "https://raw.githubusercontent.com/ThirteenAG/WidescreenFixesPack/" + REVISION + "/"

TEMPLATES = {
    'emulator/build-plugin.ps1': r"""param([switch]$Clean)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$wrapper = Join-Path $root '{{SDK_WRAPPER}}'
if (-not (Test-Path -LiteralPath $wrapper)) {
    throw 'SDK missing. Run git submodule update --init --recursive.'
}
$outputDir = Join-Path $root 'data/{{PLUGIN_SUBDIR}}'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$makeArgs = @('-C', (Join-Path $root 'source'))
if ($Clean) { $makeArgs += 'clean' }
# Run in a child PowerShell: the SDK wrapper calls exit with make's result.
& powershell -NoProfile -ExecutionPolicy Bypass -File $wrapper @makeArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($Clean) { exit 0 }
$binary = Join-Path $outputDir '{{PROJECT_NAME}}{{TARGET_EXTENSION}}'
if (-not (Test-Path -LiteralPath $binary)) { throw "Build did not produce $binary" }

# Replace only a plugin the developer has already installed; preserve its INI.
$envFile = Join-Path $root '.env'
if (Test-Path -LiteralPath $envFile) {
    foreach ($line in Get-Content -LiteralPath $envFile) {
        if ($line -match '^\s*{{EMULATOR_ENV_KEY}}\s*=\s*(.*?)\s*$') {
            $install = $Matches[1].Trim('"', "'")
            if ($install) {
                $target = Join-Path $install '{{PLUGIN_SUBDIR}}/{{PROJECT_NAME}}{{TARGET_EXTENSION}}'
                if (Test-Path -LiteralPath $target) { Copy-Item -LiteralPath $binary -Destination $target -Force }
            }
        }
    }
}
""",
    'emulator/premake5.lua': r"""newoption { trigger = "with-version", value = "STRING", description = "Release version" }

workspace "{{PROJECT_NAME}}"
   configurations { "Release", "Debug" }
   platforms { "Win32" } -- Visual Studio makefile host; the SDK compiles MIPS code.
   location "build"
   startproject "{{PROJECT_NAME}}"

project "{{PROJECT_NAME}}"
   kind "Makefile"
   language "{{PLUGIN_LANGUAGE}}"
   cppdialect "C++17"
   targetdir "data/{{PLUGIN_SUBDIR}}"
   targetextension "{{TARGET_EXTENSION}}"
   files { "source/**.c", "source/**.cpp", "source/**.h", "source/**.hpp", "source/makefile", "source/linkfile", "source/exports.exp", "data/**.ini" }
   includedirs { "source/includes" }
   local command = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' .. path.getabsolute("build-plugin.ps1") .. '"'
   buildcommands { command }
   rebuildcommands { command .. ' -Clean', 'if errorlevel 1 exit /b %errorlevel%', command }
   cleancommands { command .. ' -Clean' }
   -- Build commands always exist, including on CI where .env is absent.
   local env = io.readfile(path.join(_SCRIPT_DIR, ".env")) or ""
   for line in env:gmatch("[^\r\n]+") do
      local key, value = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
      if key == "{{EMULATOR_ENV_KEY}}" and value ~= "" then
         value = value:gsub('^"', ''):gsub('"$', ''):gsub("^'", ''):gsub("'$", '')
         debugdir(value)
         debugcommand(path.join(value, "{{EMULATOR_EXE}}"))
      end
   end
""",
    'emulator/readme.md': r"""# {{PROJECT_NAME}}

A {{TARGET_PROFILE}} guest plugin. Implement the game-specific patches in `source/main.c`.

## Build

On Windows, initialize the toolchain submodule with `git submodule update --init --recursive`,
then run `powershell -NoProfile -ExecutionPolicy Bypass -File build-plugin.ps1`.
The SDK submodule contains the Windows MIPS toolchain used by WidescreenFixesPack.
Keep the checkout path free of spaces: the upstream SDK makefiles use unquoted paths.

Alternatively, run `premake5.bat` and open `build/{{PROJECT_NAME}}.{{SOLUTION_EXTENSION}}`.
Visual Studio invokes the same makefile build. Its Win32 platform is the build host,
not the architecture of the plugin. Release and Debug currently use the same SDK flags
and output. Use `build-plugin.ps1 -Clean` before changing flags.

Run `release.bat` to package `data/` and the helper licenses. CI builds and packages
the same output without requiring an emulator or a local `.env`.

## Install and debug

Extract the archive into the emulator directory. The plugin is placed at
`{{PLUGIN_SUBDIR}}/{{PROJECT_NAME}}{{TARGET_EXTENSION}}`.

For PSP, enable plugins in PPSSPP. `plugin.ini` restricts loading to your selected
disc IDs; `source/main.c` also checks the internal game module name. Verify both
against your game build. Real PSP hardware is not supported by this starter.

For PS2, use PCSX2F or PCSX2 with the compatible **PCSX2 Plugin Injector** installed.
The ELF is a guest EE plugin, not a desktop PCSX2 graphics/input plugin. Verify the
game CRCs and reserve the configured load address in the injector's extended memory.
Different plugins must not occupy overlapping memory. The starter performs no patches.

To replace an already installed binary after a build, create a git-ignored `.env`:

```dotenv
{{EMULATOR_ENV_KEY}}=C:/Emulators/MyEmulator
```

Quotes and trailing slashes are optional. The PSP layout assumes a portable PPSSPP
`memstick` directory; adjust `PLUGIN_SUBDIR` paths in the build script and package if
you use another memory-stick location. Regenerate the solution to update the debugger
path. The default executable is `{{EMULATOR_EXE}}`; select the game in the emulator.
Builds preserve the installed INI and only replace an existing plugin binary.

## Shared helpers

MIPS injection, patterns, INI parsing and logging helpers are vendored from
ThirteenAG/WidescreenFixesPack; see `licenses/WidescreenFixesPack.txt` and the licenses
embedded in `rini` and `nanoprintf`. Keep these notices when redistributing.
Record signatures, game builds and patch evidence in `docs/research/`.

## License

[{{LICENSE_SPDX}}](license). Third-party helper licenses also apply.
""",
    'emulator/release.bat': r"""@echo off
setlocal
cd /d "%~dp0"
if not exist "data\{{PLUGIN_SUBDIR}}\{{PROJECT_NAME}}{{TARGET_EXTENSION}}" exit /b 1
if exist "{{PROJECT_NAME}}.zip" del "{{PROJECT_NAME}}.zip"
7z a "{{PROJECT_NAME}}.zip" ".\data\*" ".\licenses\*" {{PACKAGE_EXCLUDES}} -xr!*.map -xr!*.o -xr!*.elf~ -xr!*.gitkeep
exit /b %errorlevel%
""",
    'psp/source/main.c': r"""#include <pspsdk.h>
#include <pspkernel.h>
#include <string.h>
#include "includes/plugin_api.h"

#define MODULE_NAME "{{PSP_MODULE_NAME}}"
#define GAME_MODULE "{{PSP_GAME_MODULE}}"
#define PLUGIN_PATH "ms0:/PSP/PLUGINS/{{PROJECT_NAME}}/{{PROJECT_NAME}}"
PSP_MODULE_INFO(MODULE_NAME, PSP_MODULE_USER, 1, 0);
#ifdef __cplusplus
PSP_HEAP_SIZE_KB(256);
static_assert(sizeof(MODULE_NAME) - 1 < 28, "PSP module names must be shorter than 28 bytes");
#else
_Static_assert(sizeof(MODULE_NAME) - 1 < 28, "PSP module names must be shorter than 28 bytes");
#endif

static void Init(void)
{
    logger.SetPath(PLUGIN_PATH ".log");
    inireader.SetIniPath(PLUGIN_PATH ".ini");
    char message[] = "{{PROJECT_NAME}} initialized";
    logger.Write(message);
    // Add game-version-checked MIPS patches here; validate every pattern match.
    // Flush caches after writing instructions.
    sceKernelDcacheWritebackAll();
    sceKernelIcacheClearAll();
}

static int StartPlugin(void)
{
    if (sceIoDevctl("kemulator:", 3, NULL, 0, NULL, 0) != 0) return 0;
    SceUID modules[64];
    int count = 0, found = 0;
    if (sceKernelGetModuleIdList(modules, sizeof(modules), &count) < 0) return 0;
    if (count > 64) count = 64;
    for (int i = 0; i < count; ++i) {
        SceKernelModuleInfo info;
        memset(&info, 0, sizeof(info));
        info.size = sizeof(info);
        if (sceKernelQueryModuleInfo(modules[i], &info) < 0) continue;
        if (strcmp(info.name, GAME_MODULE) == 0) {
            injector.SetGameBaseAddress(info.text_addr, info.text_size);
            pattern.SetGameBaseAddress(info.text_addr, info.text_size);
            found = 1;
        } else if (strcmp(info.name, MODULE_NAME) == 0) {
            injector.SetModuleBaseAddress(info.text_addr, info.text_size);
        }
    }
    if (found) Init();
    return 0;
}

#ifdef __cplusplus
// The SDK CRT initializes the heap and constructors before calling main.
int main(int argc, char** argv)
{
    (void)argc; (void)argv;
    StartPlugin();
    sceKernelSleepThread(); // Keep the PRX resident, as in the PSP CLEO plugin.
    return 0;
}
#else
int module_start(SceSize args, void* argp)
{
    (void)args; (void)argp;
    return StartPlugin();
}
#endif
""",
    'psp/source/makefile': r"""TARGET = ../data/{{PLUGIN_SUBDIR}}/{{PROJECT_NAME}}
# C helpers stay C; C++ files use the SDK's separate CXX compilation rule.
SOURCES = $(filter-out exports.c,$(wildcard *.c *.cpp includes/*.c includes/*.cpp))
OBJS = $(addsuffix .o,$(basename $(SOURCES)))
ifeq ({{PSP_BUILD_RULES}},build_prx.mak)
OBJS += exports.o
endif
CFLAGS = -O2 -Os -G0 -Wall -MMD -MP -fno-strict-aliasing -fshort-wchar -fno-pic -mno-check-zero-division -mpreferred-stack-boundary=4 -fpack-struct=16
CXXFLAGS = $(CFLAGS) -std=gnu++17 -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)
BUILD_PRX = 1
PRX_EXPORTS = exports.exp
LIBS = -lpspsystemctrl_user -lm
ifneq ($(filter %.cpp,$(SOURCES)),)
LIBS := -lstdc++ $(LIBS)
endif
PSPSDK = $(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/{{PSP_BUILD_RULES}}
-include $(OBJS:.o=.d)
.PHONY: clean-deps
clean: clean-deps
clean-deps:
	rm -f $(OBJS:.o=.d)
""",
    'psp/source/exports.exp': r"""PSP_BEGIN_EXPORTS
PSP_EXPORT_START(syslib, 0, 0x8000)
PSP_EXPORT_FUNC(module_start)
PSP_EXPORT_VAR(module_info)
PSP_EXPORT_END
PSP_END_EXPORTS
""",
    'psp/source/includes/plugin_api.h': r"""#pragma once
// The shared helpers are compiled as C even when the plugin is C++.
#ifdef __cplusplus
extern "C" {
#endif
#include "injector.h"
#include "patterns.h"
#include "inireader.h"
#include "log.h"
#ifdef __cplusplus
}
#endif
""",
    'pcsx2/source/main.c': r"""#include <stdint.h>
#include "includes/plugin_api.h"

// These symbol names are the loader ABI. Keep them in the ELF symbol table.
#ifdef __cplusplus
extern "C" {
#endif
int CompatibleCRCList[] = { {{PS2_CRCS}} };
int PCSX2Data[PCSX2Data_Size] = { 1 };
char OSDText[OSDStringNum][OSDStringSize] = { { 1 } };
char PluginData[MaxIniSize] = { 1 };

void init(void)
{
    logger.SetBuffer(OSDText, OSDStringNum, OSDStringSize);
    uint32_t size = *(uint32_t*)PluginData;
    if (size <= sizeof(PluginData) - sizeof(uint32_t))
        inireader.SetIniPath(PluginData + sizeof(uint32_t), size);
    char message[] = "{{PROJECT_NAME}} initialized";
    logger.Write(message);
    // Identify the supported executable and configure pattern scan bounds before
    // installing game-specific MIPS patches. Do not reuse another game's addresses.
}
#ifdef __cplusplus
}
#endif

int main(void) { return 0; }
""",
    'pcsx2/source/makefile': r"""EE_BIN = ../data/{{PLUGIN_SUBDIR}}/{{PROJECT_NAME}}.elf
SOURCES = $(wildcard *.c *.cpp includes/*.c includes/*.cpp)
EE_OBJS = $(addsuffix .o,$(basename $(SOURCES)))
EE_CFLAGS = -Os -G0 -Wall -MMD -MP -fno-strict-aliasing -fshort-wchar -fno-pic -mno-check-zero-division -fpack-struct=16
EE_CXXFLAGS = $(EE_CFLAGS) -std=gnu++17 -fno-exceptions -fno-rtti
BASE_ADDRESS = {{PS2_BASE_ADDRESS}}
EE_LINKFILE = linkfile
ifneq ($(filter %.cpp,$(SOURCES)),)
EE_LIBS += -l:libstdc++.a
endif
EE_LIBS += -l:libc.a -l:libm.a -l:libgcc.a
EE_LDFLAGS = -Wl,--entry=init -Wl,-Map,$(EE_BIN).map -Wl,-exclude-libs,ALL -Wl,'--defsym=BASE_ADDRESS=$(BASE_ADDRESS)'
.PHONY: all clean
all: $(EE_BIN)
clean:
	rm -f $(EE_OBJS) $(EE_OBJS:.o=.d) $(EE_BIN) $(EE_BIN).map
PS2SDK = ../external/ps2sdk/ps2sdk
include $(PS2SDK)/samples/Makefile.pref
include $(PS2SDK)/samples/Makefile.eeglobal
-include $(EE_OBJS:.o=.d)
""",
    'pcsx2/source/includes/plugin_api.h': r"""#pragma once
// Preserve the loader ABI and link C++ plugin code to the C helpers.
#ifdef __cplusplus
extern "C" {
#endif
#include "pcsx2f_api.h"
#include "patterns.h"
#include "injector.h"
#include "inireader.h"
#include "log.h"
#ifdef __cplusplus
}
#endif
""",
}


def configure(cfg, target, language, game_module, disc_ids, crcs, base):
    cfg.update(target=target, language=language, game_module=game_module,
               disc_ids=disc_ids, crcs=crcs, base=base)
    if target == 'windows':
        return cfg
    psp = target == 'psp'
    sdk = 'pspsdk' if psp else 'ps2sdk'
    cfg.update(submodules=[dict(name=sdk, path='external/' + sdk,
               url='https://github.com/ThirteenAG/' + sdk)], run_git_sm=True,
               enable_signing=False, has_embpdb=False, steam_app_id='')
    name = cfg['tokens']['PROJECT_NAME']
    cfg['tokens'].update(MSBUILD_PLATFORM='Win32', OUTPUT_KIND='Makefile',
        TARGET_EXTENSION='.prx' if psp else '.elf', PLUGIN_LANGUAGE=language,
        TARGET_PROFILE='PPSSPP' if psp else 'PCSX2F',
        PLUGIN_SUBDIR='memstick/PSP/PLUGINS/' + name if psp else 'PLUGINS',
        EMULATOR_ENV_KEY='PPSSPP_DIR' if psp else 'PCSX2F_DIR',
        EMULATOR_EXE=cfg['game_exe'] or ('PPSSPPWindows64.exe' if psp else 'pcsx2-qtx64-clang.exe'),
        SDK_WRAPPER='external/pspsdk/vsmake.ps1' if psp else 'external/ps2sdk/ee/bin/vsmake.ps1',
        PSP_MODULE_NAME=name[:27], PSP_GAME_MODULE=game_module,
        PSP_BUILD_RULES='build.mak' if language == 'C++' else 'build_prx.mak',
        PS2_CRCS=', '.join('(int)0x' + crc.removeprefix('0x') for crc in re.split(r'[,\s]+', crcs.strip()) if crc),
        PS2_BASE_ADDRESS=base, PACKAGE_EXCLUDES='-xr!*.elf' if psp else '')
    return cfg


def validate(cfg):
    errors = []
    if cfg['target'] == 'psp':
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,27}', cfg['game_module']):
            errors.append('Enter the internal PSP game module name (up to 27 characters).')
        ids = re.split(r'[,\s]+', cfg['disc_ids'].strip())
        if not ids or any(not re.fullmatch(r'[A-Z]{4}[0-9]{5}', value) for value in ids):
            errors.append('Enter PSP disc IDs such as ULUS10041, separated by commas.')
    if cfg['target'] == 'pcsx2':
        crcs = re.split(r'[,\s]+', cfg['crcs'].strip())
        if not crcs or any(not re.fullmatch(r'(?:0x)?[A-Fa-f0-9]{8}', value) or int(value, 16) == 0 for value in crcs):
            errors.append('Enter nonzero eight-digit PS2 game CRCs, separated by commas.')
        try:
            address = int(cfg['base'], 16)
            if not re.fullmatch(r'0x[0-9A-Fa-f]{8}', cfg['base']) or not 0x02000000 <= address < 0x10000000 or address % 128:
                raise ValueError()
        except ValueError:
            errors.append('PS2 load address must be 128-byte aligned within extended memory (0x02000000–0x0FFFFFFF).')
    return errors


def manifest(target):
    files = {'licenses/WidescreenFixesPack.txt': 'license'}
    for name in ['injector', 'patterns', 'inireader', 'log', 'memalloc', 'mips', 'rini']:
        for ext in ['c', 'h']:
            files['source/includes/' + name + '.' + ext] = 'includes/' + target + '/' + name + '.' + ext
    files['source/includes/nanoprintf.h'] = 'includes/' + target + '/nanoprintf.h'
    if target == 'pcsx2':
        files['source/includes/pcsx2f_api.h'] = 'includes/pcsx2/pcsx2f_api.h'
    return files


def fetch(target, emit=print):
    """Fetch everything before changing project files; failure leaves the template intact."""
    result = {}
    for dest, source in manifest(target).items():
        emit('Downloading ' + source)
        with urlopen(BASE_URL + source, timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if not data or len(data) > 2 * 1024 * 1024:
            raise ValueError('Invalid download size: ' + source)
        result[dest] = data.decode('utf-8-sig')
    return result


def initialize_sdk(root, cfg, run_git, emit):
    sm = cfg['submodules'][0]
    ok, out = run_git(['ls-files', '--stage', '--', sm['path']], root)
    if not ok:
        raise RuntimeError(out)
    if not out.startswith('160000 '):
        ok, out = run_git(['submodule', 'add', '--', sm['url'], sm['path']], root)
        if not ok:
            raise RuntimeError('SDK submodule registration failed: ' + out)
    ok, out = run_git(['submodule', 'update', '--init', '--recursive', '--', sm['path']], root)
    if not ok:
        raise RuntimeError('SDK initialization failed: ' + out)
    if not (root / cfg['tokens']['SDK_WRAPPER']).is_file():
        raise RuntimeError('SDK submodule is missing its build wrapper.')
    emit('SDK submodule registered and initialized: ' + sm['path'])


def generate(root, cfg, downloads):
    tokens = cfg['tokens']
    target = cfg['target']
    files = dict(downloads)
    if target == 'pcsx2':
        linkfile = (root / 'external/ps2sdk/ps2sdk/ee/startup/linkfile').read_text(encoding='utf-8')
        if '.text 0x00100000:' not in linkfile:
            raise ValueError('Unexpected PS2SDK linker script layout')
        files['licenses/PS2SDK.txt'] = (root / 'external/ps2sdk/ps2sdk/LICENSE').read_text(encoding='utf-8')
        files['source/linkfile'] = linkfile.replace('.text 0x00100000:', '.text BASE_ADDRESS :')
    for key, text in TEMPLATES.items():
        platform, rel = key.split('/', 1)
        if platform not in ('emulator', target):
            continue
        if rel == 'source/main.c' and cfg['language'] == 'C++':
            rel = 'source/main.cpp'
        files[rel] = text
    readme = files['readme.md'].replace('source/main.c', 'source/main.cpp' if cfg['language'] == 'C++' else 'source/main.c')
    readme += '\nHelpers downloaded by setup from WidescreenFixesPack revision `' + REVISION + '`.\n'
    if target == 'pcsx2' and cfg['language'] == 'C++':
        readme += '\nThe direct `init` entry does not initialize a C++ heap or run global constructors. Add explicit runtime initialization before using heap-based STL or nontrivial global objects; exceptions and RTTI are disabled.\n'
    files['readme.md'] = readme
    if target == 'psp':
        files['data/' + tokens['PLUGIN_SUBDIR'] + '/plugin.ini'] = '[options]\ntype = prx\nfilename = {{PROJECT_NAME}}.prx\nversion = 1\nmemory = 93\n\n[games]\n' + ''.join(value + ' = true\n' for value in re.split(r'[,\s]+', cfg['disc_ids'].strip()))
    # Remove only the known native starter, never arbitrary user source files.
    for rel in ['source/dllmain.cpp', 'source/common.hxx', 'source/common.ixx',
                'source/includes/callbacks.h', 'source/includes/gameref.hpp', 'source/includes/ModuleList.hpp',
                'source/resources/VersionInfo.h', 'source/resources/Versioninfo.rc', 'data/plugins/.gitkeep']:
        (root / rel).unlink(missing_ok=True)
    plugins = root / 'data/plugins'
    if plugins.is_dir() and not any(plugins.iterdir()):
        plugins.rmdir()
    (root / 'data' / tokens['PLUGIN_SUBDIR']).mkdir(parents=True, exist_ok=True)
    for rel, text in files.items():
        for key, value in tokens.items():
            text = text.replace('{{' + key + '}}', value)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
    workflow = root / '.github/workflows/msvc.yml'
    text = workflow.read_text(encoding='utf-8')
    text = re.sub(r'    - name: Download Ultimate ASI Loader\n.*?(?=    - name: Pack binaries)', '', text, flags=re.S)
    workflow.write_text(text, encoding='utf-8')
