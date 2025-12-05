import threading
import time
import queue
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from openai import OpenAI
from config import LLM_API_KEY, LLM_BASE_URL
from pypinyin import lazy_pinyin
# === 配置导入 ===
from config import WAKE_WORDS,IS_LLM_CHECK
from robot_client import RobotClient
from brain import RobotBrain
from ears import BackgroundEars
import os
# === 初始化核心模块 ===
robot = RobotClient()
brain = RobotBrain()
ears = BackgroundEars()

# === Flask Web Server ===
app = Flask(__name__)
CORS(app)
director_queue = queue.Queue()
current_mode = "auto"


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/interrupt', methods=['POST'])
def api_interrupt():
    ears.clear_queue()
    robot.stop_all()
    return jsonify({"status": "stopped"})


@app.route('/api/set_mode', methods=['POST'])
def set_mode():
    global current_mode
    data = request.json
    mode = data.get('mode')
    if mode in ['auto', 'director']:
        current_mode = mode
        ears.clear_queue()
        return jsonify({"status": "success", "mode": mode})
    return jsonify({"status": "error"}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"mode": current_mode, "is_replying": robot.is_speaking()})


@app.route('/api/director/speak', methods=['POST'])
def director_speak():
    text = request.json.get('text')
    director_queue.put(('speak', text))
    return jsonify({"status": "queued"})


@app.route('/api/director/action', methods=['POST'])
def director_action():
    data = request.json
    director_queue.put(('action', data))
    return jsonify({"status": "queued"})


def run_flask():
    app.run(host='0.0.0.0', port=5000, use_reloader=False)


# === 核心逻辑：主循环 ===
def main_loop():
    ears.start()
    while True:
        # 1. 检查网页指令 (最高优先级)
        try:
            web_task = director_queue.get_nowait()
            ears.clear_queue()
            if web_task[0] == 'speak':
                brain.update_history("assistant", web_task[1])
                robot.speak(web_task[1])
            elif web_task[0] == 'action':
                threading.Thread(target=robot.perform_action, args=(web_task[1],)).start()
            continue
        except queue.Empty:
            pass

        # 2. 检查语音缓存 (Auto Mode)
        if current_mode == "auto":
            if robot.is_speaking():
                ears.clear_queue()
                time.sleep(0.1)
                continue

            user_text = ears.get_latest_text()

            if user_text:
                user_pinyin = "".join(lazy_pinyin(user_text))

                # 2. 遍历唤醒词，同样转为拼音进行匹配
                is_woken_up = any("".join(lazy_pinyin(kw)) in user_pinyin for kw in WAKE_WORDS)

                if is_woken_up:
                    try:
                        if IS_LLM_CHECK == True:
                            try:
                                # 1. 构建符合 OpenAI 标准的消息格式
                                # 建议将提示词放入 system 角色，用户语音放入 user 角色
                                messages_payload = [
                                    {"role": "system", "content": "请纠正下面用户问题的语言错误，把桂小志的同音词（例如“归小子”，“鬼小志”）换成桂小志，仅返回修复后的问题："},
                                    {"role": "user", "content": user_text}
                                ]

                                # 2. 调用 API
                                response = _client.chat.completions.create(
                                    model="gpt-4o",
                                    messages=messages_payload,  # 这里传入列表，而不是字符串
                                    temperature=0.7,
                                )

                                # 3. 更新 user_text
                                user_text = response.choices[0].message.content.strip()
                                print("修正后的句子：", user_text)

                            except Exception as e:
                                print(f"❌ LLM API Error: {str(e)}")
                                pass

                        reply_generator = brain.get_chat_reply(user_text)

                        for sentence in reply_generator:
                            if not sentence: continue

                            if robot.interrupt_event.is_set():
                                break

                            robot.speak(sentence)

                    except Exception:
                        pass

        time.sleep(0.02)


if __name__ == "__main__":
    _client = OpenAI(api_key="XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
                     base_url="https://api.rcouyi.com/v1")
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()
    try:
        main_loop()
    except KeyboardInterrupt:
        ears.stop()
