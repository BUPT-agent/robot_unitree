import os

# === 机器人配置 ===
ROBOT_SERVER_URL = "http://192.168.1.72:6000"
MIC_DEVICE_INDEX = 1

# === 大模型配置 ===
LLM_API_KEY = os.getenv("OPENAI_API_KEY")  # 请替换你的 Key
LLM_BASE_URL = "https://api.rcouyi.com/v1" # 或你的本地/中转地址
LLM_MODEL = "gpt-4o" # 或你的模型名

# === 语音交互配置 ===
WAKE_WORDS = ["你好", "桂小志", "guixiaozhi", "guixiaozi"]
VOSK_MODEL_PATH = "model"
IS_LLM_CHECK = True

# api 设置
url = "https://gzybot.wenhuaguangxi.com:XXX/XXXXXXXXXX"
sessionId = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

# === 动作定义 (ACTION_MAP) ===
# 大模型根据 "desc" 来判断用户意图，并返回对应的 Key (数字 ID)
ACTION_MAP = {
    # --- Arm Actions (手臂动作) ---
    1:  {"group": "arm", "name": "shake hand",    "desc": "握手"},
    2:  {"group": "arm", "name": "high five",     "desc": "击掌"},
    3:  {"group": "arm", "name": "hug",           "desc": "拥抱"},
    4:  {"group": "arm", "name": "high wave",     "desc": "挥手/打招呼/招手"},
    5:  {"group": "arm", "name": "clap",          "desc": "鼓掌/拍手"},
    6:  {"group": "arm", "name": "heart",         "desc": "比心"},
    7:  {"group": "arm", "name": "hands up",      "desc": "举手/举起手"},
    8:  {"group": "arm", "name": "release arm",   "desc": "放下手/松手/放松手臂"},

    # --- Locomotion Actions (运动/姿态) ---
    9:  {"group": "loco", "name": "Squat2StandUp", "desc": "站起来/起立"},
    10: {"group": "loco", "name": "StandUp2Squat", "desc": "蹲下/下蹲"},
    11: {"group": "loco", "name": "low stand",     "desc": "低站姿/低姿态"},
    12: {"group": "loco", "name": "high stand",    "desc": "高站姿/高姿态"},
    13: {"group": "loco", "name": "move forward",  "desc": "前进/往前走/向前"},
    14: {"group": "loco", "name": "move lateral",  "desc": "横移/左移/右移/侧移"},
    15: {"group": "loco", "name": "move rotate",   "desc": "转圈/旋转/原地转"},
    # 16: {"group": "loco", "name": "damp",          "desc": "阻尼状态/放松/变软"},
    # 17: {"group": "loco", "name": "zero torque",   "desc": "零力矩模式"},
    18: {"group": "loco", "name": "wave hand1",    "desc": "摆手一/动作一"},
    19: {"group": "loco", "name": "wave hand2",    "desc": "摆手二/动作二"},
    # 20: {"group": "loco", "name": "Lie2StandUp",   "desc": "躺倒起立/起身/鲤鱼打挺"},
}

def get_action_prompt_text():
    """生成给大模型的提示词文本"""
    prompt = "【可用动作列表】\n"
    for aid, info in ACTION_MAP.items():
        prompt += f"- ID {aid}: {info['desc']}\n"
    # print(prompt)
    return prompt
