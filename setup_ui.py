"""Local browser UI for the setup wizard; no third-party dependencies."""
import json
import secrets
import threading
import webbrowser
from setup_licenses import LICENSES
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


def launch(root, defaults, configure, validate, apply, libraries, required, games, licenses, versions,
           open_browser=True, ready=None):
    token = secrets.token_urlsafe(32)
    lock = threading.Lock()
    state = {"phase": "idle", "log": [], "error": ""}
    modules = {sm["name"]: sm for sm in defaults.get("submodules", [])}
    payload = dict(defaults=defaults, root=str(root), licenses=[dict(id=spdx, name=LICENSES[spdx]["name"]) for spdx in licenses], versions=versions,
                   games=[dict(name=g[0], architecture="x64" if g[5] == "x64" else "x86") for g in games],
                   submodules=[dict(name=name, path=modules.get(name, {}).get("path", path),
                                    url=modules.get(name, {}).get("url", url), required=name in required,
                                    enabled=name in required or modules.get(name, {}).get("enabled", False))
                               for name, path, url in libraries])

    def emit(message):
        with lock:
            state["log"].append(str(message))

    def work(cfg):
        try:
            apply(cfg, emit)
        except Exception as exc:
            with lock:
                state.update(phase="failed", error=str(exc))
                state["log"].append("ERROR: " + str(exc))
        else:
            with lock:
                state["phase"] = "complete"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, code, body, content_type="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def authorized(self, page=False):
            provided = (parse_qs(urlsplit(self.path).query).get("session", [""])[0]
                        if page else self.headers.get("X-Setup-Session", ""))
            if not secrets.compare_digest(provided, token):
                self.respond(403, {"error": "Relaunch setup.py to open an authorized setup session."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin != address:
                self.respond(403, {"error": "Unexpected request origin."})
                return False
            return True

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/":
                if self.authorized(page=True):
                    self.respond(200, HTML, "text/html")
            elif path == "/api/defaults" and self.authorized():
                self.respond(200, payload)
            elif path == "/api/status" and self.authorized():
                with lock:
                    snapshot = dict(state, log=list(state["log"]))
                self.respond(200, snapshot)
            elif path not in {"/api/defaults", "/api/status"}:
                self.respond(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return
            path = urlsplit(self.path).path
            if path == "/api/close":
                with lock:
                    running = state["phase"] == "running"
                if running:
                    self.respond(409, {"error": "Wait for setup to finish."})
                    return
                self.respond(200, {"ok": True})
                threading.Thread(target=server.shutdown, daemon=True).start()
                return
            if path not in {"/api/review", "/api/initialize"}:
                self.respond(404, {"error": "Not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 131072:
                    raise ValueError("Invalid form size.")
                values = json.loads(self.rfile.read(length))
                if not isinstance(values, dict):
                    raise ValueError("Invalid form data.")
                cfg = configure(values)
                errors = validate(cfg)
                if errors:
                    self.respond(400, {"error": "\n".join(errors)})
                    return
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                self.respond(400, {"error": str(exc) or "Check your project details."})
                return
            if path == "/api/review":
                self.respond(200, cfg)
                return
            with lock:
                if state["phase"] in {"running", "complete"}:
                    self.respond(409, {"error": "This project is already being initialized."})
                    return
                state.update(phase="running", log=[], error="")
            threading.Thread(target=work, args=(cfg,), daemon=False).start()
            self.respond(200, {"ok": True})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    address = "http://127.0.0.1:" + str(server.server_port)
    url = address + "/?session=" + token
    print("FusionFix setup: " + url, flush=True)
    print("Runs locally. Choose Exit setup to close, or press Ctrl+C here.", flush=True)
    if ready:
        ready(url)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


HTML = r'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>FusionFix · New plugin</title>
<style>
:root{color-scheme:dark;--text:#eef3fc;--muted:#8f9caf;--line:#ffffff12;--accent:#8ebdff;--panel:#17213191;--field:#09111d70}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:#0a101c;color:var(--text);font:14px/1.5 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;letter-spacing:.01em}
body:before,body:after{content:"";position:fixed;width:650px;height:650px;border-radius:50%;pointer-events:none;filter:blur(100px);z-index:-1}body:before{background:#24568a50;top:-310px;left:8%}body:after{background:#217e7740;bottom:-400px;right:-150px}
button,input,select,textarea{font:inherit}button{cursor:pointer}button:disabled{cursor:wait;opacity:.5}button,input,select,textarea{outline:none}button:focus-visible{outline:2px solid var(--accent);outline-offset:4px}input:focus,select:focus,textarea:focus{border-color:#88b9ff90;box-shadow:0 0 0 3px #70a9ff12}input,select,textarea{min-width:0;width:100%;background:var(--field);color:var(--text);border:1px solid #ffffff16;border-radius:10px;padding:12px 14px;transition:border-color .18s,box-shadow .18s}input::placeholder,textarea::placeholder{color:#637185}select option{background:#172233}input[type=checkbox]{width:17px;height:17px;accent-color:#83b8ff;padding:0}
button{border:1px solid var(--line);background:#ffffff07;color:var(--text);border-radius:11px;padding:10px 16px;transition:background .16s,transform .16s}button:hover{background:#ffffff10}button:active{transform:translateY(1px)}button.primary{background:#c8defe;color:#0e2544;border-color:#d2e4ff;font-weight:650;box-shadow:0 3px 16px #5c9deb1a}button.primary:hover{background:#e1edff}button.quiet{border-color:transparent;background:transparent;color:var(--muted)}button.quiet:hover{color:var(--text);background:#ffffff06}.small{font-size:12px}.muted{color:var(--muted)}.mono{font-family:Consolas,"Cascadia Code",monospace;font-size:12px}h1,h2,h3,p{margin:0}h1{font-size:34px;letter-spacing:-1.1px;line-height:1.2;font-weight:600}h2{font-size:17px;letter-spacing:-.3px;font-weight:600}.eyebrow{font-size:10px;letter-spacing:1.8px;font-weight:650;color:#8295af;text-transform:uppercase}.glass{background:linear-gradient(130deg,#ffffff07,#ffffff02),var(--panel);border:1px solid #ffffff12;box-shadow:0 20px 70px #00000018,inset 0 1px #ffffff05;backdrop-filter:blur(30px) saturate(140%);-webkit-backdrop-filter:blur(30px) saturate(140%)}
.shell{max-width:1360px;min-height:100vh;margin:auto;padding:28px;display:grid;grid-template-columns:200px minmax(0,1fr);gap:32px}.sidebar{padding:10px 4px;display:flex;flex-direction:column}.brand{display:flex;align-items:center;gap:12px;margin-bottom:56px;font-weight:650;font-size:16px}.brand-icon{height:36px;width:36px;border-radius:11px;background:linear-gradient(145deg,#d9e9ff,#7ca8e6);color:#132844;display:grid;place-items:center;font-size:13px;letter-spacing:-1px;box-shadow:0 4px 22px #8ebaff18}.brand small{display:block;color:var(--muted);font-size:11px;font-weight:400}.nav{display:flex;flex-direction:column;gap:7px}.nav button{display:flex;align-items:center;gap:13px;background:transparent;border-color:transparent;text-align:left;color:var(--muted);padding:12px;font-size:13px}.nav button.active{background:#8ebaff0e;border-color:#a7c8ff17;color:#d9e8ff}.nav svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:1.6}.sidebar-bottom{margin-top:auto;padding:40px 8px 4px}.sidebar-bottom p{font-size:11px;color:#6e7f95;margin-top:8px}.workspace{min-width:0}.topbar{display:flex;justify-content:space-between;align-items:center;height:45px;margin-bottom:30px}.crumb{color:var(--muted);font-size:12px}.crumb span{color:#d0daea}.pill{display:inline-flex;align-items:center;border:1px solid var(--line);border-radius:99px;padding:5px 10px;color:#a8b8cb;font-size:11px;background:#ffffff04}.heading{margin-bottom:28px}.heading p{margin-top:10px;color:var(--muted);font-size:14px}.main-grid{display:grid;grid-template-columns:minmax(0,1fr) 248px;gap:22px;align-items:start}.card{border-radius:22px;padding:26px}.section-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.targets{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.target{display:flex;flex-direction:column;align-items:flex-start;text-align:left;padding:16px 14px;border-radius:14px;position:relative;min-height:122px;background:#0b13204d}.target[aria-checked=true]{border-color:#8ebaff88;background:linear-gradient(140deg,#8bbaff15,#5b8fcb0a);box-shadow:inset 0 0 25px #78aaff06}.target[aria-checked=true]:after{content:"";position:absolute;width:6px;height:6px;border-radius:50%;right:12px;top:12px;background:#b8d8ff;box-shadow:0 0 10px #a2cdff66}.target svg{width:25px;height:25px;stroke:#9faec2;fill:none;stroke-width:1.4;margin-bottom:12px}.target[aria-checked=true] svg{stroke:#c5deff}.target strong{font-size:13px;font-weight:600}.target small{font-family:Consolas,monospace;font-size:11px;color:var(--muted);margin-top:3px}.platform-note{min-height:36px;font-size:12px;color:var(--muted);margin-top:14px}.divider{height:1px;background:var(--line);margin:24px 0}.fields{display:grid;gap:18px}.field{display:block}.field-label{display:flex;align-items:center;justify-content:space-between;margin-bottom:7px;font-size:12px;color:#c0cdde;font-weight:500}.hint{display:block;color:#8799af;font-size:11px;margin-top:7px}.inline{display:flex;gap:12px;align-items:center}.inline>*{flex:1}.link-button{background:none!important;border:0;color:var(--accent);padding:0;font-size:11px;flex:0 0 auto}.input-wrap{position:relative}.input-wrap input{padding-right:56px}.suffix{position:absolute;right:13px;top:14px;color:#8094ad;font-size:11px;pointer-events:none}.segmented{display:flex;border:1px solid #ffffff14;border-radius:10px;background:#09111d70;padding:4px;gap:4px}.segmented button{flex:1;border:0;color:var(--muted);font-size:12px;background:none;padding:8px}.segmented button.active{background:#a6cbff17;color:#d7e8ff;box-shadow:0 1px 3px #0002}.platform-fields{margin-top:20px}.platform-fields .fields{gap:14px}.preview{padding:23px;position:sticky;top:28px}.preview-icon{width:55px;height:65px;border:1px solid #b0d3ff32;background:linear-gradient(135deg,#8fbfff1a,#6093c408);border-radius:12px;display:grid;place-items:center;color:#aecffe;font:14px Consolas,monospace;margin:24px 0 16px;box-shadow:0 8px 24px #0001}.preview-name{font-weight:550;font-size:15px;overflow-wrap:anywhere;letter-spacing:-.2px}.preview dl{margin:22px 0 0}.preview dt{color:#879bb4;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-top:17px}.preview dd{margin:5px 0 0;font-size:12px;color:#c0cddd;overflow-wrap:anywhere}.preview-footer{border-top:1px solid var(--line);margin-top:24px;padding-top:18px;color:#8a9cb3;font-size:11px;display:flex;gap:8px}.footer{display:flex;align-items:center;justify-content:space-between;padding:22px 2px;gap:16px}.footer-note{font-size:11px;color:#899bb3}.footer button{min-width:160px}[hidden]{display:none!important}.panel>.card{margin-bottom:18px}.module{padding:15px 0;border-bottom:1px solid var(--line)}.module:last-child{border:0}.module-row{display:flex;align-items:center;gap:12px}.module-row label{display:flex;align-items:center;gap:10px;flex:1;cursor:pointer}.module-row small{color:var(--muted);font-size:11px}.module details{margin-left:27px;margin-top:8px}.module summary{font-size:11px;color:#8c9fb7;cursor:pointer}.module input[type=text]{font-size:11px;padding:8px}.options-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:18px}.toggle-row{display:flex;align-items:center;gap:10px;font-size:12px;color:#bac8da;margin:14px 0;cursor:pointer}.notice{border:1px solid #7eaded22;background:#70a7e408;border-radius:12px;padding:14px;color:#a2b9d3;font-size:12px;line-height:1.7}.error{color:#ffb6b6;background:#f9777710;border:1px solid #f9777733;padding:13px 16px;border-radius:12px;white-space:pre-line;font-size:12px;margin-bottom:18px}dialog{width:min(620px,calc(100vw - 32px));max-height:90vh;padding:30px;border-radius:24px;color:var(--text);background:#172131e8;border:1px solid #ffffff24;box-shadow:0 35px 150px #0008;backdrop-filter:blur(40px);overflow:auto}dialog::backdrop{background:#050b1688;backdrop-filter:blur(9px)}.dialog-header{margin-bottom:22px}.dialog-header p{color:var(--muted);margin-top:9px;font-size:13px}.review-list{display:grid;grid-template-columns:130px 1fr;gap:13px;font-size:12px;padding:20px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:20px 0}.review-list dt{color:var(--muted)}.review-list dd{margin:0;overflow-wrap:anywhere}.dialog-actions{display:flex;justify-content:space-between;gap:12px;margin-top:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.8 Consolas,monospace;color:#a1b6ce;background:#080f1980;padding:16px;border:1px solid var(--line);border-radius:12px;max-height:280px;overflow:auto}.progress{height:3px;background:#ffffff0b;overflow:hidden;border-radius:5px;margin:20px 0}.progress:after{content:"";display:block;width:35%;height:100%;background:#b6d6ff;animation:scan 1.5s ease-in-out infinite}.progress.done:after{width:100%;animation:none;background:#94ceb9}@keyframes scan{from{transform:translateX(-100%)}to{transform:translateX(380%)}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}@media(max-width:1150px){.shell{grid-template-columns:170px minmax(0,1fr);gap:20px;padding:20px}.main-grid{grid-template-columns:minmax(0,1fr)}.preview{display:none}.brand{margin-bottom:45px}}@media(max-width:700px){.shell{display:block;padding:16px}.sidebar{padding:0}.brand{margin-bottom:18px}.nav{flex-direction:row;margin-bottom:18px}.nav button{padding:10px}.sidebar-bottom,.topbar{display:none}.heading{margin:20px 0}.card{padding:20px}h1{font-size:28px}.options-grid{grid-template-columns:1fr}.targets{gap:7px}.target{padding:12px 10px}.footer-note{max-width:160px}.review-list{grid-template-columns:100px 1fr}}
</style></head><body>
<div class="shell">
<aside class="sidebar">
 <div class="brand"><div class="brand-icon">FF</div><div>FusionFix<small>Project setup</small></div></div>
 <nav class="nav" aria-label="Setup sections">
  <button class="active" data-page="project" aria-current="page"><svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5zM3 12l9 5 9-5M3 16l9 5 9-5"/></svg>Project</button>
  <button data-page="dependencies" id="dependency-nav"><svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><path d="M17.5 14v7M14 17.5h7"/></svg>Dependencies</button>
  <button data-page="options"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3" fill="#111c2b"/><circle cx="16" cy="17" r="3" fill="#111c2b"/></svg>Preferences</button>
 </nav>
 <div class="sidebar-bottom"><button class="quiet small" id="exit" style="padding:12px 0;margin-top:8px">Exit setup ↗</button></div>
</aside>
<main class="workspace">
 <div class="topbar"><div class="crumb">Workspace <span style="margin:0 10px;color:#4b5b72">/</span> <span>New plugin</span></div><span class="pill">FusionFix Template</span></div>
 <header class="heading"><div class="eyebrow" style="margin-bottom:12px">New project</div><h1 id="page-title">Project setup</h1><p id="page-description">Select a plugin type and enter the repository details.</p></header>
 <div id="error" class="error" role="alert" hidden></div>
 <div class="main-grid"><div>
 <section class="panel" id="project">
  <div class="card glass">
   <div class="section-head"><h2>Choose a platform</h2></div>
   <div class="targets" role="radiogroup" aria-label="Plugin platform">
    <button class="target" role="radio" aria-checked="true" data-target="windows"><svg viewBox="0 0 24 24"><path d="m3 5 8-1v8H3zm10-1 8-1v9h-8zM3 14h8v7l-8-1zm10 0h8v9l-8-1z"/></svg><strong>Windows</strong><small>.asi plugin</small></button>
    <button class="target" role="radio" aria-checked="false" data-target="psp"><svg viewBox="0 0 28 24"><rect x="1" y="5" width="26" height="15" rx="5"/><rect x="8" y="8" width="12" height="9" rx="1"/><path d="M3 12h4M5 10v4M23 10v1M23 14v1"/></svg><strong>PSP</strong><small>.prx plugin</small></button>
    <button class="target" role="radio" aria-checked="false" data-target="pcsx2"><svg viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 5v11M11 5v11M14 5v11M16 19h1"/></svg><strong>PCSX2F</strong><small>.elf plugin</small></button>
   </div>
   <p class="platform-note" id="platform-note"></p>
   <div class="divider"></div>
   <div class="section-head"><h2>Repository</h2></div>
   <div class="fields">
    <label class="field"><span class="field-label">Project name</span><span class="input-wrap" style="display:block"><input id="project_name" placeholder="GameName.FusionFix" autocomplete="off" spellcheck="false"><span class="suffix" id="name-suffix">.asi</span></span></label>
    <div class="field"><span class="field-label"><label for="repo_url">GitHub repository</label><button type="button" class="link-button" id="relink" hidden>Use project name</button></span><input id="repo_url" aria-describedby="repo-hint" spellcheck="false" autocomplete="off"><span class="hint" id="repo-hint">Repository name follows your project name.</span></div>
   </div>
   <div class="platform-fields" id="windows-fields"><div class="field-label">Architecture</div><div class="segmented" aria-label="Architecture"><button data-arch="x86">x86 / Win32</button><button data-arch="x64" class="active">x64</button></div></div>
   <div class="platform-fields" id="emulator-fields" hidden>
    <div class="field-label">Source language</div><div class="segmented" aria-label="Source language"><button data-language="C" class="active">C</button><button data-language="C++">C++</button></div>
    <div id="psp-fields" class="fields" style="margin-top:18px">
     <label><span class="field-label">Internal game module</span><input id="game_module" placeholder="e.g. GTA3" spellcheck="false"><span class="hint">The module name reported by the PSP game executable.</span></label>
     <label><span class="field-label">Disc IDs</span><input id="disc_ids" placeholder="ULUS10041, ULES00182" spellcheck="false"><span class="hint">Separate supported game IDs with commas.</span></label>
    </div>
    <div id="pcsx2-fields" class="fields" style="margin-top:18px" hidden>
     <label><span class="field-label">Game CRCs</span><input id="crcs" placeholder="4F32A11F, 7EA439F5" spellcheck="false"><span class="hint">Eight hexadecimal digits per CRC, separated by commas.</span></label>
     <label><span class="field-label">Load address</span><input id="base" value="0x02100000" spellcheck="false"><span class="hint">Reserve this address in extended memory; avoid overlapping plugins.</span></label>
    </div>
   </div>
  </div>
 </section>
 <section class="panel" id="dependencies" hidden>
  <div class="card glass"><div class="section-head"><h2>Libraries & helpers</h2><span class="pill">Git submodules</span></div><p class="muted small" style="margin-bottom:14px">Required libraries are included. Other libraries are optional.</p><div id="modules"></div>
   <div id="sdk-game" hidden style="margin-top:20px"><label><span class="field-label">plugin-sdk game</span><select id="plugin_sdk_game"></select><span class="hint">Architecture is selected to match the game.</span></label></div>
   <div class="divider"></div><button id="add-module" class="quiet small">＋ Add a custom submodule</button>
  </div>
 </section>
 <section class="panel" id="options" hidden>
  <div class="card glass"><div class="section-head"><h2>Build settings</h2><span class="pill">Optional</span></div>
   <div class="options-grid"><label><span class="field-label">Visual Studio</span><select id="premake_version"></select></label><label><span class="field-label">License</span><select id="license"></select></label><label><span class="field-label">Default branch</span><input id="branch" value="main"></label></div>
  </div>
  <div class="card glass"><h2>Local debugging</h2><p class="muted small" style="margin:7px 0 20px">Saved in your local .env. Never committed.</p><div class="fields">
   <label><span class="field-label" id="directory-label">Game directory</span><input id="game_path" placeholder="C:/Games/MyGame" spellcheck="false"></label>
   <label><span class="field-label" id="executable-label">Game executable</span><input id="game_exe" placeholder="Game.exe" spellcheck="false"><span class="hint" id="executable-hint">Optional. Relative to the directory above.</span></label>
  </div><p class="hint" style="margin-top:16px">Builds replace an already installed plugin and preserve its INI.</p></div>
  <div class="card glass" id="native-options"><h2>Windows options</h2><div class="options-grid" style="margin-top:20px"><label><span class="field-label">Plugin folder</span><input id="script_subdir" value="plugins/"></label><label><span class="field-label">Steam App ID</span><input id="steam_app_id" placeholder="Optional" inputmode="numeric"></label></div>
   <label class="toggle-row"><input type="checkbox" id="run_git_sm" checked>Initialize library submodules</label>
   <label class="toggle-row"><input type="checkbox" id="enable_signing">Enable code signing</label>
   <label class="toggle-row"><input type="checkbox" id="has_embpdb" checked>Embed debugging symbols with EmbedPDB</label>
  </div>
  <div class="card glass"><h2>Repository & packaging</h2><label class="toggle-row"><input type="checkbox" id="run_commit" checked>Create an initial Git commit</label><label style="display:block;margin-top:20px"><span class="field-label">Extra files or folders to package</span><textarea id="extra_paths" rows="3" placeholder="One path per line"></textarea></label></div>
 </section>
 <footer class="footer"><span class="footer-note">Review settings before applying changes.</span><button class="primary" id="review" disabled>Review setup <span style="margin-left:15px">→</span></button></footer>
 </div>
 <aside class="preview card glass" aria-label="Project preview"><div class="eyebrow">Output preview</div><div class="preview-icon" id="preview-extension">.asi</div><div class="preview-name" id="preview-name">Untitled plugin</div><p class="muted small" id="preview-platform" style="margin-top:6px">Windows · C++</p><dl><dt>Toolchain</dt><dd id="preview-toolchain">Visual Studio 2026</dd><dt>Repository</dt><dd id="preview-repo">Fusion-Fix / …</dd><dt>Output</dt><dd class="mono" id="preview-output">data/plugins/</dd></dl><div class="preview-footer"><span>↳</span><span id="preview-footnote">CI uses the selected dependencies.</span></div></aside>
 </div>
</main></div>
<dialog id="review-dialog" aria-labelledby="review-title"><div class="dialog-header"><h1 id="review-title" style="font-size:27px">Review setup</h1><p>Initialize this checkout with the settings below.</p></div><dl class="review-list" id="review-list"></dl><div class="notice" id="review-notice"></div><div class="dialog-actions"><button id="back">Back</button><button id="initialize" class="primary">Initialize project →</button></div></dialog>
<dialog id="progress-dialog" aria-labelledby="progress-title"><div class="eyebrow" style="margin-bottom:12px">Project setup</div><h1 id="progress-title" style="font-size:27px">Initializing project…</h1><p class="muted small" id="progress-description" style="margin-top:10px">Preparing files and dependencies. This may take a few minutes.</p><div class="progress" id="progress-bar"></div><pre id="log" aria-live="polite">Starting…</pre><div id="progress-error" class="error" hidden></div><div class="dialog-actions"><button id="retry" hidden>Back to setup</button><button id="done" class="primary" hidden>Done</button></div></dialog>
<script>
'use strict';
const $=id=>document.getElementById(id),session=new URL(location.href).searchParams.get('session');
let catalog,target='windows',architecture='x64',language='C',repoAuto=true,modules=[],busy=false,reviewValues;
const localValues={},extensions={windows:'.asi',psp:'.prx',pcsx2:'.elf'},names={windows:'Windows',psp:'PSP',pcsx2:'PCSX2F'};
const textFields=['project_name','repo_url','game_module','disc_ids','crcs','base','plugin_sdk_game','premake_version','license','branch','game_path','game_exe','script_subdir','steam_app_id','extra_paths'];
const checks=['run_git_sm','run_commit','enable_signing','has_embpdb'];
async function api(path,body){const response=await fetch('/api/'+path,{method:body===undefined?'GET':'POST',headers:{'X-Setup-Session':session,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');return result}
function error(message){$('error').textContent=message;$('error').hidden=!message;if(message)$('error').scrollIntoView({behavior:'smooth',block:'center'})}
function showPage(page){document.querySelectorAll('.panel').forEach(el=>el.hidden=el.id!==page);document.querySelectorAll('[data-page]').forEach(el=>{const active=el.dataset.page===page;el.classList.toggle('active',active);if(active)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current')});const titles={project:['Project setup','Select a plugin type and enter the repository details.'],dependencies:['Dependencies','Select optional libraries and configure submodule paths.'],options:['Preferences','Build, debugging and packaging settings.']};$('page-title').textContent=titles[page][0];$('page-description').textContent=titles[page][1]}
function followName(){const match=$('repo_url').value.match(/^(https:\/\/github\.com\/[^/]+)(?:\/.*)?$/);const owner=match?match[1]:'https://github.com/Fusion-Fix';$('repo_url').value=owner+'/'+$('project_name').value.trim()}
function linkedState(){$('relink').hidden=repoAuto;$('repo-hint').textContent=repoAuto?'Repository name follows your project name.':'Custom repository URL. It will stay as entered.'}
function syncSDK(){const sdk=modules.find(m=>m.name==='plugin-sdk');$('sdk-game').hidden=!sdk?.enabled;if(target==='windows'&&sdk?.enabled)architecture=catalog.games.find(g=>g.name===$('plugin_sdk_game').value)?.architecture||architecture;update()}
function selectTarget(next){localValues[target]={path:$('game_path').value,exe:$('game_exe').value};if(next!==target){$('game_path').value=localValues[next]?.path||'';$('game_exe').value=localValues[next]?.exe||''}target=next;const native=target==='windows';$('dependency-nav').hidden=!native;if(!native&&!$('dependencies').hidden)showPage('project');$('native-options').hidden=!native;$('windows-fields').hidden=!native;$('emulator-fields').hidden=native;$('psp-fields').hidden=target!=='psp';$('pcsx2-fields').hidden=target!=='pcsx2';$('directory-label').textContent=native?'Game directory':'Emulator directory';$('executable-label').textContent=native?'Game executable':'Emulator executable';$('game_path').placeholder=native?'C:/Games/MyGame':'C:/Emulators/'+(target==='psp'?'PPSSPP':'PCSX2F');$('game_exe').placeholder=native?'Game.exe':target==='psp'?'PPSSPPWindows64.exe':'pcsx2-qtx64-clang.exe';$('executable-hint').textContent=native?'Optional. Relative to the directory above.':'Optional. Leave empty to use '+$('game_exe').placeholder+'.';$('platform-note').textContent={windows:'A native Windows plugin, loaded through an ASI loader.',psp:'A PPSSPP guest plugin. Includes helper sources and the pspsdk submodule.',pcsx2:'A guest PS2 plugin for PCSX2F / Plugin Injector, with ps2sdk included.'}[target];syncSDK()}
function update(){document.querySelectorAll('[data-target]').forEach(el=>el.setAttribute('aria-checked',el.dataset.target===target));document.querySelectorAll('[data-arch]').forEach(el=>{el.disabled=target==='windows'&&!!modules.find(m=>m.name==='plugin-sdk'&&m.enabled);el.title=el.disabled?'Selected by plugin-sdk game':'';el.classList.toggle('active',el.dataset.arch===architecture);el.setAttribute('aria-pressed',el.dataset.arch===architecture)});document.querySelectorAll('[data-language]').forEach(el=>{el.classList.toggle('active',el.dataset.language===language);el.setAttribute('aria-pressed',el.dataset.language===language)});const ext=extensions[target],name=$('project_name').value.trim();$('name-suffix').textContent=ext;$('preview-extension').textContent=ext;$('preview-name').textContent=name?name+ext:'Untitled plugin';$('preview-platform').textContent=names[target]+' · '+(target==='windows'?'C++ / '+architecture:language);$('preview-toolchain').textContent=target==='windows'?$('premake_version').value.replace('vs','Visual Studio '):target==='psp'?'PSPSDK · MIPS':'PS2SDK · Emotion Engine';$('preview-repo').textContent=$('repo_url').value.replace('https://github.com/','').replace('/',' / ')||'Not set';$('preview-output').textContent=target==='windows'?'data/'+($('script_subdir').value||''):target==='psp'?'memstick/PSP/PLUGINS/'+(name||'…')+'/':'PLUGINS/';$('preview-footnote').textContent=target==='windows'?'CI uses the selected dependencies.':'Helpers download from GitHub. The SDK is added as a Git submodule.'}
function renderModules(){const host=$('modules');host.replaceChildren();modules.forEach((m,index)=>{const row=document.createElement('div');row.className='module';const line=document.createElement('div');line.className='module-row';const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=m.enabled;check.disabled=m.required;check.addEventListener('change',()=>{m.enabled=check.checked;syncSDK()});label.append(check,document.createTextNode(m.name));line.append(label);const tag=document.createElement('small');tag.textContent=m.required?'Included':'Optional';line.append(tag);row.append(line);const details=document.createElement('details'),summary=document.createElement('summary');summary.textContent='Path & source';details.append(summary);const fields=document.createElement('div');fields.className='fields';fields.style.marginTop='10px';for(const key of ['path','url']){const input=document.createElement('input');input.type='text';input.value=m[key];input.setAttribute('aria-label',m.name+' '+key);input.addEventListener('input',()=>m[key]=input.value);fields.append(input)}details.append(fields);row.append(details);if(m.custom){const remove=document.createElement('button');remove.className='link-button';remove.textContent='Remove';remove.addEventListener('click',()=>{modules.splice(index,1);renderModules()});line.append(remove)}host.append(row)})}
function values(){const result={target,architecture,language,submodules:modules.map(m=>({...m}))};for(const key of textFields)result[key]=$(key).value;for(const key of checks)result[key]=$(key).checked;return result}
function reviewRow(label,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=value;$('review-list').append(dt,dd)}
async function review(){error('');$('review').disabled=true;try{reviewValues=values();const cfg=await api('review',reviewValues),t=cfg.tokens;$('review-list').replaceChildren();reviewRow('Plugin',t.PROJECT_NAME+t.TARGET_EXTENSION);reviewRow('Platform',names[cfg.target]+' · '+(cfg.target==='windows'?'C++ / '+architecture:cfg.language));reviewRow('Repository',t.REPO_URL);reviewRow('Checkout',catalog.root);reviewRow('Dependencies',cfg.submodules.map(m=>m.name).join(', ')||'None');reviewRow('Build',t.PREMAKE_VS_VERSION.replace('vs','Visual Studio ')+' · '+t.LICENSE_SPDX);reviewRow('Git commit',cfg.run_commit?'Create initial commit':'Leave changes uncommitted');if(target!=='windows')reviewRow(target==='psp'?'Disc IDs':'Game CRCs',target==='psp'?cfg.disc_ids:cfg.crcs);$('review-notice').textContent='This updates the template in this checkout and removes the setup scripts when finished. '+(target==='windows'?(cfg.run_git_sm?'Selected submodules will be initialized.':'You will need to initialize library submodules manually.'):'Helpers will be downloaded from GitHub and the SDK submodule initialized.');$('review-dialog').showModal()}catch(e){error(e.message)}finally{$('review').disabled=false}}
async function poll(){try{const state=await api('status');$('log').textContent=state.log.join('\n')||'Preparing dependencies…';$('log').scrollTop=$('log').scrollHeight;if(state.phase==='running'){setTimeout(poll,700);return}busy=false;$('progress-bar').classList.add('done');if(state.phase==='complete'){$('progress-title').textContent='Setup complete';$('progress-description').textContent='Run premake5.bat to generate your Visual Studio solution.';$('done').hidden=false}else{$('progress-title').textContent='Setup failed';$('progress-description').textContent='Check the details below before continuing.';$('progress-error').textContent=state.error;$('progress-error').hidden=false;$('retry').hidden=false}}catch(e){$('progress-description').textContent='Connection interrupted. Keep this page open while reconnecting…';setTimeout(poll,2000)}}
async function initialize(){if(busy)return;busy=true;$('initialize').disabled=true;try{await api('initialize',reviewValues);$('review-dialog').close();$('progress-dialog').showModal();$('progress-error').hidden=true;$('retry').hidden=true;$('progress-bar').classList.remove('done');$('progress-title').textContent='Initializing project…';$('progress-description').textContent='Preparing files and dependencies. This may take a few minutes.';poll()}catch(e){busy=false;error(e.message);$('review-dialog').close()}finally{$('initialize').disabled=false}}
async function closeSetup(){try{await api('close',{});document.body.replaceChildren();const div=document.createElement('div');div.style.cssText='max-width:500px;margin:20vh auto;padding:32px;text-align:center';const title=document.createElement('h1');title.textContent='Setup closed';const p=document.createElement('p');p.className='muted';p.style.marginTop='16px';p.textContent='Setup has closed. You can close this tab.';div.append(title,p);document.body.append(div)}catch(e){error(e.message)}}
document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.page)));
document.querySelectorAll('[data-target]').forEach(el=>{el.addEventListener('click',()=>selectTarget(el.dataset.target));el.addEventListener('keydown',event=>{if(!['ArrowRight','ArrowLeft'].includes(event.key))return;event.preventDefault();const buttons=[...document.querySelectorAll('[data-target]')],next=buttons[(buttons.indexOf(el)+(event.key==='ArrowRight'?1:2))%3];next.focus();selectTarget(next.dataset.target)})});
document.querySelectorAll('[data-arch]').forEach(el=>el.addEventListener('click',()=>{architecture=el.dataset.arch;update()}));document.querySelectorAll('[data-language]').forEach(el=>el.addEventListener('click',()=>{language=el.dataset.language;update()}));
$('project_name').addEventListener('input',()=>{if(repoAuto)followName();update()});$('repo_url').addEventListener('input',()=>{repoAuto=false;linkedState();update()});$('relink').addEventListener('click',()=>{repoAuto=true;followName();linkedState();update()});$('plugin_sdk_game').addEventListener('change',syncSDK);$('premake_version').addEventListener('change',update);$('script_subdir').addEventListener('input',update);$('review').addEventListener('click',review);$('back').addEventListener('click',()=>$('review-dialog').close());$('initialize').addEventListener('click',initialize);$('progress-dialog').addEventListener('cancel',event=>event.preventDefault());$('retry').addEventListener('click',()=>$('progress-dialog').close());$('exit').addEventListener('click',closeSetup);$('done').addEventListener('click',closeSetup);
$('add-module').addEventListener('click',()=>{modules.push({name:'custom-'+Date.now(),path:'external/custom',url:'https://github.com/',enabled:true,custom:true});renderModules();const details=$('modules').lastElementChild.querySelector('details');details.open=true;details.scrollIntoView({behavior:'smooth',block:'center'})});
window.addEventListener('beforeunload',event=>{if(busy){event.preventDefault();event.returnValue=''}});
(async()=>{try{catalog=await api('defaults');const d=catalog.defaults;modules=catalog.submodules;for(const [id,items] of [['license',catalog.licenses],['premake_version',catalog.versions],['plugin_sdk_game',catalog.games.map(g=>g.name)]]){for(const value of items){const option=document.createElement('option');option.value=id==='license'?value.id:value;option.textContent=id==='license'?value.name+' ('+value.id+')':id==='premake_version'?value.replace('vs','Visual Studio '):value;$(id).append(option)}}for(const key of ['game_module','disc_ids','crcs','base'])if(d[key]!==undefined)$(key).value=d[key];$('project_name').value=d.project_name==='GameName.FusionFix'?'':d.project_name||'';$('repo_url').value=d.repo_url||'https://github.com/Fusion-Fix/';repoAuto=!d.repo_url||d.repo_url.replace(/\/$/,'').replace(/\.git$/,'').endsWith('/'+(d.project_name||''));if(repoAuto)followName();$('license').value=['GPL-3.0 license','GPL-3.0'].includes(d.license_spdx)?'GPL-3.0-only':d.license_spdx||'MIT';$('premake_version').value=d.premake_vs_version||'vs2026';$('plugin_sdk_game').value=d.plugin_sdk_game||'GTA III';$('branch').value=d.default_branch||'main';$('game_exe').value=d.game_executable||'';$('steam_app_id').value=d.steam_app_id||'';$('run_git_sm').checked=d.run_git_submodule_add!==false;$('run_commit').checked=d.run_initial_commit!==false;$('enable_signing').checked=!!d.enable_code_signing;architecture=d.architecture||'x64';language=d.language||'C';target=d.target||'windows';renderModules();linkedState();selectTarget(target);$('review').disabled=false;const state=await api('status');if(state.phase!=='idle'){busy=state.phase==='running';$('progress-dialog').showModal();poll()}}catch(e){error('Could not load setup: '+e.message);$('review').disabled=true}})();
</script></body></html>'''
