from openai import OpenAI
from config import ACTION_MAP, get_action_prompt_text, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


class RobotBrain:
    def __init__(self):
        self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL

        # === 记忆模块配置 ===
        self.history = []
        # 10轮对话 = 10条用户消息 + 10条助手消息 = 20条记录
        self.max_history_items = 2

        # === 动作判断 Prompt ===
        self.action_system_prompt = (
            "你是一个机器人动作指令分类器。用户会输入一句话，请判断是否需要执行物理动作。\n"
            f"{get_action_prompt_text()}\n"
            "规则：\n"
            "1. 如果需要执行动作，请严格只返回对应的 ID 数字。\n"
            "2. 如果不需要动作或动作不在列表中，请严格只返回 -1。\n"
            "3. 只输出数字，不要标点。"
        )

    def update_history(self, role, content):
        """更新对话历史，并保持在限制长度内"""
        self.history.append({"role": role, "content": content})

        # 确保历史记录不超过设定条数 (20条)
        while len(self.history) > self.max_history_items:
            self.history.pop(0)  # 移除最老的一条

    def _call_llm(self, messages, temperature=0.7):
        try:
            # print(f"📡 Sending {len(messages)} msgs to LLM...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ LLM API Error: {str(e)}")
            return None

    def analyze_action(self, user_text):
        """判断用户意图是否包含动作"""
        messages = [
            {"role": "system", "content": self.action_system_prompt},
            {"role": "user", "content": user_text}
        ]
        # 温度为0，确保动作识别准确
        result = self._call_llm(messages, temperature=0.0)

        try:
            action_id = int(result)
            if action_id in ACTION_MAP:
                return ACTION_MAP[action_id]
        except (ValueError, TypeError):
            pass
        return None

    def get_chat_reply(self, user_text, action_data=None):
        """
        获取回复 (包含历史上下文 + 动作上下文)
        """
        # 1. 构建系统提示词
        system_prompt = "你是一个Unitree G1机器人助手，性格活泼、幽默。请用口语化、简短的方式回答用户，字数控制在30字以内。"

        # 2. 构建完整消息链：System -> History -> Current User Input
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)  # 放入最近10轮对话
        messages.append({"role": "user", "content": user_text})

        # 3. 调用 LLM
        reply = self._call_llm(messages, temperature=0.8)

        # 4. 更新记忆
        self.update_history("user", user_text)
        if reply:
            self.update_history("assistant", reply)

        return reply

    def trigger_idle_behavior(self):
        """
        闲时触发：根据最近10轮对话，决定说什么或做什么。
        返回: (回复文本, 动作字典)
        """
        # 如果完全没有历史（刚启动），可以不做任何事，或者做个随机动作
        if not self.history:
            return None, None

        prompt = (
            "现在的场景是：用户暂时没有说话，场面陷入了沉默。\n"
            "请读取上方的对话历史，作为机器人，请主动打破沉默。\n"
            "你可以：\n"
            "1. 针对刚刚的话题继续聊些不一样的东西。\n"
            "2. 发起一个全新的更有趣话题。\n"
            "3. 必须配合一个符合当前语境的动作（如伸懒腰、转圈、摊手等）。\n"
            "----------------\n"
            f"{get_action_prompt_text()}\n"
            "----------------\n"
            "【强制返回格式】：话语内容 ||| 动作ID\n"
            "示例1: 刚才聊太久了，我得活动活动筋骨。 ||| 9\n"
            "示例2: 你还在吗？我都快睡着了。 ||| 16\n"
            "如果不想做动作，ID填 -1。"
        )

        messages = [{"role": "system", "content": prompt}]
        messages.extend(self.history)  # 把历史发给它参考

        # 温度调高，增加创造性
        result = self._call_llm(messages, temperature=1.0)
        print(f"💤 Idle Thought: {result}")

        if result and "|||" in result:
            parts = result.split("|||")
            text = parts[0].strip()

            action = None
            try:
                action_id = int(parts[1].strip())
                action = ACTION_MAP.get(action_id)
            except:
                pass

            # 记录这次机器人的主动发言，避免上下文断裂
            if text:
                self.update_history("assistant", text)

            return text, action

        return None, None