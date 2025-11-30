import os
import sys
import queue
import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from config import VOSK_MODEL_PATH, MIC_DEVICE_INDEX, WAKE_WORDS


class RobotEars:
    def __init__(self):
        if not os.path.exists(VOSK_MODEL_PATH):
            print(f"Error: Model not found at {VOSK_MODEL_PATH}")
            sys.exit(1)

        self.model = Model(VOSK_MODEL_PATH)
        self.fs = 16000
        self.q = queue.Queue()

    def _callback(self, indata, frames, time, status):
        self.q.put(bytes(indata))

    def listen_once(self, timeout=10, check_wake_word=False):
        """
        监听一次语音输入。
        check_wake_word: 如果为True，只返回包含唤醒词的结果。
        """
        rec = KaldiRecognizer(self.model, self.fs)
        buffer_text = ""

        print(f"🎤 Listening... (Wake: {check_wake_word})")

        with sd.RawInputStream(samplerate=self.fs, blocksize=8000, device=MIC_DEVICE_INDEX,
                               dtype='int16', channels=1, callback=self._callback):
            start_time = import_time.time()
            while True:
                # 超时控制
                if import_time.time() - start_time > timeout:
                    return None

                try:
                    data = self.q.get(timeout=1)
                except queue.Empty:
                    continue

                if rec.AcceptWaveform(data):
                    res = json.loads(rec.Result())
                    text = res.get("text", "").replace(" ", "")
                    if text:
                        if check_wake_word:
                            # 检查是否包含任何唤醒词
                            if any(w in text for w in WAKE_WORDS):
                                return text
                        else:
                            return text
        return None


# 为了避免通过 import time 导致的命名冲突，这里做一个小补丁
import time as import_time