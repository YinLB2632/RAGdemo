from typing import Callable

from langchain.agents import AgentState
from langchain.agents.middleware import before_model, wrap_tool_call
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from utils.logger_handler import logger


@wrap_tool_call
def monitor_tool(
    request: ToolCallRequest,
    handler: Callable[[ToolCallRequest], ToolMessage | Command],
) -> ToolMessage | Command:
    """记录工具调用及其异常。"""
    logger.info(f"[tool monitor] 执行工具：{request.tool_call['name']}")
    logger.info(f"[tool monitor] 传入参数：{request.tool_call['args']}")
    try:
        result = handler(request)
        logger.info(f"[tool monitor] 工具 {request.tool_call['name']} 调用成功")
        return result
    except Exception as exc:
        logger.error(f"工具 {request.tool_call['name']} 调用失败，原因：{exc}")
        raise


@before_model
def log_before_model(state: AgentState, runtime) -> None:
    """在模型调用前记录最后一条消息。"""
    logger.info(f"[log_before_model] 即将调用模型，带有 {len(state['messages'])} 条消息。")
    message = state["messages"][-1]
    logger.debug(f"[log_before_model] {type(message).__name__} | {message.content.strip()}")
