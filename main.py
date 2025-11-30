import threading
import time
import queue
import random
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
    print(">>> System Ready. Continuous Listening Mode...")

    # --- 空闲行为计时初始化 ---
    last_interaction_time = time.time()
    # 初始随机阈值：15~30秒内没人说话，机器人就会触发闲时行为
    idle_threshold = random.randint(15, 30)

    while True:
        # =================================================
        # 1. 优先处理 Web 端指令 (Director Mode & Auto Mode)
        # =================================================
        try:
            # get_nowait() 是非阻塞的，如果没有指令会立即抛出 Empty 异常
            task = director_queue.get_nowait()

            # 只要有网页操作，就视为产生了互动，重置空闲计时
            last_interaction_time = time.time()

            if task[0] == 'speak':
                text_content = task[1]
                print(f"📡 Web Command Speak: {text_content}")

                # 手动更新大脑记忆，确保机器人知道自己刚才被强制说了什么
                brain.update_history("assistant", text_content)
                robot.speak(text_content)

            elif task[0] == 'action':
                action_data = task[1]
                print(f"📡 Web Command Action: {action_data}")
                robot.perform_action(action_data)

            # 处理完网页指令后，立即跳过本次循环的剩余部分，
            # 快速回到开头检查是否还有下一条网页指令（保证连点不卡顿）
            continue

        except queue.Empty:
            pass

        # =================================================
        # 2. 自动模式逻辑 (Auto Mode)
        # =================================================
        if current_mode == "auto":
            # 监听环境音
            # timeout=2 表示监听2秒。如果2秒内没说话，函数返回 None，
            # 程序会继续向下运行去检查空闲计时器或重新检查网页指令。
            user_text = ears.listen_once(timeout=5, check_wake_word=False)

            if user_text:
                # ---------------------------------
                # 情况 A: 用户说话了 (User Spoke)
                # ---------------------------------
                print(f"👂 User said: {user_text}")

                # 重置空闲计时
                last_interaction_time = time.time()
                # 重置下一次触发闲时行为的阈值 (15-30秒)
                idle_threshold = random.randint(15, 30)

                # A.1 打断检测 (最高优先级)
                if any(k in user_text for k in INTERRUPT_KEYWORDS):
                    print("🛑 Interrupt detected!")
                    robot.stop_all()
                    continue

                # A.2 核心交互流程
                # 1. 判断动作
                print("Analyzing action...")
                action_data = brain.analyze_action(user_text)

                # 2. 生成回复 (带动作上下文)
                print("Generating reply...")
                # 注意：get_chat_reply 内部会自动更新 brain.history
                reply = brain.get_chat_reply(user_text, action_data=action_data)

                # 3. 并发执行 (一边说一边做)
                t_speak = None
                if reply:
                    print(f"🗣️ Robot says: {reply}")
                    # 启动独立线程说话，防止阻塞动作执行
                    t_speak = threading.Thread(target=robot.speak, args=(reply,))
                    t_speak.start()

                if action_data:
                    print(f"🦾 Robot acts: {action_data['desc']}")
                    robot.perform_action(action_data)

                # 等待说话线程结束
                # 这一步很重要，防止机器人说话时被自己的麦克风录进去导致死循环
                if t_speak:
                    t_speak.join()

            else:
                # ---------------------------------
                # 情况 B: 没人说话 (Silence / Idle)
                # ---------------------------------
                current_time = time.time()
                time_diff = current_time - last_interaction_time

                # 检查沉默时间是否超过了随机阈值
                if time_diff > idle_threshold:
                    print(f"💤 Idle triggered (Silence for {int(time_diff)}s)...")

                    # 触发大脑的闲时行为逻辑
                    idle_text, idle_action = brain.trigger_idle_behavior()
                    print(idle_text)
                    print(idle_action)

                    if idle_text:
                        print(f"🤖 Auto-Idle-Reply: {idle_text}")

                        # 同样采用线程说话，配合可能的动作
                        t_idle = threading.Thread(target=robot.speak, args=(idle_text,))
                        t_idle.start()

                        if idle_action:
                            print(f"🦾 Auto-Idle-Action: {idle_action['desc']}")
                            robot.perform_action(idle_action)

                        if t_idle: t_idle.join()

                    # 触发过一次后，重置计时器
                    last_interaction_time = time.time()

                    # 将下一次的触发间隔调长 (例如 20-60秒)，防止它过于唠叨
                    idle_threshold = random.randint(20, 30)
                    print(f"💤 Next idle check in {idle_threshold}s")

        # 避免 CPU 100% 占用
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