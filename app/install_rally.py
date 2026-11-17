"""Install minimal core dependencies or full optional camera/voice extensions."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import argparse
import importlib.util
import os
import subprocess
import sys
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.rally-runtime'
ASSETS = ROOT / 'assets'
MODEL = ASSETS / 'hand_landmarker.task'
VOICE = ASSETS / 'vosk-model-small-cn-0.22'
HAND_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
VOICE_URL = 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip'
VOICE_SHA = '3af8b0e7e0f835ae9d414ce5df580237a3cfb08d586c9fbbb0f7ff29ad5b14ba'


def download(url):
    with urlopen(url, timeout=30) as r:
        return r.read()


def check_tkinter():
    try:
        import tkinter  # noqa: F401
        return True
    except Exception:
        print('========================================================================', flush=True)
        print('[错误] 当前 Python 缺少 tkinter 图形库（大概率是嵌入式 Python / Embedded 版）！', flush=True)
        print('透明桌面桌宠必须使用完整桌面版 Python（自带 tkinter）。', flush=True)
        print('请执行以下命令安装标准 64 位 Python 3.11（或交由 AI Agent 自动执行）：', flush=True)
        print('  winget install -e --id Python.Python.3.11 --scope user --accept-package-agreements --accept-source-agreements', flush=True)
        print('安装完成后，请使用新 Python 重新运行：python app/install_rally.py --core', flush=True)
        print('========================================================================', flush=True)
        return False


def install(core_only=False, with_voice=False):
    if not check_tkinter():
        raise RuntimeError('当前 Python 缺少 tkinter，请安装标准桌面版 Python 3.11')
    RUNTIME.mkdir(exist_ok=True)
    sys.path.insert(0, str(RUNTIME))
    py = [sys.executable, '-m', 'pip', '--disable-pip-version-check', 'install', '--target', str(RUNTIME)]

    core_pkgs = []
    for module, package in (('PIL', 'Pillow>=9.0.0'), ('qrcode', 'qrcode>=7.4')):
        if not importlib.util.find_spec(module):
            core_pkgs.append(package)
    if core_pkgs:
        print(f'[1/3] 正在安装轻量核心依赖 ({", ".join(core_pkgs)})...', flush=True)
        subprocess.run(py + core_pkgs, check=True)
    else:
        print('[1/3] 轻量核心依赖 Pillow / qrcode 已就绪！', flush=True)

    if core_only:
        print('已完成极简无摄像头安装（纯鼠标/按钮玩法 100% 就绪）！', flush=True)
        return

    print('[2/3] 正在安装可选本地摄像头 AI 手势与 HTTPS 扩展...', flush=True)
    extra = []
    for module, package in (('cv2', 'opencv-python-headless>=4.10'), ('cryptography', 'cryptography>=41')):
        if not importlib.util.find_spec(module):
            extra.append(package)
    if extra:
        subprocess.run(py + extra, check=True)
    try:
        subprocess.run(py + ['--no-deps', 'mediapipe==0.10.32'], check=True)
        subprocess.run(py + ['absl-py==2.3.1', 'flatbuffers==25.9.23', 'matplotlib>=3.9,<4', 'numpy>=1.26,<2.3'], check=True)
    except Exception as e:
        print(f'[提示] 摄像头视觉扩展安装受网络或系统版本影响未完全成功（{e}），不影响纯鼠标及三合一畅玩！', flush=True)

    if not MODEL.is_file():
        try:
            print('[3/3] 正在下载可选手部 21 关节点模型...', flush=True)
            MODEL.write_bytes(download(HAND_URL))
        except Exception as e:
            print(f'[提示] 手部模型下载失败（{e}），仍可使用纯鼠标模式。', flush=True)

    if with_voice and not (VOICE / 'am' / 'final.mdl').is_file():
        try:
            print('[可选] 正在安装离线普通话语音包 (约 65MB)...', flush=True)
            subprocess.run(py + ['sounddevice>=0.5,<0.6', 'vosk==0.3.45'], check=True)
            data = download(VOICE_URL)
            if sha256(data).hexdigest() == VOICE_SHA:
                with ZipFile(BytesIO(data)) as z:
                    z.extractall(ASSETS)
        except Exception as e:
            print(f'[提示] 可选离线语音包跳过：{e}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--core', action='store_true', help='仅安装核心轻量包 (Pillow + qrcode)，免装视觉大模型')
    parser.add_argument('--with-voice', action='store_true', help='额外安装离线语音包 (约65MB)')
    args = parser.parse_args()
    try:
        install(core_only=args.core, with_voice=args.with_voice)
    except Exception as e:
        print(f'安装未完成：{e}')
        sys.exit(1)
