from openai import OpenAI
from config import ACTION_MAP, get_action_prompt_text, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


class RobotBrain:
    def __init__(self):
        self.client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_BASE_URL)
        self.model = LLM_MODEL
        # 动作判断的 Prompt
        self.action_system_prompt = (
            "你是一个机器人动作指令分类器。用户会输入一句话，请判断是否需要执行物理动作。\n"
            f"{get_action_prompt_text()}\n"
            "规则：\n"
            "1. 如果需要执行动作，请严格只返回对应的 ID 数字。\n"
            "2. 如果不需要动作或动作不在列表中，请严格只返回 -1。\n"
            "3. 只输出数字，不要标点。"
        )

    def _call_llm(self, messages, temperature=0.7):
        try:
            # print(f"Messages sent to LLM: {messages}") # 调试用
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
        """判断是否需要执行动作"""
        messages = [
            {"role": "system", "content": self.action_system_prompt},
            {"role": "user", "content": user_text}
        ]
        print(messages)
        result = self._call_llm(messages, temperature=0.0)
        print(f"🧠 Action ID Result: [{result}]")

        try:
            action_id = int(result)
            if action_id in ACTION_MAP:
                return ACTION_MAP[action_id]
        except (ValueError, TypeError):
            pass
        return None

    def get_chat_reply(self, user_text, action_data=None):
        """
        获取对话回复
        :param user_text: 用户说的话
        :param action_data: (可选) 机器人即将执行的动作字典，包含 'desc' 描述
        """

        # 基础人设
        system_prompt = "你是一个Unitree G1机器人助手，性格活泼、幽默。请用口语化、简短的方式回答用户，字数控制在40字以内。"

        # 关键修改：如果识别出了动作，将动作信息注入到 System Prompt 中
        if action_data:
            action_desc = action_data.get('desc', '未知动作')
            system_prompt += (
                f"\n【重要上下文】你即将执行物理动作：“{action_desc}”。"
                "请务必结合这个动作来回复用户，让语言和动作配合自然。"
                "例如：如果是握手，可以说'很高兴认识你（伸出手）'。"
            )
        else:
            system_prompt += "\n你当前没有执行任何物理动作，正常交流即可。"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ]
        print(messages)
        return self._call_llm(messages, temperature=0.8)