# robot_client.py
import os
import requests
import threading
import time
from config import ROBOT_SERVER_URL
from tool import safe_upload_wav


class RobotClient:
    def __init__(self):
        self.session = requests.Session()
        self.interrupt_event = threading.Event()
        self._disable_proxies()

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
        self.interrupt_event.set()
        self._post("/cmd/stop")
        self._post("/cmd/action", {"group": "loco", "name": "damp"})

    def speak(self, text):
        if not text: return
        self.interrupt_event.clear()
        print(f"🤖 Robot Speak: {text}")
        self._post("/cmd/speak", {"text": text})

        # 简单延时防止连续指令冲突
        duration = len(text) * 0.3 + 1
        start = time.time()
        while time.time() - start < duration:
            if self.interrupt_event.is_set(): break
            time.sleep(0.1)

    def perform_action(self, action_data):
        if self.interrupt_event.is_set(): return
        print(f"🦾 Executing Action: {action_data}")
        self._post("/cmd/action", action_data)

    def play_wav(self, filepath):
        # 逻辑全部移交给 tool.py，保持代码极简
        safe_upload_wav(self.session, ROBOT_SERVER_URL, filepath)