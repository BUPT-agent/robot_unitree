import os
import requests
import threading
import time
import queue  # 引入队列
from config import ROBOT_SERVER_URL
from tool import safe_upload_wav
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

def set_windows_mic_mute(mute: bool):
    """
    控制 Windows 系统默认麦克风的静音状态
    :param mute: True 为静音, False 为取消静音
    """
    try:
        # 获取系统默认的音频输入设备（麦克风）
        # 注意：GetMicrophone() 需要较新版本的 pycaw，如果报错请看底部的替代写法
        devices = AudioUtilities.GetMicrophone()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = interface.QueryInterface(IAudioEndpointVolume)
        volume.SetMute(mute, None)
    except Exception as e:
        print(f"⚠️ 麦克风控制失败: {e}")

class RobotClient:
    def __init__(self):
        self.session = requests.Session()
        self.interrupt_event = threading.Event()
        self._disable_proxies()

        # === 语音队列系统 ===
        self.speech_queue = queue.Queue()
        self.is_speaking_flag = False  # 标记机器人是否正在忙碌（说话中）

        # 启动后台线程处理说话任务
        self.worker_thread = threading.Thread(target=self._speak_worker, daemon=True)
        self.worker_thread.start()

    def _disable_proxies(self):
        proxies = ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']
        for p in proxies:
            if p in os.environ: del os.environ[p]

    def _post(self, endpoint, json_data=None):
        try:
            url = f"{ROBOT_SERVER_URL.rstrip('/')}/{endpoint.lstrip('/')}"
            return self.session.post(url, json=json_data, timeout=3)
        except Exception as e:
            print(f"Robot Comm Error: {e}")
            return None

    def stop_all(self):
        """停止一切，清空队列"""
        self.interrupt_event.set()

        # 1. 清空等待说的队列
        with self.speech_queue.mutex:
            self.speech_queue.queue.clear()

        self.is_speaking_flag = False

        # 2. 发送物理停止指令
        self._post("/cmd/stop")
        self._post("/cmd/action", {"group": "loco", "name": "damp"})

    def speak(self, text):
        """
        非阻塞说话：只把文字放入队列。
        """
        if not text: return
        self.interrupt_event.clear()
        # print(f"📥 [Client] 入队: {text}")
        self.speech_queue.put(text)

    def is_speaking(self):
        """判断机器人是否正在说话或有话没说完"""
        # 如果 Flag 为 True 或者 队列里还有东西，就算作正在说话
        return self.is_speaking_flag or not self.speech_queue.empty()

    def _speak_worker(self):
        while True:
            try:
                text = self.speech_queue.get()
                self.is_speaking_flag = True

                if self.interrupt_event.is_set():
                    self.speech_queue.task_done()
                    self.is_speaking_flag = False
                    continue

                print(f"🤖 [Robot] Playing: {text}")
                self._post("/cmd/speak", {"text": text})

                # === 估算等待时间 ===
                duration = len(text) * 0.22 + 0.1
                print("duration:", duration)

                # ===============================================
                # 👇 在这里修改代码
                # ===============================================

                # 1. 马上静音
                set_windows_mic_mute(True)

                try:
                    start_time = time.time()
                    while time.time() - start_time < duration:
                        if self.interrupt_event.is_set():
                            break
                        time.sleep(0.1)
                finally:
                    # 2. 无论时间到没到，还是被打断，最后必须恢复麦克风
                    set_windows_mic_mute(False)

                # ===============================================
                # 👆 修改结束
                # ===============================================

                self.speech_queue.task_done()

                if self.speech_queue.empty():
                    self.is_speaking_flag = False

            except Exception as e:
                print(f"Worker Error: {e}")
                self.is_speaking_flag = False
                # 异常保护：防止报错导致麦克风一直静音
                set_windows_mic_mute(False)

    def perform_action(self, action_data):
        if self.interrupt_event.is_set(): return
        print(f"🦾 Executing Action: {action_data}")
        self._post("/cmd/action", action_data)

    def play_wav(self, filepath):
        safe_upload_wav(self.session, ROBOT_SERVER_URL, filepath)