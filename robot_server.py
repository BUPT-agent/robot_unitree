# robot_server.py
import os
import sys
import threading
import time
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient

# 机械臂动作控制
from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map

# 运动控制（运动模式）
from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

# ================= 可选音频辅助模块 =================
try:
    from wav import read_wav, play_pcm_stream

    WAV_MODULE_LOADED = True
except ImportError:
    print("Warning: wav.py module not found. WAV playback will be unavailable.")
    WAV_MODULE_LOADED = False

# ================= Flask 配置 =================
app = Flask(__name__)
UPLOAD_FOLDER = "server_uploads"
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ================= 全局客户端与锁 =================
audio_client = None
armAction_client = None
loco_client = None

speech_lock = threading.Lock()
action_lock = threading.Lock()

# ================= 音频：支持立即中断 =================
# WAV 播放使用此 app_name（与现有代码行为保持一致）。
WAV_APP_NAME = "server_play"

# 尽力停止其他可能的音频管线候选项。
# 注意：有效的 app_name 可能会因 SDK/固件版本不同而变化。
STOP_APP_CANDIDATES = [
    WAV_APP_NAME,
    "voice",
    "tts",
    "audio_tts",
    "vui",
    "audio",
    "server_tts",
]

# 追踪当前播放线程（WAV 流式播放）
_playback_thread = None
_playback_lock = threading.Lock()

# 音频代数计数器：防止陈旧的播放线程在 stop/抢占后又被启动
_audio_gen = 0
_audio_gen_lock = threading.Lock()


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def _bump_audio_gen():
    """增加音频代数编号，用于使待启动的音频失效。"""
    global _audio_gen
    with _audio_gen_lock:
        _audio_gen += 1
        return _audio_gen


def _get_audio_gen():
    """读取当前音频代数编号。"""
    with _audio_gen_lock:
        return _audio_gen


def _try_audio_stop_now():
    """
    尽力立即停止。
    - 优先尝试以非阻塞方式获取 speech_lock，以减少对 AudioClient 的并发访问。
    - 如果锁获取失败，也会在不阻塞的情况下尽力执行停止操作。
    """
    global audio_client
    if audio_client is None:
        return

    acquired = speech_lock.acquire(blocking=False)
    try:
        # 1) 如果 SDK 提供显式 stop/cancel 的 TTS 方法，则调用（若存在）。
        for m in ("TtsStop", "TtsCancel", "StopTts", "StopTTS", "StopVoice", "StopAll", "Stop"):
            fn = getattr(audio_client, m, None)
            if callable(fn):
                _safe_call(fn)

        # 2) 始终尝试对一组 app_name 候选项执行 PlayStop（WAV + 可能的 TTS 管线）。
        play_stop = getattr(audio_client, "PlayStop", None)
        if callable(play_stop):
            for app_name in STOP_APP_CANDIDATES:
                _safe_call(play_stop, app_name)
    finally:
        if acquired:
            speech_lock.release()


def _stop_and_preempt_audio():
    """
    在启动新音频前抢占（停止）任何正在进行的音频。
    同时推进音频代数计数器，使待启动的播放失效。
    """
    _bump_audio_gen()
    _try_audio_stop_now()


def _start_wav_playback_async(pcm_list):
    """
    在后台线程中启动 WAV 播放，使 HTTP 请求能够立即返回。
    同时支持通过 /cmd/stop 快速中断。
    """
    global _playback_thread, audio_client

    def _worker(gen_snapshot: int):
        # 用 speech_lock 串行化音频启动；停止操作为非阻塞尽力而为。
        with speech_lock:
            # 防止 stop/抢占后陈旧线程仍然启动。
            if gen_snapshot != _get_audio_gen():
                return
            if audio_client is None:
                return
            play_pcm_stream(audio_client, pcm_list, WAV_APP_NAME)

    with _playback_lock:
        # 抢占当前播放并使之前待启动的音频全部失效。
        _stop_and_preempt_audio()
        gen_snapshot = _get_audio_gen()

        t = threading.Thread(target=_worker, args=(gen_snapshot,), daemon=True)
        _playback_thread = t
        t.start()


# ================= 机械臂动作选项 =================
ARM_ACTION_OPTIONS = [
    {"name": "release arm", "id": 0},
    {"name": "shake hand", "id": 1},
    {"name": "high five", "id": 2},
    {"name": "hug", "id": 3},
    {"name": "high wave", "id": 4},
    {"name": "clap", "id": 5},
    {"name": "face wave", "id": 6},
    {"name": "left kiss", "id": 7},
    {"name": "heart", "id": 8},
    {"name": "right heart", "id": 9},
    {"name": "hands up", "id": 10},
    {"name": "x-ray", "id": 11},
    {"name": "right hand up", "id": 12},
    {"name": "reject", "id": 13},
    {"name": "right kiss", "id": 14},
    {"name": "two-hand kiss", "id": 15},
]
ARM_ID_TO_NAME = {x["id"]: x["name"] for x in ARM_ACTION_OPTIONS}
ARM_NAME_SET = {x["name"] for x in ARM_ACTION_OPTIONS}

