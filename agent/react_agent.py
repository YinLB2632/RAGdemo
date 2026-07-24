from langchain.agents import create_agent
from model.factory import chat_model
from utils.prompt_loader import load_system_prompts
from agent.tools.agent_tools import (rag_summarize, get_weather, get_user_location,
                                     get_current_month)
from agent.tools.middleware import monitor_tool, log_before_model


class ReactAgent:
    def __init__(self):
        self.agent = create_agent(
            model=chat_model,
            system_prompt=load_system_prompts(),
            tools=[rag_summarize, get_weather, get_user_location, get_current_month],
            middleware=[monitor_tool, log_before_model],
        )

    def execute_stream(self, messages: list[dict[str, str]]):
        # 调用方传入按时间排序的完整会话历史；这里仅读取它，避免 Agent 处理过程改写 Streamlit 状态。
        input_dict = {
            "messages": messages,
        }

        # 第三个参数context就是上下文runtime中的信息，就是我们做提示词切换的标记
        for chunk in self.agent.stream(input_dict, stream_mode="values", context={"report": False}):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"


if __name__ == '__main__':
    agent = ReactAgent()

    for chunk in agent.execute_stream([{"role": "user", "content": "给我生成我的使用报告"}]):
        print(chunk, end="", flush=True)
