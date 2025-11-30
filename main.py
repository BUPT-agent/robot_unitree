import threading
import time
import queue
import random
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

from config import INTERRUPT_KEYWORDS, FILLER_PHRASES
from robot_client import RobotClient
from brain import RobotBrain
# 注意这里引入的是新的 BackgroundEars
from ears import BackgroundEars
from concurrent.futures import ThreadPoolExecutor

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
    # 1. 启动耳朵线程
    ears.start()
    print(">>> System Ready. High-Performance Event Loop Started.")

    last_interaction_time = time.time()
    idle_threshold = random.randint(15, 30)

    while True:
        # ==========================================
        # 1. 检查网页指令 (保持不变)
        # ==========================================
        try:
            web_task = director_queue.get_nowait()
            last_interaction_time = time.time()
            ears.clear_queue()

            if web_task[0] == 'speak':
                print(f"📡 Web Speak: {web_task[1]}")
                brain.update_history("assistant", web_task[1])
                threading.Thread(target=robot.speak, args=(web_task[1],)).start()
            elif web_task[0] == 'action':
                print(f"📡 Web Action: {web_task[1]}")
                threading.Thread(target=robot.perform_action, args=(web_task[1],)).start()
            continue
        except queue.Empty:
            pass

        # ==========================================
        # 2. 检查语音缓存 (Auto Mode) - 修改了这里
        # ==========================================
        if current_mode == "auto":
            user_text = ears.get_latest_text()

            if user_text:
                t_received = time.time()
                print(f"\n[TIMING] 📨 Received: '{user_text}'")

                # 重置空闲计时
                last_interaction_time = time.time()
                idle_threshold = random.randint(15, 30)

                # A. 打断检测
                if any(k in user_text for k in INTERRUPT_KEYWORDS):
                    print("🛑 Interrupt detected!")
                    robot.stop_all()
                    ears.clear_queue()
                    continue

                # ==========================================
                # ⚡️ 极速响应逻辑 (Instant Feedback)
                # ==========================================

                # # 1. 【立即】播放“填空词” (Filler)
                # # 这一步是毫秒级的，用户说完话立刻就能听到反馈
                # filler = random.choice(FILLER_PHRASES)
                # print(f"🗣️ [Fast Ack] Speaking filler: {filler}")
                # # 注意：这里使用线程播放，确保不阻塞后面的大脑思考
                # threading.Thread(target=robot.speak, args=(filler,)).start()

                # ==========================================
                # 🧠 并行思考 (Parallel Thinking)
                # ==========================================
                # 在机器人念叨“嗯，让我想想...”的同时，大脑疯狂运转
                print("⚡️ Processing LLM in background...")

                action_data = None
                reply = None

                # 使用线程池并行请求 Action 和 Reply
                with ThreadPoolExecutor(max_workers=2) as executor:
                    future_action = executor.submit(brain.analyze_action, user_text)
                    future_reply = executor.submit(brain.get_chat_reply, user_text)

                    # 等待结果 (此时机器人可能正在播放 Filler，或者刚播完)
                    action_data = future_action.result()
                    reply = future_reply.result()

                # 计算思考耗时
                think_duration = time.time() - t_received
                print(f"✅ Thinking done in {think_duration:.2f}s")

                # ==========================================
                # 🎬 最终执行 (Final Execution)
                # ==========================================

                # 1. 播放正式回复
                # 语音合成通常有队列机制。如果 Filler 还没说完，这句话会自动排在后面。
                if reply:
                    print(f"🗣️ Robot Reply: {reply}")
                    threading.Thread(target=robot.speak, args=(reply,)).start()

                # 2. 执行动作
                # 动作也应该并行触发，不要等话说完才动
                if action_data:
                    print(f"🦾 Robot Act: {action_data.get('desc', 'Unknown')}")
                    threading.Thread(target=robot.perform_action, args=(action_data,)).start()

            else:
                # ==========================================
                # 3. 空闲检测 (保持不变)
                # ==========================================
                if time.time() - last_interaction_time > idle_threshold:
                    print(f"💤 Idle triggered...")
                    idle_text, idle_action = brain.trigger_idle_behavior()
                    if idle_text:
                        threading.Thread(target=robot.speak, args=(idle_text,)).start()
                        if idle_action:
                            threading.Thread(target=robot.perform_action, args=(idle_action,)).start()
                    last_interaction_time = time.time()
                    idle_threshold = random.randint(10, 20)

        time.sleep(0.02)


if __name__ == "__main__":
    t_flask = threading.Thread(target=run_flask, daemon=True)
    t_flask.start()

    try:
        main_loop()
    except KeyboardInterrupt:
        ears.stop()  # 记得关闭耳朵线程
        print("Stopping...")