# 这些动作在短暂延时后应该跟随执行 “release arm”
ARM_RELEASE_AFTER_2S_IDS = {1, 2, 3, 8, 9, 10, 11, 12, 13}

# ================= 运动控制（sport）选项 =================
LOCO_ACTION_OPTIONS = [
    {"name": "damp", "id": 0},
    {"name": "Squat2StandUp", "id": 1},
    {"name": "StandUp2Squat", "id": 2},
    {"name": "move forward", "id": 3},
    {"name": "move lateral", "id": 4},
    {"name": "move rotate", "id": 5},
    {"name": "low stand", "id": 6},
    {"name": "high stand", "id": 7},
    {"name": "zero torque", "id": 8},
    {"name": "wave hand1", "id": 9},   # 挥手但不转身
    {"name": "wave hand2", "id": 10},  # 挥手并伴随转身
    {"name": "shake hand", "id": 11},
    {"name": "Lie2StandUp", "id": 12},
]
LOCO_ID_TO_NAME = {x["id"]: x["name"] for x in LOCO_ACTION_OPTIONS}
LOCO_NAME_SET = {x["name"] for x in LOCO_ACTION_OPTIONS}


# ================= 核心接口 =================

# robot_server.py (片段)

@app.route("/cmd/speak", methods=["POST"])
def handle_speak():
    """文本转语音（TTS）接口。"""
    global audio_client
    data = request.json or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"status": "error", "msg": "No text provided"}), 400

    # 保持原有的串行调用行为。
    with speech_lock:
        if audio_client:
            ret = audio_client.TtsMaker(text, 0)
            return jsonify({"status": "success", "ret": ret})

    return jsonify({"status": "error", "msg": "Audio client not ready"}), 500

@app.route("/cmd/play_wav", methods=["POST"])
def handle_play_wav():
    """WAV 文件播放接口（16 kHz，单声道）。"""
    if not WAV_MODULE_LOADED:
        return jsonify({"status": "error", "msg": "wav.py module missing"}), 500

    if "file" not in request.files:
        return jsonify({"status": "error", "msg": "No file part"}), 400

    file = request.files["file"]
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        pcm_list, sample_rate, num_channels, is_ok = read_wav(filepath)
        if (not is_ok) or sample_rate != 16000 or num_channels != 1:
            return jsonify({"status": "error", "msg": "Invalid wav format (need 16k mono)"}), 400

        # 启动异步播放；抢占逻辑在 helper 内部已处理。
        _start_wav_playback_async(pcm_list)

        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500


@app.route("/cmd/stop", methods=["POST"])
def handle_stop():
    """停止音频流播放接口（并尽力停止 TTS）。"""
    # 先让任何“尚未开始”的待播放线程失效，然后尝试立即停止。
    _bump_audio_gen()
    _try_audio_stop_now()
    return jsonify({"status": "success"})


def _execute_arm_action(action_id: int, action_name: str):
    """使用 G1ArmActionClient 执行一个机械臂动作。"""
    global armAction_client
    if armAction_client is None:
        raise RuntimeError("Arm action client not ready")

    act = action_map.get(action_name)
    if act is None:
        raise RuntimeError(f"action_map not found for: {action_name}")

    armAction_client.ExecuteAction(act)

    if action_id in ARM_RELEASE_AFTER_2S_IDS:
        time.sleep(2)
        armAction_client.ExecuteAction(action_map.get("release arm"))


def _execute_loco_action(action_id: int, action_name: str):
    """使用 LocoClient 执行一个运动（sport）动作。"""
    global loco_client
    if loco_client is None:
        raise RuntimeError("Loco client not ready")

    # 以下行为与提供的终端示例保持一致。
    if action_id == 0:
        loco_client.Damp()
    elif action_id == 1:
        loco_client.Damp()
        time.sleep(0.5)
        loco_client.Squat2StandUp()
    elif action_id == 2:
        loco_client.StandUp2Squat()
    elif action_id == 3:
        loco_client.Move(0.3, 0.0, 0.0)
    elif action_id == 4:
        loco_client.Move(0.0, 0.3, 0.0)
    elif action_id == 5:
        loco_client.Move(0.0, 0.0, 0.3)
    elif action_id == 6:
        loco_client.LowStand()
    elif action_id == 7:
        loco_client.HighStand()
    elif action_id == 8:
        loco_client.ZeroTorque()
    elif action_id == 9:
        loco_client.WaveHand()
    elif action_id == 10:
        loco_client.WaveHand(True)
    elif action_id == 11:
        loco_client.ShakeHand()
        time.sleep(3)
        loco_client.ShakeHand()
    elif action_id == 12:
        loco_client.Damp()
        time.sleep(0.5)
        # 安全提示：使用 Lie2StandUp 时，请确保机器人面朝上，且地面坚硬、平整并具有一定粗糙度。
        loco_client.Lie2StandUp()
    else:
        raise ValueError(f"Unknown loco action id: {action_id}")


