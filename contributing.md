# Contributing

## Development flow

1. Open an issue (bug/feature/performance) before major work.
2. Work in a topic branch.
3. Keep changes scoped and include reproduction steps where possible.

## Reverse-engineering notes

Do not leave findings only in chat logs.

- Put durable findings in `docs/research/`.
- Use one file per topic (pattern scans, class layouts, offsets, call flows).
- Include game version/build and evidence (addresses, signatures, traces, screenshots).
- Update notes when assumptions change.

Suggested filename format:

`docs/research/YYYY-MM-DD-<topic>.md`

## Code review checklist

- Works on target architecture (x86/x64).
- No pointer truncation (`DWORD` casts for addresses are not allowed on x64).
- Premake and CI stay in sync with selected settings.
- New dependencies are declared as submodules and wired in premake.

## PSP / PCSX2F setup

Run `python setup.py` and select `psp` or `pcsx2` in the Target tab, then choose C
or C++. Supply the PSP internal game module and disc IDs, or PS2 game CRCs and
load address. The local game path is the emulator directory, stored in `.env`
as `PPSSPP_DIR` or `PCSX2F_DIR`.

Setup downloads only the selected platform's injection, pattern, INI and logging
helpers from a pinned WidescreenFixesPack GitHub revision. The PS2 linker script
comes from the initialized SDK submodule, retaining its license notice.
It preserves their licenses. No `template-assets` directory is needed. Internet
access and Git are required: setup always adds and initializes `external/pspsdk`
or `external/ps2sdk` as a real submodule, even if the Windows submodule checkbox
is unchecked. Download or SDK failures stop setup before template rewriting.
Generated CI checks out submodules recursively and invokes the same SDK build
through Visual Studio. It excludes Windows plugin-sdk and ASI Loader steps.

The generated `build-plugin.ps1` builds directly on Windows; `premake5.bat` creates
a Visual Studio Makefile project. Keep the checkout path free of spaces because
the SDK makefiles use unquoted paths. PSP packages use the portable PPSSPP
`memstick/PSP/PLUGINS/<project>/` layout; PS2 packages use `PLUGINS/` and require
PCSX2F or a compatible PCSX2 Plugin Injector. Verify game IDs, CRCs, scan bounds
and the reserved load address before adding patches.

C helpers retain C linkage in C++ projects. PSP C++ uses SDK CRT startup for the
heap and global constructors. PS2 enters `init` directly; add explicit heap and
constructor initialization before heap-based STL or nontrivial global objects.
The starter disables exceptions and RTTI. Both languages produce guest MIPS
plugins, not host emulator graphics/input plugins.
