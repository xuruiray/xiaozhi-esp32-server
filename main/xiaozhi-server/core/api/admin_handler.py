import os
import yaml
from aiohttp import web
from config.logger import setup_logging
from config.config_loader import get_project_dir

TAG = __name__

ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>xiaozhi config</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/codemirror@5/theme/dracula.min.css">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,system-ui,sans-serif;background:#1e1e2e;color:#cdd6f4;height:100vh;display:flex;flex-direction:column}
header{padding:12px 20px;background:#181825;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #313244}
header h1{font-size:16px;font-weight:600}
.actions{display:flex;gap:8px;align-items:center}
.status{font-size:13px;color:#6c7086;transition:color .3s}
.status.ok{color:#a6e3a1}
.status.err{color:#f38ba8}
button{padding:6px 16px;border:none;border-radius:6px;font-size:13px;cursor:pointer;font-weight:500}
#save{background:#89b4fa;color:#1e1e2e}
#save:hover{background:#74c7ec}
#save:disabled{background:#45475a;color:#6c7086;cursor:not-allowed}
.editor-wrap{flex:1;overflow:hidden}
.CodeMirror{height:100%!important;font-size:13px;font-family:'Fira Code',monospace}
</style>
</head>
<body>
<header>
<h1>xiaozhi config</h1>
<div class="actions">
<span class="status" id="status"></span>
<button id="save">Save &amp; Reload</button>
</div>
</header>
<div class="editor-wrap"><textarea id="editor"></textarea></div>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/lib/codemirror.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/codemirror@5/mode/yaml/yaml.min.js"></script>
<script>
const KEY = new URLSearchParams(location.search).get('key') || '';
const cm = CodeMirror.fromTextArea(document.getElementById('editor'), {
  mode: 'yaml', theme: 'dracula', lineNumbers: true, tabSize: 2, indentWithTabs: false, lineWrapping: true
});
const st = document.getElementById('status');
const btn = document.getElementById('save');
function setStatus(msg, ok) { st.textContent = msg; st.className = 'status ' + (ok ? 'ok' : 'err'); }
fetch('/admin/config?key=' + KEY).then(r => r.ok ? r.text() : Promise.reject(r.statusText))
  .then(t => { cm.setValue(t); setStatus('loaded', true); })
  .catch(e => setStatus('load failed: ' + e, false));
btn.addEventListener('click', () => {
  btn.disabled = true;
  setStatus('saving...', true);
  fetch('/admin/save?key=' + KEY, { method: 'POST', headers: {'Content-Type': 'text/plain'}, body: cm.getValue() })
    .then(r => r.json())
    .then(d => { setStatus(d.ok ? 'saved & reloaded' : d.error, d.ok); btn.disabled = false; })
    .catch(e => { setStatus('error: ' + e, false); btn.disabled = false; });
});
</script>
</body>
</html>"""


class AdminHandler:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()
        self.config_path = get_project_dir() + "data/.config.yaml"

    def _check_auth(self, request):
        auth_key = self.config.get("server", {}).get("auth_key", "")
        if not auth_key:
            return True
        key = request.query.get("key", "")
        return key == auth_key

    async def handle_page(self, request):
        if not self._check_auth(request):
            return web.Response(status=403, text="forbidden")
        return web.Response(text=ADMIN_HTML, content_type="text/html")

    async def handle_get_config(self, request):
        if not self._check_auth(request):
            return web.Response(status=403, text="forbidden")
        if not os.path.exists(self.config_path):
            return web.Response(status=404, text="config file not found")
        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read()
        return web.Response(text=content, content_type="text/plain")

    async def handle_save(self, request):
        if not self._check_auth(request):
            return web.json_response({"ok": False, "error": "forbidden"}, status=403)
        body = await request.text()
        try:
            yaml.safe_load(body)
        except yaml.YAMLError as e:
            return web.json_response({"ok": False, "error": f"YAML syntax error: {e}"})

        backup_path = self.config_path + ".bak"
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                old = f.read()
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(old)

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write(body)

        from core.utils.cache.manager import cache_manager, CacheType
        cache_manager.delete(CacheType.CONFIG, "main_config")

        self.logger.bind(tag=TAG).info("Config saved via /admin, cache invalidated")
        return web.json_response({"ok": True})
