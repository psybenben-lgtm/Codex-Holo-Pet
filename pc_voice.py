"""On-demand Windows speech, owned by the visible hub and its Stop button."""
import json
import subprocess
import sys
import threading

SCRIPT = r'''
$ErrorActionPreference = 'Stop'
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$zh = $voice.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN' } | Select-Object -First 1
if ($zh) { $voice.SelectVoice($zh.VoiceInfo.Name) }
$voice.Volume = [int]$data.volume
try { $voice.Speak([string]$data.text) } finally { $voice.Dispose() }
'''
lock = threading.Lock()
process = None
active_id = None
canceled = set()


def _win_hidden_kwargs():
    if sys.platform != 'win32':
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= getattr(subprocess, 'STARTF_USESHOWWINDOW', 0)
    si.wShowWindow = getattr(subprocess, 'SW_HIDE', 0)
    return {
        'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        'startupinfo': si,
    }

def stop(job_id=None):
    global process
    with lock:
        if job_id:
            canceled.add(job_id)
            if len(canceled) > 512:
                canceled.clear()
                canceled.add(job_id)
        if process is not None and (job_id is None or job_id == active_id):
            if process.poll() is None:
                process.terminate()

def speak(data):
    global process, active_id
    text = data.get('text', '')
    job_id = data.get('id', '')
    if not isinstance(text, str) or not 0 < len(text) <= 2000:
        raise ValueError('台词需为 1–2000 个字符')
    if not isinstance(job_id, str) or not 1 <= len(job_id) <= 100:
        raise ValueError('缺少播报编号')
    volume = max(0, min(100, int(float(data.get('volume', 1)) * 100)))
    payload = json.dumps(dict(text=text, volume=volume), ensure_ascii=True)
    with lock:
        if job_id in canceled:
            return dict(ok=False, canceled=True)
        if process is not None and process.poll() is None:
            process.terminate()
        proc = subprocess.Popen(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', SCRIPT],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                **_win_hidden_kwargs())
        process, active_id = proc, job_id
    print('[PC voice] Speaking; use the controller Stop button to cancel.', flush=True)
    try:
        _, error = proc.communicate(payload.encode('ascii'), timeout=240)
        with lock:
            was_canceled = job_id in canceled or active_id != job_id
        if was_canceled:
            return dict(ok=False, canceled=True)
        if proc.returncode:
            raise RuntimeError('Windows 语音播放失败，请检查系统语音和音量设置')
        print('[PC voice] Finished.', flush=True)
        return dict(ok=True, finished=True)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError('播报超时，已停止，请缩短台词后重试')
    finally:
        with lock:
            if process is proc:
                process, active_id = None, None
