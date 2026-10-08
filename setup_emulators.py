"""Emulator setup: generated build files using SDK and injector submodules."""
import re
TEMPLATES = {
    'emulator/build-plugin.ps1': r"""param([ValidateSet('Debug', 'Release')][string]$Configuration = 'Release', [switch]$Clean)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$wrapper = Join-Path $root '{{SDK_WRAPPER}}'
if (-not (Test-Path -LiteralPath $wrapper)) {
    throw 'SDK missing. Run git submodule update --init --recursive.'
}
$outputDir = Join-Path $root 'data/{{PLUGIN_SUBDIR}}'
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$makeArgs = @('-Project', (Join-Path $root 'source/module.json'))
if ('{{HELPER_PLATFORM}}' -eq 'psp') { $makeArgs += @('-Configuration', $Configuration) }
if ($Clean) { $makeArgs += '-Clean' }
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

require "vstudio"

-- {{MSBUILD_PLATFORM}} as a Visual Studio platform of its own (as premake-consoles does for
-- consoles); the project is a Makefile one, so no MSBuild platform files are needed.
premake.vstudio.vs2010_architectures.{{HELPER_PLATFORM}} = "{{MSBUILD_PLATFORM}}"
premake.api.addAllowed("system", "{{HELPER_PLATFORM}}")

workspace "{{PROJECT_NAME}}"
   configurations { "Release", "Debug" }
   platforms { "{{MSBUILD_PLATFORM}}" }
   system "{{HELPER_PLATFORM}}"
   bindirs { "$(PATH)" } -- unknown VS platform: keep the system PATH for the build commands
   location "build"
   startproject "{{PROJECT_NAME}}"

project "{{PROJECT_NAME}}"
   kind "Makefile"
   language "{{PLUGIN_LANGUAGE}}"
   cppdialect "C++17"
   targetdir "data/{{PLUGIN_SUBDIR}}"
   targetextension "{{TARGET_EXTENSION}}"
   files { "source/**.c", "source/**.cpp", "source/**.h", "source/**.hpp", "source/makefile", "source/module.json", "source/exports.exp", "data/**.ini" }
   includedirs { "source/includes", "external/injector/include" }
   files { "external/injector/include/{{HELPER_PLATFORM}}/**.h", "external/injector/include/{{HELPER_PLATFORM}}/**.hpp" }
   local command = 'powershell -NoProfile -ExecutionPolicy Bypass -File "' .. path.getabsolute("build-plugin.ps1") .. '" -Configuration "%{cfg.buildcfg}"'
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
Both SDK module builders read `source/module.json`, support paths containing spaces,
and keep intermediate files separate. Update the manifest when adding source files.

Alternatively, run `premake5.bat` and open `build/{{PROJECT_NAME}}.{{SOLUTION_EXTENSION}}`.
Visual Studio invokes the same SDK build through its {{MSBUILD_PLATFORM}} platform. For PSP, Debug enables the starter's hook diagnostics and adds debug symbols while retaining
the optimized guest code; Release omits the starter hook diagnostics.
The shared logger remains available in both configurations. Select Debug with
`build-plugin.ps1 -Configuration Debug` or the Visual Studio configuration.
PS2 configurations retain their existing SDK flags. Both use the same output path.

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
game CRCs and enable 128 MB RAM. The injector assigns the ELF a dynamic base,
private stack and heap. The SDK module runtime runs global C++ constructors before
calling `init`; exceptions and RTTI are disabled. The starter performs no patches.

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

MIPS injection, patterns, INI parsing and logging helpers come from the
`external/injector` submodule. C APIs and standalone C++ hook/patch handles are
available under `include/{{HELPER_PLATFORM}}`; see its `hooks.md` for memory,
cache and register contracts. Keep `licenses/EmulatorHelpers.txt` and the embedded
`rini`/`nanoprintf` notices when redistributing. Update the submodule to update helpers.
Record signatures, game builds and patch evidence in `docs/research/`.

## License

[{{LICENSE_SPDX}}](license). Third-party helper licenses also apply.
""",
    'emulator/release.bat': r"""@echo off
setlocal
cd /d "%~dp0"
if not exist "data\{{PLUGIN_SUBDIR}}\{{PROJECT_NAME}}{{TARGET_EXTENSION}}" exit /b 1
if exist "{{PROJECT_NAME}}.zip" del "{{PROJECT_NAME}}.zip"
7z a "{{PROJECT_NAME}}.zip" ".\data\*" ".\licenses\*" {{PACKAGE_EXCLUDES}} -xr!*.objects -xr!*.map -xr!*.o -xr!*.elf~ -xr!*.gitkeep
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
    'psp/source/makefile': r"""CONFIGURATION ?= Release
.PHONY: all clean
all:
	powershell -NoProfile -ExecutionPolicy Bypass -File "../external/pspsdk/plugins/build-module.ps1" -Project module.json -Configuration "$(CONFIGURATION)"
clean:
	powershell -NoProfile -ExecutionPolicy Bypass -File "../external/pspsdk/plugins/build-module.ps1" -Project module.json -Configuration "$(CONFIGURATION)" -Clean
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
#include <psp/injector.h>
#include <psp/patterns.h>
#include <psp/inireader.h>
#include <psp/log.h>
#ifdef __cplusplus
}
#endif
#ifdef __cplusplus
#include <psp/hooks.hpp>
#include <psp/patches.hpp>
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
    'pcsx2/source/makefile': r""".PHONY: all clean
all:
	powershell -NoProfile -ExecutionPolicy Bypass -File "../external/ps2sdk/plugins/build-module.ps1" -Project module.json
clean:
	powershell -NoProfile -ExecutionPolicy Bypass -File "../external/ps2sdk/plugins/build-module.ps1" -Project module.json -Clean
""",
    'pcsx2/source/includes/plugin_api.h': r"""#pragma once
// Preserve the loader ABI and link C++ plugin code to the C helpers.
#ifdef __cplusplus
extern "C" {
#endif
#include <ps2/pcsx2f_api.h>
#include <ps2/patterns.h>
#include <ps2/injector.h>
#include <ps2/inireader.h>
#include <ps2/log.h>
#ifdef __cplusplus
}
#endif
#ifdef __cplusplus
#include <ps2/hooks.hpp>
#include <ps2/patches.hpp>
#endif
""",
}


