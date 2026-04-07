#!/usr/bin/env python3
"""Voiceprint registration tool: browser mic recording + one-click register + auto-update config."""
import argparse, io, json, struct, subprocess, tempfile, os
from pathlib import Path
from flask import Flask, request, jsonify, Response
import requests, yaml

app = Flask(__name__)
API_URL = ""
API_KEY = ""
CONFIG_PATH = ""
SSH_CMD = ""

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Voiceprint Register</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#0f172a;color:#e2e8f0;display:flex;justify-content:center;padding:40px}
.wrap{max-width:480px;width:100%}
h1{font-size:1.4rem;margin-bottom:24px;color:#38bdf8}
label{display:block;font-size:.85rem;color:#94a3b8;margin:12px 0 4px}
input,textarea{width:100%;padding:8px 12px;border:1px solid #334155;border-radius:6px;background:#1e293b;color:#e2e8f0;font-size:.9rem}
textarea{resize:vertical;height:60px}
.btn-row{display:flex;gap:10px;margin-top:16px}
button{flex:1;padding:10px;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer;transition:background .2s}
.rec{background:#ef4444;color:#fff}.rec:hover{background:#dc2626}
.rec.active{background:#22c55e}.rec.active:hover{background:#16a34a}
.reg{background:#3b82f6;color:#fff}.reg:hover{background:#2563eb}
.reg:disabled{background:#334155;cursor:not-allowed}
.status{margin-top:16px;padding:10px;border-radius:6px;font-size:.85rem;display:none}
.status.ok{display:block;background:#064e3b;color:#6ee7b7}
.status.err{display:block;background:#7f1d1d;color:#fca5a5}
.status.info{display:block;background:#1e3a5f;color:#93c5fd}
.timer{text-align:center;font-size:2rem;color:#f59e0b;margin:12px 0;font-variant-numeric:tabular-nums}
audio{width:100%;margin-top:8px;border-radius:6px}
.list{margin-top:24px;border-top:1px solid #334155;padding-top:16px}
.list h2{font-size:1rem;color:#94a3b8;margin-bottom:8px}
.list-item{padding:6px 0;font-size:.85rem;color:#cbd5e1;border-bottom:1px solid #1e293b}
</style></head><body>
<div class="wrap">
<h1>Voiceprint Register</h1>
<label>Speaker ID</label><input id="sid" placeholder="e.g. xurui">
<label>Display Name</label><input id="sname" placeholder="e.g. Xu Rui">
<label>Description</label><textarea id="sdesc" placeholder="e.g. device owner, software engineer"></textarea>
<div style="margin:12px 0;padding:10px;background:#1e293b;border-radius:6px;border-left:3px solid #f59e0b">
<div style="font-size:.75rem;color:#f59e0b;margin-bottom:4px">Suggested script (read naturally, 5-10s):</div>
<div style="font-size:.85rem;color:#e2e8f0;line-height:1.5">"Hi, my name is [your name]. Today the weather is nice, perfect for a walk outside and enjoying some fresh air."</div>
</div>
<div class="timer" id="timer">00:00</div>
<div class="btn-row">
  <button class="rec" id="recBtn" onclick="toggleRec()">Start Recording</button>
  <button class="reg" id="regBtn" onclick="doRegister()" disabled>Register</button>
</div>
<audio id="preview" controls style="display:none"></audio>
<div class="status" id="status"></div>
<div class="list" id="listWrap"><h2>Registered Speakers</h2><div id="listBody">loading...</div></div>
</div>
<script>
var mediaRec=null,chunks=[],recording=false,blob=null,timerInt=null,sec=0;
function toggleRec(){
  if(!recording) startRec(); else stopRec();
}
async function startRec(){
  var stream=await navigator.mediaDevices.getUserMedia({audio:true});
  mediaRec=new MediaRecorder(stream,{mimeType:'audio/webm;codecs=opus'});
  chunks=[];sec=0;
  mediaRec.ondataavailable=function(e){if(e.data.size>0)chunks.push(e.data)};
  mediaRec.onstop=function(){
    blob=new Blob(chunks,{type:'audio/webm'});
    var url=URL.createObjectURL(blob);
    var au=document.getElementById('preview');au.src=url;au.style.display='block';
    document.getElementById('regBtn').disabled=false;
  };
  mediaRec.start();recording=true;
  document.getElementById('recBtn').textContent='Stop';
  document.getElementById('recBtn').classList.add('active');
  timerInt=setInterval(function(){sec++;var m=Math.floor(sec/60),s=sec%60;
    document.getElementById('timer').textContent=String(m).padStart(2,'0')+':'+String(s).padStart(2,'0');
  },1000);
}
function stopRec(){
  mediaRec.stop();mediaRec.stream.getTracks().forEach(function(t){t.stop()});
  recording=false;clearInterval(timerInt);
  document.getElementById('recBtn').textContent='Start Recording';
  document.getElementById('recBtn').classList.remove('active');
}
function showStatus(msg,type){var el=document.getElementById('status');el.textContent=msg;el.className='status '+type}
async function doRegister(){
  var sid=document.getElementById('sid').value.trim();
  var sname=document.getElementById('sname').value.trim();
  var sdesc=document.getElementById('sdesc').value.trim();
  if(!sid||!sname){showStatus('Please fill Speaker ID and Name','err');return}
  if(!blob){showStatus('Please record audio first','err');return}
  showStatus('Registering...','info');
  document.getElementById('regBtn').disabled=true;
  var fd=new FormData();
  fd.append('speaker_id',sid);fd.append('name',sname);fd.append('description',sdesc);
  fd.append('audio',blob,'recording.webm');
  try{
    var r=await fetch('/api/register',{method:'POST',body:fd});
    var j=await r.json();
    if(r.ok){showStatus(j.message||'Success','ok');loadList()}
    else{showStatus(j.error||'Failed','err')}
  }catch(e){showStatus('Network error: '+e,'err')}
  document.getElementById('regBtn').disabled=false;
}
async function loadList(){
  try{var r=await fetch('/api/speakers');var j=await r.json();
    var html='';j.forEach(function(s){html+='<div class="list-item">'+s+'</div>'});
    document.getElementById('listBody').textContent='';
    document.getElementById('listBody').insertAdjacentHTML('beforeend',html||'<div class="list-item">No speakers yet</div>');
  }catch(e){document.getElementById('listBody').textContent='Failed to load'}
}
loadList();
</script></body></html>"""


def convert_webm_to_wav(webm_data: bytes) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(webm_data)
        webm_path = f.name
    wav_path = webm_path.replace(".webm", ".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", webm_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
            capture_output=True, check=True, timeout=30,
        )
        with open(wav_path, "rb") as f:
            return f.read()
    finally:
        for p in [webm_path, wav_path]:
            try:
                os.unlink(p)
            except OSError:
                pass


def update_remote_config(speaker_id: str, name: str, description: str):
    entry = f"{speaker_id},{name},{description}"
    if SSH_CMD and CONFIG_PATH:
        script = (
            f"python3 -c \""
            f"import yaml; "
            f"p='{CONFIG_PATH}'; "
            f"d=yaml.safe_load(open(p)); "
            f"d.setdefault('voiceprint',{{}}).setdefault('speakers',[]); "
            f"e='{entry}'; "
            f"[s for s in d['voiceprint']['speakers'] if s.startswith('{speaker_id},')] or d['voiceprint']['speakers'].append(e); "
            f"yaml.dump(d,open(p,'w'),allow_unicode=True,default_flow_style=False)"
            f"\""
        )
        subprocess.run(SSH_CMD.split() + [script], capture_output=True, timeout=15)


def update_local_config(speaker_id: str, name: str, description: str):
    entry = f"{speaker_id},{name},{description}"
    p = Path(CONFIG_PATH)
    if not p.exists():
        return
    with open(p) as f:
        data = yaml.safe_load(f) or {}
    vp = data.setdefault("voiceprint", {})
    speakers = vp.setdefault("speakers", [])
    if not any(s.startswith(f"{speaker_id},") for s in speakers):
        speakers.append(entry)
    with open(p, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


@app.route("/")
def index():
    return Response(HTML_PAGE, content_type="text/html")


@app.route("/api/register", methods=["POST"])
def register():
    sid = request.form.get("speaker_id", "").strip()
    name = request.form.get("name", "").strip()
    desc = request.form.get("description", "").strip()
    audio = request.files.get("audio")
    if not sid or not name or not audio:
        return jsonify({"error": "Missing speaker_id, name, or audio"}), 400

    webm_data = audio.read()
    try:
        wav_data = convert_webm_to_wav(webm_data)
    except Exception as e:
        return jsonify({"error": f"Audio conversion failed: {e}"}), 500

    try:
        resp = requests.post(
            f"{API_URL}/voiceprint/register",
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={"file": ("audio.wav", wav_data, "audio/wav")},
            data={"speaker_id": sid},
            timeout=30,
        )
        if resp.status_code != 200:
            return jsonify({"error": f"API error {resp.status_code}: {resp.text}"}), 502
    except Exception as e:
        return jsonify({"error": f"API request failed: {e}"}), 502

    try:
        if SSH_CMD:
            update_remote_config(sid, name, desc)
        else:
            update_local_config(sid, name, desc)
    except Exception as e:
        return jsonify({"message": f"Voiceprint registered but config update failed: {e}"}), 200

    return jsonify({"message": f"Registered {name} ({sid}). Restart xiaozhi-server to take effect."})


@app.route("/api/speakers")
def speakers():
    if SSH_CMD and CONFIG_PATH:
        try:
            r = subprocess.run(
                SSH_CMD.split() + [f"cat {CONFIG_PATH}"],
                capture_output=True, text=True, timeout=10,
            )
            data = yaml.safe_load(r.stdout) or {}
        except Exception:
            data = {}
    else:
        p = Path(CONFIG_PATH)
        data = yaml.safe_load(open(p)) if p.exists() else {}
    return jsonify(data.get("voiceprint", {}).get("speakers", []))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Voiceprint registration server")
    parser.add_argument("--api-url", required=True, help="voiceprint-api base URL, e.g. http://82.156.17.28:8005")
    parser.add_argument("--api-key", required=True, help="voiceprint-api access key")
    parser.add_argument("--config-path", required=True, help="path to .config.yaml (local or remote)")
    parser.add_argument("--ssh", default="", help="SSH command prefix for remote config, e.g. 'ssh -i key user@host'")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    API_URL = args.api_url.rstrip("/")
    API_KEY = args.api_key
    CONFIG_PATH = args.config_path
    SSH_CMD = args.ssh

    print(f"Voiceprint API: {API_URL}")
    print(f"Config: {CONFIG_PATH}" + (f" (via {SSH_CMD})" if SSH_CMD else " (local)"))
    print(f"Open http://localhost:{args.port} in your browser")
    app.run(host="0.0.0.0", port=args.port, debug=False)
