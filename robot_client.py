import os
import requests
import threading
import time
from config import ROBOT_SERVER_URL


class RobotClient:
    def __init__(self):
        self.session = requests.Session()
        self.interrupt_event = threading.Event()
        self._disable_proxies()

    def _disable_proxies(self):
        # 禁用代理防止连接局域网机器人失败
        proxies = ['http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY']
        for p in proxies:
            if p in os.environ:
                del os.environ[p]

    def _post(self, endpoint, json_data=None, files=None):
        try:
            url = f"{ROBOT_SERVER_URL.rstrip('/')}/{endpoint.lstrip('/')}"
            return self.session.post(url, json=json_data, files=files, timeout=2)
        except Exception as e:
            print(f"Robot Comm Error: {e}")
            return None

    def stop_all(self):
        """停止说话和运动"""
        self.interrupt_event.set()
        self._post("/cmd/stop")  # 停止音频
        self._post("/cmd/action", {"group": "loco", "name": "damp"})  # 阻尼模式作为急停

    def speak(self, text):
        """发送 TTS 请求"""
        if not text: return
        self.interrupt_event.clear()
        print(f"🤖 Robot Speak: {text}")
        self._post("/cmd/speak", {"text": text})

        # 简单的估算延时，允许打断
        duration = len(text) * 0.3 + 1
        start = time.time()
        while time.time() - start < duration:
            if self.interrupt_event.is_set():
                break
            time.sleep(0.1)

    def perform_action(self, action_data):
        """执行具体的动作指令"""
        if self.interrupt_event.is_set(): return
        print(f"🦾 Executing Action: {action_data}")
        self._post("/cmd/action", action_data)

    def play_wav(self, filepath):
        with open(filepath, 'rb') as f:
            self._post("/cmd/play_wav", files={'file': f})