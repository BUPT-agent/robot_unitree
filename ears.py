import sys
import json
import queue
import os
import time
import requests
import speech_recognition as sr
from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest
from config import MIC_DEVICE_INDEX

# ================= 阿里云配置 =================
ACCESS_KEY_ID = "XXXX"
ACCESS_KEY_SECRET = "XXXX"
APPKEY = "XXXX"


# ============================================

class BackgroundEars:
    def __init__(self):
        """
        初始化耳朵
        """
        self.recognizer = sr.Recognizer()
        self.msg_queue = queue.Queue()
        self.stop_listening_func = None
        self.aliyun_token = None

        # 获取阿里云 Token (启动时获取一次)
        self.aliyun_token = self._get_aliyun_token()
        if not self.aliyun_token:
            print("❌ 无法获取阿里云 Token，程序退出")
            sys.exit(1)

        # 1. 声音波动检测灵敏度
        self.recognizer.energy_threshold = 400
        self.recognizer.dynamic_energy_threshold = True

        # 2. 直到 1s 内检测不到声音，才认为说话结束
        self.recognizer.pause_threshold = 1.0

        # 其他辅助参数
        self.recognizer.non_speaking_duration = 0.5
        self.recognizer.phrase_threshold = 0.3

    def _get_aliyun_token(self):
        """获取阿里云访问令牌"""
        print(">>> 正在初始化阿里云 Token...")
        client = AcsClient(ACCESS_KEY_ID, ACCESS_KEY_SECRET, "cn-shanghai")
        request = CommonRequest()
        request.set_method('POST')
        request.set_domain('nls-meta.cn-shanghai.aliyuncs.com')
        request.set_version('2019-02-28')
        request.set_action_name('CreateToken')

        try:
            response = client.do_action_with_exception(request)
            jss = json.loads(response)
            if 'Token' in jss and 'Id' in jss['Token']:
                return jss['Token']['Id']
            else:
                return None
        except Exception as e:
            print(f"❌ Token 获取异常: {e}")
            return None

    def clear_queue(self):
        """清空缓存"""
        with self.msg_queue.mutex:
            self.msg_queue.queue.clear()

    def start(self):
        """启动后台监听线程"""
        print(f"👂 Initializing Microphone for [ALIYUN] Speech...")

        try:
            # 阿里云通常建议 16000 采样率
            self.mic = sr.Microphone(device_index=MIC_DEVICE_INDEX, sample_rate=16000)

            with self.mic as source:
                print(">>> 正在调整环境噪音基准 (请保持安静 0.5秒)...")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

            # 启动后台监听
            # 这里的逻辑是：检测到声音 -> 开始录音 -> 声音停止1秒 -> 触发 _callback
            self.stop_listening_func = self.recognizer.listen_in_background(
                self.mic,
                self._callback,
                phrase_time_limit=20  # 单句最长录音限制，防止一直不结束
            )
            print(">>> 服务已就绪，请说话...")

        except Exception as e:
            print(f"❌ Microphone Init Error: {e}")
            sys.exit(1)

    def stop(self):
        """停止监听"""
        if self.stop_listening_func:
            self.stop_listening_func(wait_for_stop=False)
            self.stop_listening_func = None

    def get_latest_text(self):
        try:
            return self.msg_queue.get_nowait()
        except queue.Empty:
            return None

    def _callback(self, recognizer, audio):
        """
        回调函数：当检测到说话停止（停顿1s）后触发，上传阿里云
        """
        start_process_time = time.time()

        try:
            # --- 1. 获取 WAV 二进制数据 ---
            # 直接转换成 WAV 格式的 bytes，无需保存文件
            audio_data = audio.get_wav_data(convert_rate=16000, convert_width=2)

            if len(audio_data) == 0:
                return

            # --- 2. 发送给阿里云 (RESTful API) ---
            url = f"http://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
            request_url = f"{url}?appkey={APPKEY}&format=wav&sample_rate=16000"

            headers = {
                'X-NLS-Token': self.aliyun_token,
                'Content-Type': 'application/octet-stream',
                'Content-Length': str(len(audio_data))
            }

            # print(">>> 正在上传音频至阿里云...") # 调试用，可注释
            response = requests.post(request_url, headers=headers, data=audio_data)
            result = response.json()

            text = ""
            if response.status_code == 200 and result.get('status') == 20000000:
                text = result.get('result', '')
            else:
                print(f"❌ 阿里云识别失败: {result}")

            # 结果清理
            text = text.strip().replace(" ", "")

            if text:
                end_process_time = time.time()
                total_latency = (end_process_time - start_process_time) * 1000
                print(f"🎤 [ALIYUN] Captured: '{text}' (Latency: {total_latency:.1f}ms)")
                self.msg_queue.put(text)

        except Exception as e:
            print(f"❌ Unexpected Error in callback: {e}")


# 测试代码
if __name__ == "__main__":
    ears = BackgroundEars()
    ears.start()

    print("🛑 按 Ctrl+C 停止测试")
    try:
        while True:
            text = ears.get_latest_text()
            if text:
                print(f"✅ Main Thread Received: {text}")
            time.sleep(0.05)
    except KeyboardInterrupt:
        ears.stop()