@app.route("/cmd/action", methods=["POST"])
def handle_action():
    data = request.json or {}

    group = data.get("group") or data.get("type")  # 允许 "type" 作为别名
    do_list = data.get("list") is True

    if do_list:
        if group == "arm":
            return jsonify({"status": "success", "group": "arm", "actions": ARM_ACTION_OPTIONS})
        if group == "loco":
            return jsonify({"status": "success", "group": "loco", "actions": LOCO_ACTION_OPTIONS})
        return jsonify({"status": "success", "actions": {"arm": ARM_ACTION_OPTIONS, "loco": LOCO_ACTION_OPTIONS}})

    action_id = data.get("id", None)
    action_name = data.get("name", None)

    # 如果未显式提供 group，则尝试自动判断
    if not group:
        if action_name:
            in_arm = action_name in ARM_NAME_SET
            in_loco = action_name in LOCO_NAME_SET
            if in_arm and in_loco:
                return jsonify(
                    {"status": "error", "msg": "Action name is ambiguous; please specify group='arm' or group='loco'."}
                ), 400
            if in_arm:
                group = "arm"
            elif in_loco:
                group = "loco"
            else:
                return jsonify({"status": "error", "msg": f"Unknown action name: {action_name}"}), 400
        else:
            # 默认行为：仅提供 id 的请求按机械臂动作处理，以保持兼容性。
            group = "arm"

    # 在选定 group 内解析 name/id
    if group == "arm":
        if action_name:
            if action_name not in ARM_NAME_SET:
                return jsonify({"status": "error", "msg": f"Unknown arm action name: {action_name}"}), 400
            resolved_id = next((x["id"] for x in ARM_ACTION_OPTIONS if x["name"] == action_name), None)
            resolved_name = action_name
        else:
            try:
                if action_id is None:
                    return jsonify({"status": "error", "msg": "No action id or name provided"}), 400
                resolved_id = int(action_id)
            except Exception:
                return jsonify({"status": "error", "msg": "Invalid action id"}), 400
            if resolved_id not in ARM_ID_TO_NAME:
                return jsonify({"status": "error", "msg": f"Unknown arm action id: {resolved_id}"}), 400
            resolved_name = ARM_ID_TO_NAME[resolved_id]

        try:
            with action_lock:
                _execute_arm_action(resolved_id, resolved_name)
            return jsonify({"status": "success", "group": "arm", "action": resolved_name, "id": resolved_id})
        except Exception as e:
            return jsonify({"status": "error", "msg": str(e)}), 500

    if group == "loco":
        if action_name:
            if action_name not in LOCO_NAME_SET:
                return jsonify({"status": "error", "msg": f"Unknown loco action name: {action_name}"}), 400
            resolved_id = next((x["id"] for x in LOCO_ACTION_OPTIONS if x["name"] == action_name), None)
            resolved_name = action_name
        else:
            try:
                if action_id is None:
                    return jsonify({"status": "error", "msg": "No action id or name provided"}), 400
                resolved_id = int(action_id)
            except Exception:
                return jsonify({"status": "error", "msg": "Invalid action id"}), 400
            if resolved_id not in LOCO_ID_TO_NAME:
                return jsonify({"status": "error", "msg": f"Unknown loco action id: {resolved_id}"}), 400
            resolved_name = LOCO_ID_TO_NAME[resolved_id]

        try:
            with action_lock:
                _execute_loco_action(resolved_id, resolved_name)
            return jsonify({"status": "success", "group": "loco", "action": resolved_name, "id": resolved_id})
        except ValueError as e:
            return jsonify({"status": "error", "msg": str(e)}), 400
        except Exception as e:
            return jsonify({"status": "error", "msg": str(e)}), 500

    return jsonify({"status": "error", "msg": "Invalid group; expected 'arm' or 'loco'."}), 400


@app.route("/status", methods=["GET"])
def health_check():
    """服务健康检查接口。"""
    return jsonify(
        {
            "status": "online",
            "sdk_ready": audio_client is not None,
            "arm_ready": armAction_client is not None,
            "loco_ready": loco_client is not None,
        }
    )


# ================= 启动 =================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python3 {sys.argv[0]} <network_interface>")
        print(f"Example: python3 {sys.argv[0]} eth0")
        sys.exit(-1)

    print("Initializing Unitree communication channel...")
    ChannelFactoryInitialize(0, sys.argv[1])

    # 音频客户端初始化
    audio_client = AudioClient()
    audio_client.Init()
    audio_client.SetVolume(100)

    # 机械臂动作客户端初始化
    armAction_client = G1ArmActionClient()
    armAction_client.SetTimeout(10.0)
    armAction_client.Init()

    # 运动客户端初始化
    loco_client = LocoClient()
    loco_client.SetTimeout(10.0)
    loco_client.Init()

    print("Server starting on 0.0.0.0:6000 ...")
    app.run(host="0.0.0.0", port=6000, debug=False, use_reloader=False)
