"""Listen for a short Mandarin command on the computer; never send or save audio."""
from collections import deque
import json
from pathlib import Path
from threading import Event, Thread

ROOT=Path(__file__).resolve().parents[1]


class Voice:
    commands = ('清 个 屏', '清 屏', '清 理 一 下 空 间', '清 一 下 屏', '开 始 打 球',
                '清 一 下 空 间', '清 理 空 间', '打 羽 毛 球', '[unk]')

    def __init__(self):
        self.stop = Event()
        self.active = Event()
        self.status = '正在准备语音…'
        self.phrases = {s.replace(' ','') for s in self.commands[:-1]}
        self.request = 0
        Thread(target=self._run, name='offline voice', daemon=True).start()

    def _run(self):
        try:
            import sounddevice as sd
            import vosk
            vosk.SetLogLevel(-1)
            model_path = ROOT/'assets'/'vosk-model-small-cn-0.22'
            if not (model_path/'am'/'final.mdl').is_file():
                self.status = '语音未安装 · Enter 开打'
                return
            # model_path is accepted as UTF-8 by Vosk. A relative ASCII path also works on older Windows builds.
            model = vosk.Model(str(model_path.relative_to(ROOT)))
            rate = round(sd.query_devices(kind='input')['default_samplerate'])
            recognizer = vosk.KaldiRecognizer(model, rate, json.dumps(self.commands, ensure_ascii=False))
            while not self.stop.is_set():
                if not self.active.wait(.18):
                    continue
                queue = deque(maxlen=12)
                with sd.RawInputStream(samplerate=rate, blocksize=max(1600,rate//10),
                                       dtype='int16', channels=1,
                                       callback=lambda indata,*_: queue.append(bytes(indata))):
                    recognizer.Reset()
                    self.status = '麦克风就绪'
                    while self.active.is_set() and not self.stop.is_set():
                        if not queue:
                            self.stop.wait(.03)
                            continue
                        if recognizer.AcceptWaveform(queue.popleft()):
                            said=json.loads(recognizer.Result()).get('text','').replace(' ','')
                            if said in self.phrases:
                                self.request += 1
                                recognizer.Reset()
                                self.active.clear()
        except Exception as e:
            print(f'[voice] {e}', flush=True)
            self.status = '麦克风不可用 · Enter 开打'

