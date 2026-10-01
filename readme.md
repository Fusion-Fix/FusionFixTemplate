# {{PROJECT_NAME}}

> A fix/enhancement mod for [Game Name].

## Installation

1. Download the latest release from the [Releases]({{REPO_URL}}/releases/latest) page.
2. Extract the archive into the game root directory.
3. Launch the game.

## Building from Source

Requirements:
- Visual Studio 2022 or 2026 (with C++ desktop workload)
- Git (for submodule checkout)

```bat
git clone --recurse-submodules {{REPO_URL}}
cd {{PROJECT_NAME}}
premake5.bat
```

Open `build/{{PROJECT_NAME}}.{{SOLUTION_EXTENSION}}` in Visual Studio and build.

For local deployment, create a `.env` file next to `premake5.lua` (the setup wizard
also creates it when you supply a game install path):

```dotenv
GAME_DIR=C:/Games/GameName
```

This file is ignored by git. Quotes and a trailing slash are optional. Rerun
`premake5.bat` after changing it. Builds replace an already installed plugin in
`GAME_DIR/plugins/`; without `GAME_DIR`, no copy or game debugging is configured.
Build output remains in `bin/Release` or `bin/Debug`.

To launch the game from Visual Studio, set the executable and plugin subdirectory
in `premake5.lua`, then regenerate the solution:

```lua
setpaths("GAME_DIR", "Game.exe", "plugins/")
```

The setup GUI can also set the relative game executable, plugin subdirectory and
optional Steam App ID. Deployment and packaging use the selected subdirectory.

The setup GUI also creates PSP and PCSX2F plugins in C or C++, downloading helper
files from GitHub and adding the SDK as a submodule. See the
[emulator setup notes](contributing.md#psp--pcsx2f-setup).
## Contributing

Pull requests are welcome. Please open an issue first to discuss what you would like to change.
See [contributing.md](contributing.md) for workflow and reverse-engineering note conventions.

## License

[{{LICENSE_SPDX}}](license)
