-- The folder a project is deployed to, and the game it is started from when debugging,
-- is the path of one machine and does not belong in the repository. It is read from a
-- `.env` file next to this script, which is not tracked by git and holds one
-- `<KEY>=<folder>` line per game (quotes and a trailing slash are optional). A project
-- whose key is missing is not deployed at all.
local envkeys = nil
function envdir(key)
   if not envkeys then
      envkeys = {}
      local text = io.readfile(path.join(_SCRIPT_DIR, ".env")) or ""
      for line in text:gmatch("[^\r\n]+") do
         local k, v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
         if k and v ~= "" then
            v = v:gsub('^"', ""):gsub('"$', ""):gsub("^'", ""):gsub("'$", "")
            envkeys[k] = v
         end
      end
   end

   local value = envkeys[key]
   if not value then return nil end

   value = value:gsub("[%s\\/]+$", "")
   if value == "" then return nil end

   return path.translate(value)
end

-- Deploys the built .asi into the script folder of the game that `key` names in the .env
-- file, and starts the game from there when debugging. Only a plugin that is already
-- installed in the game folder is replaced, a folder without one is left alone.
function setpaths(key, exepath, scriptspath)
   scriptspath = scriptspath or "scripts/"
   local gamepath = envdir(key)
   if gamepath then
      local target = path.translate(path.join(gamepath, scriptspath)) .. "\\"
      postbuildcommands {
         "if exist \"" .. target .. "$(TargetFileName)\" copy /y \"$(TargetPath)\" \"" .. target .. "\"",
      }
      debugdir (gamepath)
      if exepath and exepath ~= "" then
         debugcommand (path.join(gamepath, exepath))
         debugdir (path.join(gamepath, path.getdirectory(exepath)))
      end
   end
end

newoption {
    trigger     = "with-version",
    value       = "STRING",
    description = "Current version",
}

workspace "{{PROJECT_NAME}}"
   configurations { "Release", "Debug" }
   architecture "{{ARCHITECTURE}}"
   location "build"
   objdir "build/obj/%{prj.name}/%{cfg.buildcfg}"
   cppdialect "C++latest"
   targetdir "bin/%{cfg.buildcfg}"
   buildoptions { "/dxifcInlineFunctions- /Zc:__cplusplus /utf-8" }
   staticruntime "On"
   multiprocessorcompile ("On")
   startproject "{{PROJECT_NAME}}"

   local major = os.date("%d")
   local minor = os.date("%m")
   local build = os.date("%Y")
   local revision = os.date("%H") .. os.date("%M")

   if _OPTIONS["with-version"] then
      local t = {}
      for i in _OPTIONS["with-version"]:gmatch("([^.]+)") do
         t[#t + 1], _ = i:gsub("%D+", "")
      end
      while #t < 4 do t[#t + 1] = 0 end
      major    = math.min(tonumber(t[1]), 255)
      minor    = math.min(tonumber(t[2]), 255)
      build    = math.min(tonumber(t[3]), 65535)
      revision = math.min(tonumber(t[4]), 65535)
   end

   local githash = ""
   local f = io.popen("git rev-parse --short HEAD")
   if f then
      githash = f:read("*a"):gsub("%s+", "")
      f:close()
   end

   local productVersion = major .. "." .. minor .. "." .. build .. "." .. revision
   if githash ~= "" then
      productVersion = productVersion .. "-" .. githash
   end

   filter "configurations:Debug"
      defines { "DEBUG" }
      symbols "On"

   filter "configurations:Release"
      defines { "NDEBUG" }
      optimize "On"

   filter {}

project "{{PROJECT_NAME}}"
   kind "{{OUTPUT_KIND}}"
   language "C++"
   targetdir "bin/%{cfg.buildcfg}"
   targetextension "{{TARGET_EXTENSION}}"
   characterset ("Unicode")

   defines { "rsc_CompanyName=\"{{PROJECT_NAME}}\"" }
   defines { "rsc_LegalCopyright=\"{{LICENSE_SPDX}}\""}
   defines { "rsc_InternalName=\"%{prj.name}\"", "rsc_ProductName=\"%{prj.name}\"", "rsc_OriginalFilename=\"%{cfg.buildtarget.name}\"" }
   defines { "rsc_FileDescription=\"{{PROJECT_NAME}}\"" }
   defines { "rsc_UpdateUrl=\"{{REPO_URL}}\"" }
   defines { "rsc_FileVersion_MAJOR=" .. major }
   defines { "rsc_FileVersion_MINOR=" .. minor }
   defines { "rsc_FileVersion_BUILD=" .. build }
   defines { "rsc_FileVersion_REVISION=" .. revision }
   defines { "rsc_FileVersion=\"" .. major .. "." .. minor .. "." .. build .. "\"" }
   defines { "rsc_ProductVersion=\"" .. productVersion .. "\"" }
   defines { "rsc_GitSHA1=\"" .. githash .. "\"" }
   defines { "rsc_GitSHA1W=L\"" .. githash .. "\"" }
   defines { "_CRT_SECURE_NO_WARNINGS" }

   includedirs { "source" }
   includedirs { "source/includes" }
   files { "source/**.h", "source/**.hpp", "source/**.cpp", "source/**.hxx", "source/**.ixx" }
   files { "source/resources/Versioninfo.rc" }
   files { "data/**.ini" }

   -- ##BEGIN_EXTERNAL_SUBMODULES## (managed by setup.py - do not edit this line)
   -- ##END_EXTERNAL_SUBMODULES## (managed by setup.py - do not edit this line)

   -- Set GAME_DIR in .env for local deployment; supply the game executable to debug it.
   setpaths("GAME_DIR", nil, "plugins/")