CPP_TEMPLATES = {
    'psp/source/includes/plugin_api.h': r"""#pragma once
#include <psp/injector.hpp>
#include <psp/safetymips.hpp>
#include <psp/hooks_guest.h>
#include <psp/memalloc.h>
extern "C" {
#include <psp/patterns.h>
#include <psp/inireader.h>
#include <psp/log.h>
}
""",
    'pcsx2/source/includes/plugin_api.h': r"""#pragma once
#include <stdlib.h>
#include <ps2/injector.hpp>
#include <ps2/safetymips.hpp>
#include <ps2/game_abi.hpp>
#include <ps2/hooks_guest.h>
extern "C" {
#include "guest_module.h"
#include <ps2/pcsx2f_api.h>
#include <ps2/patterns.h>
#include <ps2/inireader.h>
#include <ps2/log.h>
extern const PCSX2FModuleContext* PCSX2FContext;
}
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
               url='https://github.com/ThirteenAG/' + sdk),
               dict(name='injector', path='external/injector', url='https://github.com/ThirteenAG/injector')], run_git_sm=True,
               enable_signing=False, has_embpdb=False, steam_app_id='')
    name = cfg['tokens']['PROJECT_NAME']
    cfg['tokens'].update(MSBUILD_PLATFORM='PSP' if psp else 'PS2', OUTPUT_KIND='Makefile',
        TARGET_EXTENSION='.prx' if psp else '.elf', PLUGIN_LANGUAGE=language,
        TARGET_PROFILE='PPSSPP' if psp else 'PCSX2F', HELPER_PLATFORM='psp' if psp else 'ps2',
        PLUGIN_SUBDIR='memstick/PSP/PLUGINS/' + name if psp else 'PLUGINS',
        EMULATOR_ENV_KEY='PPSSPP_DIR' if psp else 'PCSX2F_DIR',
        EMULATOR_EXE=cfg['game_exe'] or ('PPSSPPWindows64.exe' if psp else 'pcsx2-qtx64.exe'),
        SDK_WRAPPER='external/' + sdk + '/plugins/build-module.ps1',
        PSP_MODULE_NAME=name[:27], PSP_GAME_MODULE=game_module,
        PS2_CRCS=', '.join('(int)0x' + crc.removeprefix('0x') for crc in re.split(r'[,\s]+', crcs.strip()) if crc),
        PACKAGE_EXCLUDES='-xr!*.elf' if psp else '')
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
    return errors


def initialize_submodules(root, cfg, run_git, emit):
    for sm in cfg['submodules']:
        ok, out = run_git(['ls-files', '--stage', '--', sm['path']], root)
        if not ok:
            raise RuntimeError(out)
        if not out.startswith('160000 '):
            ok, out = run_git(['submodule', 'add', '--', sm['url'], sm['path']], root)
            if not ok:
                raise RuntimeError('Submodule registration failed: ' + out)
        ok, out = run_git(['submodule', 'update', '--init', '--recursive', '--', sm['path']], root)
        if not ok:
            raise RuntimeError('Submodule initialization failed: ' + out)
        emit('Submodule initialized: ' + sm['path'])
    if not (root / cfg['tokens']['SDK_WRAPPER']).is_file():
        raise RuntimeError('SDK submodule is missing its build wrapper.')
    if not (root / 'external/injector/include' / ('psp' if cfg['target'] == 'psp' else 'ps2') / 'hooks.h').is_file():
        raise RuntimeError('Injector submodule lacks emulator helpers; update it to a compatible revision.')


def generate(root, cfg):
    tokens = cfg['tokens']
    target = cfg['target']
    helper_platform = 'psp' if target == 'psp' else 'ps2'
    files = {'licenses/EmulatorHelpers.txt': (root / 'external/injector/include' / helper_platform / 'LICENSE').read_text(encoding='utf-8')}
    if target == 'pcsx2':
        files['licenses/PS2SDK.txt'] = (root / 'external/ps2sdk/ps2sdk/LICENSE').read_text(encoding='utf-8')
    for key, text in TEMPLATES.items():
        platform, rel = key.split('/', 1)
        if platform not in ('emulator', target):
            continue
        if rel == 'source/main.c' and cfg['language'] == 'C++':
            rel = 'source/main.cpp'
        if cfg['language'] == 'C++' and key in CPP_TEMPLATES:
            text = CPP_TEMPLATES[key]
        if cfg['language'] == 'C++' and rel == 'source/main.cpp':
            if target == 'psp':
                text = text.replace('PSP_HEAP_SIZE_KB(256);', '// Hook storage is embedded in this PRX; no system heap is requested.')
                start = text.index('#ifdef __cplusplus\n// The SDK CRT')
                text = text[:start] + '''extern "C" int module_start(SceSize args, void* argp)
{
    (void)args; (void)argp;
    return StartPlugin();
}
'''
                text = text.replace('static void Init(void)', 'static psp_hook_guest hookGuest{};\n\nstatic int Init(void)')
                text = text.replace('    // Add game-version-checked MIPS patches here; validate every pattern match.\n    // Flush caches after writing instructions.\n    sceKernelDcacheWritebackAll();\n    sceKernelIcacheClearAll();', '    psp_hook_backend backend{};\n    if (psp_hook_guest_backend(&backend, &hookGuest, psp_mem_storage_begin(), psp_mem_storage_size(),\n                               AllocMemBlock, FreeMemBlock) != PSP_HOOK_OK) return -1;\n    if (injector::Initialize(backend, [](psp_hook_status status) {\n#if (defined(DEBUG) || defined(_DEBUG)) && !defined(NDEBUG)\n        logger.WriteF("Hook installation failed: %u", (unsigned)status);\n#else\n        (void)status;\n#endif\n    }) != PSP_HOOK_OK) return -1;\n    // Resolve supported game patterns, then use injector::MakeCALL/WriteMemory\n    // or safetymips::create_inline/create_mid with SafetyMipsContext& callbacks.\n    // Keep owning SafetyMips handles alive after Init returns.\n    return injector::FlushCaches() == PSP_HOOK_OK ? 0 : -1;')
                text = text.replace('            injector.SetGameBaseAddress(info.text_addr, info.text_size);\n', '')
                text = text.replace('        } else if (strcmp(info.name, MODULE_NAME) == 0) {\n            injector.SetModuleBaseAddress(info.text_addr, info.text_size);', '')
                text = text.replace('    if (found) Init();', '    if (found) return Init();')
            else:
                text = text.replace('void init(void)', 'void init(void)')
                text = text.replace("    // Identify the supported executable and configure pattern scan bounds before\n    // installing game-specific MIPS patches. Do not reuse another game's addresses.", '    static pcsx2_hook_guest hookGuest{};\n    pcsx2_hook_backend backend{};\n    if (pcsx2_hook_guest_backend(&backend, &hookGuest, PCSX2FContext, malloc, free) != PCSX2_HOOK_OK) return;\n    if (injector::Initialize(backend, [](pcsx2_hook_status status) {\n        logger.WriteF("Hook installation failed: %u", (unsigned)status);\n    }) != PCSX2_HOOK_OK) return;\n    // Resolve supported game patterns, then use injector::MakeCALL/WriteMemory\n    // or safetymips::create_inline/create_mid with SafetyMipsContext& callbacks.\n    // Keep owning SafetyMips handles alive after init returns.\n    injector::FlushCaches();')
        files[rel] = text
    readme = files['readme.md'].replace('source/main.c', 'source/main.cpp' if cfg['language'] == 'C++' else 'source/main.c')
    if target == 'psp' and cfg['language'] == 'C++':
        readme = readme.replace('For PSP, enable plugins in PPSSPP.',
            'The minimal PSP C++ runtime runs constructors before `module_start` and\n'
            'keeps destructor registrations bounded inside the PRX. Hook storage is\n'
            'embedded; this starter requests no system heap.\n\nFor PSP, enable plugins in PPSSPP.')
    if target == 'pcsx2' and cfg['language'] == 'C++':
        readme = readme.replace('Record signatures, game builds and patch evidence in `docs/research/`.',
            'Native PS2 games may use the SGI argument/register ABI. Use\n'
            '`injector::GameFunction`, `injector::GameCallback` and\n'
            '`safetymips::create_inline_game` for those boundaries; ordinary SDK calls\n'
            'use the standard frontends. See `ps2/game_abi.hpp`.\n'
            'Record signatures, game builds and patch evidence in `docs/research/`.')
    import json
    sources = sorted(rel.removeprefix('source/') for rel in files if rel.startswith('source/') and rel.endswith(('.c', '.cpp')))
    helpers = ['patterns', 'inireader', 'log', 'memalloc', 'rini']
    if cfg['language'] != 'C++':
        helpers = ['injector', 'patterns', 'inireader', 'log', 'memalloc', 'mips', 'rini']
    sources += ['../external/injector/include/' + helper_platform + '/' + name + '.c' for name in helpers]
    module = dict(sources=sources, includes=['../external/injector/include'], output='../data/' + tokens['PLUGIN_SUBDIR'] + '/' + tokens['PROJECT_NAME'] + tokens['TARGET_EXTENSION'])
    if target == 'psp':
        module.update(exports='exports.exp', startup='module_start',
                      defines=['PSP_HOOK_RAM_END=0x0DD00000', 'PSP_GAME_ABI_COMPAT'],
                      libraries=['-lpspsystemctrl_user', '-lm'],
                      c_flags=['-O2', '-Os', '-G0', '-Wall', '-fno-strict-aliasing', '-fshort-wchar', '-fno-pic', '-mno-check-zero-division', '-mpreferred-stack-boundary=4', '-fpack-struct=16'],
                      cxx_flags=['-std=gnu++17', '-fno-exceptions', '-fno-rtti'])
    if target == 'psp' and cfg['language'] == 'C++':
        module['defines'].append('MEM_CUSTOM_TOTAL_SIZE=16384')
    if target == 'pcsx2':
        # Mid-hook callbacks must not introduce EE scalar-ACC operations.
        module.update(c_flags=['-ffp-contract=off'], cxx_flags=['-ffp-contract=off'])
    files['source/module.json'] = json.dumps(module, indent=2) + '\n'
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
