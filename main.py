import threading
import time
import queue
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from config import INTERRUPT_KEYWORDS
from robot_client import RobotClient
from brain import RobotBrain
from ears import RobotEars

# === 初始化核心模块 ===
robot = RobotClient() # 连接机器人
brain = RobotBrain()  # LLM
ears = RobotEars()    # ASR

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
    robot.stop_all()
    return jsonify({"status": "stopped"})


@app.route('/api/set_mode', methods=['POST'])
def set_mode():
    global current_mode
    data = request.json
    mode = data.get('mode')
    if mode in ['auto', 'director']:
        current_mode = mode
        return jsonify({"status": "success", "mode": mode})
    return jsonify({"status": "error"}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    # 简单的状态返回，用于前端心跳
    return jsonify({"mode": current_mode, "is_replying": False})  # is_replying 可根据实际扩充


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


# === 主控制循环 ===
def main_loop():
    print(">>> System Ready. Waiting for wake word...")

    while True:
        # 1. 优先处理 Web 端指令 (Director Mode)
        try:
            task = director_queue.get_nowait()
            if task[0] == 'speak':
                robot.speak(task[1])
            elif task[0] == 'action':
                robot.perform_action(task[1])
            continue
        except queue.Empty:
            pass

        # 2. 自动模式逻辑
        if current_mode == "auto":
            # A. 监听唤醒词
            # 注意：timeout 设置太大可能会导致网页端指令响应变慢，建议设置短一点循环检查
            wake_text = ears.listen_once(timeout=10, check_wake_word=True)

            if wake_text:
                print(f"⚡️ Wake Word Detected: {wake_text}")
                robot.speak("我在")

                # B. 监听具体指令 (唤醒后给更多时间说话)
                cmd_text = ears.listen_once(timeout=10, check_wake_word=False)

                if cmd_text:
                    print(f"User said: {cmd_text}")

                    # 检查是否是打断指令
                    if any(k in cmd_text for k in INTERRUPT_KEYWORDS):
                        robot.stop_all()
                        continue

                    # --- 核心 AI 流程 (修改后) ---

                    # 步骤 1: 先判断动作 (Action Analysis)
                    print("Analyzing action...")
                    action_data = brain.analyze_action(cmd_text)

                    # 步骤 2: 将动作信息作为上下文，生成回复 (Chat Generation)
                    # 此时 prompt 会变成："你即将执行[握手]，请结合该动作回复用户"
                    print("Generating reply with action context...")
                    reply = brain.get_chat_reply(cmd_text, action_data=action_data)

                    # 步骤 3: 执行 (Execution)
                    # 策略：先触发说话，紧接着触发动作，让它们尽可能并发
                    if reply:
                        print(f"🗣️ Robot says: {reply}")
                        # 使用线程或者非阻塞方式说话，这里取决于 robot.speak 实现
                        # 如果 robot.speak 是阻塞的，动作会在说完后执行
                        # 如果想要一边说一边做，可以把 speak 放到线程里
                        t_speak = threading.Thread(target=robot.speak, args=(reply,))
                        t_speak.start()

                    if action_data:
                        print(f"🦾 Robot acts: {action_data['desc']}")
                        robot.perform_action(action_data)

                    # 确保说话线程结束 (可选)
                    if reply:
                        t_speak.join(timeout=10)

                else:
                    print("No command detected (timeout).")

        time.sleep(0.05)


if __name__ == "__main__":
    # 启动 Flask 线程
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()

    # 启动主循环
    try:
        main_loop()
    except KeyboardInterrupt:
        print("Stopping...")