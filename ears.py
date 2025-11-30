import sys
import queue
import speech_recognition as sr
from config import MIC_DEVICE_INDEX


class BackgroundEars:
    def __init__(self):
        # 初始化识别器
        self.recognizer = sr.Recognizer()
        # 语音缓存队列
        self.msg_queue = queue.Queue()
        # 用于存储停止监听的函数
        self.stop_listening_func = None

        # 可选：动态调整能量阈值（灵敏度）
        self.recognizer.energy_threshold = 400
        # 如果环境嘈杂，设为 True 会自动调整，但在机器人身上可能导致误判，建议 False 或手动调
        self.recognizer.dynamic_energy_threshold = False

    def start(self):
        """启动后台监听线程"""
        print("👂 Initializing Microphone for Google Speech...")

        try:
            # 初始化麦克风
            # 注意：PyAudio 的设备索引可能与 sounddevice 不同，如果报错请尝试不传 device_index
            self.mic = sr.Microphone(device_index=MIC_DEVICE_INDEX)

            with self.mic as source:
                print(">>> Adjusting for ambient noise... (Please stay quiet for 1s)")
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                print(">>> Listening...")

            # 启动后台监听
            # listen_in_background 会自动创建一个线程去录音
            # 当检测到一句完整的语音后，会自动调用 self._callback
            self.stop_listening_func = self.recognizer.listen_in_background(self.mic, self._callback)
            print("👂 Background Ears Started (Google Engine)...")

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
        """非阻塞获取当前的一条语音文本"""
        try:
            return self.msg_queue.get_nowait()
        except queue.Empty:
            return None

    def clear_queue(self):
        """清空缓存"""
        with self.msg_queue.mutex:
            self.msg_queue.queue.clear()

    def _callback(self, recognizer, audio):
        """
        这是回调函数，当后台线程录完一句话后会自动调用这里。
        在这里我们将音频发送给 Google 进行识别。
        """
        try:
            # 使用 Google 语音识别 (需要联网)
            # language='zh-CN' 指定中文
            text = recognizer.recognize_google(audio, language='zh-CN')

            # 简单的文本清理
            text = text.strip().replace(" ", "")

            if text:
                print(f"🎤 [Google] Captured: {text}")
                self.msg_queue.put(text)

        except sr.UnknownValueError:
            # 听不到或听不清时会抛出此异常，直接忽略即可
            pass
        except sr.RequestError as e:
            # 网络问题或 API 限制
            print(f"❌ Google Speech API Error: {e}")
        except Exception as e:
            print(f"❌ Unexpected Error in recognition: {e}")


# 测试代码
if __name__ == "__main__":
    import time

    ears = BackgroundEars()
    ears.start()
    try:
        while True:
            text = ears.get_latest_text()
            if text:
                print(f"Main Thread Got: {text}")
            time.sleep(0.1)
    except KeyboardInterrupt:
        ears.stop()