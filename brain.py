from openai import OpenAI
import json
import requests
import re
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, url, sessionId


class RobotBrain:
    def __init__(self):
        self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL

        # === 记忆模块配置 ===
        self.history = []
        self.max_history_items = 0

    def update_history(self, role, content):
        """更新对话历史，并保持在限制长度内"""
        self.history.append({"role": role, "content": content})
        while len(self.history) > self.max_history_items:
            self.history.pop(0)

    def _call_llm(self, messages, temperature=0.7):
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ LLM API Error: {str(e)}")
            return None

    def _call_external_api_stream(self, text):
        """
        请求外部API，过滤 eventName='text-data'，
        并将接收到的文本按标点切分为句子，实时 yield 返回。
        """
        params = {
            "voiceText": text,
            "sessionId": sessionId
        }

        headers = {
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache",
            "Referer": "https://gzybot.wenhuaguangxi.com:40509/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
            "Pragma": "no-cache"
        }

        print(f"📡 Calling External API (Streaming) for: {text}")

        buffer = ""
        # 切分规则：句号、问号、感叹号、换行符
        split_pattern = r'([。！？.!?\n]+)'

        try:
            response = requests.get(url, params=params, headers=headers, stream=True)

            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        if decoded_line.startswith("data:"):
                            json_str = decoded_line[5:].strip()
                            try:
                                data = json.loads(json_str)

                                # 只关注 text-data 事件
                                if data.get("eventName") == "text-data":
                                    chunk = data.get("data", "")
                                    buffer += chunk

                                    # 缓冲区切分逻辑
                                    while True:
                                        match = re.search(split_pattern, buffer)
                                        if match:
                                            end_pos = match.end()
                                            sentence = buffer[:end_pos]
                                            buffer = buffer[end_pos:]

                                            if sentence.strip():
                                                yield sentence
                                        else:
                                            break
                            except json.JSONDecodeError:
                                pass

                # 收尾
                if buffer.strip():
                    yield buffer
            else:
                print(f"❌ API Status Code: {response.status_code}")
        except Exception as e:
            print(f"❌ API Error: {str(e)}")

    def get_chat_reply(self, user_text):
        """
        获取回复 (Generator)
        只负责流式获取语音文本，不处理动作上下文。
        """
        full_reply_accumulator = ""

        # 调用流式处理
        stream_generator = self._call_external_api_stream(user_text)
        print(stream_generator)
        for sentence in stream_generator:
            print(sentence)
            full_reply_accumulator += sentence

            yield sentence

        # 更新历史
        self.update_history("user", user_text)
        if full_reply_accumulator:
            self.update_history("assistant", full_reply_accumulator)
