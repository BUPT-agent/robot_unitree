import threading
import time
import queue
import random
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from config import INTERRUPT_KEYWORDS
from robot_client import RobotClient
from brain import RobotBrain
# 注意这里引入的是新的 BackgroundEars
from ears import BackgroundEars

# === 初始化核心模块 ===
robot = RobotClient()
brain = RobotBrain()
ears = BackgroundEars()  # 实例化

# === Flask Web Server (保持不变) ===
app = Flask(__name__)
CORS(app)
director_queue = queue.Queue()
current_mode = "auto"


@app.route('/')
def index(): return render_template('index.html')


@app.route('/api/interrupt', methods=['POST'])
def api_interrupt():
    # 打断时，不仅要停机器人，还要清空积压的语音缓存
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
        ears.clear_queue()  # 切换模式时清空缓存
        return jsonify({"status": "success", "mode": mode})
    return jsonify({"status": "error"}), 400


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify({"mode": current_mode, "is_replying": False})


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
    # 1. 启动耳朵线程 (它会自己一直在后台听，把字存进队列)
    ears.start()

    print(">>> System Ready. High-Performance Event Loop Started.")

    # 空闲计时
    last_interaction_time = time.time()
    idle_threshold = random.randint(15, 30)

    while True:
        # 这个循环现在运行得非常快 (每秒几十次)
        # 它可以瞬间响应网页指令，或者瞬间处理缓存里的语音

        # ==========================================
        # 1. 检查网页指令 (最高优先级)
        # ==========================================
        try:
            web_task = director_queue.get_nowait()
            last_interaction_time = time.time()

            # 网页指令来了，先把语音缓存清空，防止处理旧语音
            ears.clear_queue()

            if web_task[0] == 'speak':
                print(f"📡 Web Speak: {web_task[1]}")
                brain.update_history("assistant", web_task[1])
                # 使用线程发送，避免阻塞主循环
                threading.Thread(target=robot.speak, args=(web_task[1],)).start()

            elif web_task[0] == 'action':
                print(f"📡 Web Action: {web_task[1]}")
                threading.Thread(target=robot.perform_action, args=(web_task[1],)).start()

            continue  # 处理完立刻进入下一次循环
        except queue.Empty:
            pass

        # ==========================================
        # 2. 检查语音缓存 (Auto Mode)
        # ==========================================
        if current_mode == "auto":
            # 这里不再阻塞等待！直接看缓存队列里有没有货
            user_text = ears.get_latest_text()

            if user_text:
                print(f"📨 Processing Buffer: {user_text}")

                # 重置空闲计时
                last_interaction_time = time.time()
                idle_threshold = random.randint(15, 30)

                # A. 打断检测 (最高优先级)
                if any(k in user_text for k in INTERRUPT_KEYWORDS):
                    print("🛑 Interrupt detected!")
                    robot.stop_all()
                    ears.clear_queue()  # 既然打断了，后面的缓存也没必要处理了
                    continue

                # B. 核心 AI 处理
                # 这一步是耗时的 (HTTP请求)，为了不卡住主循环去接收新的语音，
                # 我们可以选择在这里阻塞一下 (简单做法)，
                # 或者把 AI 处理也丢进线程池 (复杂做法)。
                # 鉴于目前逻辑，在这里同步等待 Brain 结果是可以接受的，
                # 因为耳朵线程依然在后台继续缓存新的话。

                # 1. 分析动作
                # action_data = brain.analyze_action(user_text)

                # 2. 生成回复
                reply = brain.get_chat_reply(user_text)

                # 3. 执行 (多线程并发)
                if reply:
                    print(f"🗣️ Robot says: {reply}")
                    threading.Thread(target=robot.speak, args=(reply,)).start()

                # if action_data:
                #     print(f"🦾 Robot acts: {action_data['desc']}")
                #     threading.Thread(target=robot.perform_action, args=(action_data,)).start()

            else:
                # ==========================================
                # 3. 空闲检测 (Idle Logic)
                # ==========================================
                # 只有在没有网页指令、也没有语音缓存时才检查空闲
                if time.time() - last_interaction_time > idle_threshold:
                    print(f"💤 Idle triggered...")

                    idle_text, idle_action = brain.trigger_idle_behavior()

                    if idle_text:
                        print(f"🤖 Idle Reply: {idle_text}")
                        threading.Thread(target=robot.speak, args=(idle_text,)).start()

                        if idle_action:
                            threading.Thread(target=robot.perform_action, args=(idle_action,)).start()

                    last_interaction_time = time.time()
                    idle_threshold = random.randint(10, 20)

        # 极短的休眠，防止 CPU 占用 100%，同时保证反应极快
        time.sleep(0.02)


if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()

    try:
        main_loop()
    except KeyboardInterrupt:
        ears.stop()  # 记得关闭耳朵线程
        print("Stopping...")