import sys
import json
import queue
import os
import time
import speech_recognition as sr
from vosk import Model, KaldiRecognizer
from config import MIC_DEVICE_INDEX

# 设置你的 Vosk 模型路径
VOSK_MODEL_PATH = "model/vosk-model-small-cn-0.22"


class BackgroundEars:
    def __init__(self, engine_type='vosk'):
        """
        初始化耳朵
        :param engine_type: 'google' (在线) 或 'vosk' (离线本地)
        """
        self.engine_type = engine_type
        self.recognizer = sr.Recognizer()
        self.msg_queue = queue.Queue()
        self.stop_listening_func = None

        # ================== [关键优化 1: 调整灵敏度参数] ==================
        # 能量阈值：越低越灵敏，但噪音多。如果你环境安静，可以设为 300。
        # 如果环境嘈杂，设为 400-1000。动态阈值开启后会自动调整。
        self.recognizer.energy_threshold = 400
        self.recognizer.dynamic_energy_threshold = True  # 建议开启，适应环境变化

        # 说话结束的判断时间：这是减少延迟的核心。
        # 默认是 0.8s，改成 0.4s。意思是停顿 0.4s 就认为你说完了，立马开始识别。
        self.recognizer.pause_threshold = 0.4

        # 非说话状态的缓冲时间：保持短一点，减少处理开销
        self.recognizer.non_speaking_duration = 0.3

        # 录音时的短语限制，防止一直录个没完
        self.recognizer.phrase_threshold = 0.3

        # 预加载 Vosk 模型
        self.vosk_model = None
        if self.engine_type == 'vosk':
            if not os.path.exists(VOSK_MODEL_PATH):
                print(f"❌ Error: Vosk model not found at {VOSK_MODEL_PATH}")
                sys.exit(1)
            print(f"⏳ Loading Vosk model from {VOSK_MODEL_PATH}...")
            # gpu_init=False 显式关闭 GPU 以防某些环境报错，通常 CPU 够快了
            self.vosk_model = Model(VOSK_MODEL_PATH)
            print("✅ Vosk model loaded.")

    def start(self):
        """启动后台监听线程"""
        print(f"👂 Initializing Microphone for [{self.engine_type.upper()}] Speech...")

        try:
            # 初始化麦克风
            # sample_rate=16000 是 Vosk 模型的标准采样率，直接硬件匹配可以省去重采样时间
            self.mic = sr.Microphone(device_index=MIC_DEVICE_INDEX, sample_rate=16000)

            with self.mic as source:
                print(">>> Adjusting for ambient noise... (0.5s)")
                # 减少校准时间到 0.5s
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                print(f">>> Listening... (Threshold: {self.recognizer.energy_threshold})")

            # 启动后台监听
            # phrase_time_limit=10: 限制单句最长 10 秒，防止噪音导致一直不切断录音
            self.stop_listening_func = self.recognizer.listen_in_background(
                self.mic,
                self._callback,
                phrase_time_limit=10
            )
            print(f"👂 Background Ears Started ({self.engine_type} Engine)...")

        except Exception as e:
            print(f"❌ Error starting microphone: {e}")
            sys.exit(1)

    def stop(self):
        """停止监听"""
        if self.stop_listening_func:
            self.stop_listening_func(wait_for_stop=False)
            self.stop_listening_func = None
        print("👂 Ears Stopped.")

    def get_latest_text(self):
        try:
            return self.msg_queue.get_nowait()
        except queue.Empty:
            return None

    def _callback(self, recognizer, audio):
        """
        回调函数：当检测到一段语音结束时触发
        """
        start_time = time.time()  # 记录处理开始时间，用于调试延迟
        try:
            text = ""

            if self.engine_type == 'google':
                try:
                    text = recognizer.recognize_google(audio, language='zh-CN')
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    print(f"❌ Google API Error: {e}")

            elif self.engine_type == 'vosk':
                try:
                    # ================== [关键优化 2: 直接处理 Raw Data] ==================
                    # 获取原始数据，这里不需要 convert_rate 因为我们麦克风初始化就是 16000
                    audio_data = audio.get_raw_data(convert_rate=16000, convert_width=2)

                    if len(audio_data) == 0:
                        return

                    # 创建识别器 (每次 callback 创建一个新的识别器实例是安全的，也可以尝试复用但需要 Reset)
                    rec = KaldiRecognizer(self.vosk_model, 16000)
                    rec.AcceptWaveform(audio_data)

                    # 使用 FinalResult 获取最终结果
                    result_json = rec.FinalResult()
                    res = json.loads(result_json)
                    text = res.get('text', '')

                except Exception as e:
                    print(f"❌ Vosk Processing Error: {e}")

            # 结果清理
            text = text.strip().replace(" ", "")

            if text:
                process_time = (time.time() - start_time) * 1000
                print(f"🎤 [{self.engine_type.upper()}] Captured: {text} (Lat: {process_time:.0f}ms)")
                self.msg_queue.put(text)

        except Exception as e:
            print(f"❌ Unexpected Error in recognition callback: {e}")


# 测试代码
if __name__ == "__main__":
    # 修改这里来切换引擎： 'google' 或 'vosk'
    CURRENT_ENGINE = 'vosk'

    ears = BackgroundEars(engine_type=CURRENT_ENGINE)
    ears.start()

    try:
        while True:
            text = ears.get_latest_text()
            if text:
                print(f"Main Thread Got: {text}")
                # 这里可以添加逻辑：比如听到“退出”就 break
            time.sleep(0.05)  # 稍微减少主循环的 sleep 时间，提高响应检查频率
    except KeyboardInterrupt:
        ears.stop()