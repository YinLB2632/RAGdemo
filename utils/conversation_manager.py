"""当前 Streamlit 页面会话内的聊天窗口状态管理。"""

from uuid import uuid4


def create_conversation(conversations: list[dict]) -> dict:
    """创建空会话并追加到显示顺序末尾。"""
    conversation = {
        "id": uuid4().hex,
        "title": "新会话",
        "messages": [],
    }
    conversations.append(conversation)
    return conversation


def get_conversation(conversations: list[dict], conversation_id: str | None) -> dict | None:
    """按会话 ID 获取记录；找不到时由调用方决定回退策略。"""
    for conversation in conversations:
        if conversation["id"] == conversation_id:
            return conversation
    return None


def ensure_active_conversation(conversations: list[dict], active_conversation_id: str | None) -> tuple[dict, str]:
    """确保页面始终有一个可显示的活动会话。"""
    active_conversation = get_conversation(conversations, active_conversation_id)
    if active_conversation is None:
        # 首次打开页面、删除最后一个窗口或活动 ID 失效时，自动补一个新窗口，避免主聊天区无可用状态。
        active_conversation = create_conversation(conversations)
    return active_conversation, active_conversation["id"]


def set_first_prompt_title(conversation: dict, prompt: str) -> None:
    """仅用首条有效用户提问更新默认会话标题。"""
    normalized_prompt = prompt.strip()
    if conversation["title"] != "新会话" or not normalized_prompt:
        return

    title_limit = 16
    # 截断标题仅用于侧栏展示，不修改原始消息内容，保证 Agent 接收的上下文完整无损。
    conversation["title"] = normalized_prompt[:title_limit]
    if len(normalized_prompt) > title_limit:
        conversation["title"] += "…"


def delete_conversation(conversations: list[dict], conversation_id: str) -> str:
    """删除指定会话，并返回删除后应该激活的会话 ID。"""
    for index, conversation in enumerate(conversations):
        if conversation["id"] != conversation_id:
            continue

        conversations.pop(index)
        if conversations:
            # 优先选中被删除项后面的窗口；若删除的是最后一项，则回退到前一个窗口。
            return conversations[min(index, len(conversations) - 1)]["id"]

        # 删除最后一个会话后立即补建空窗口，保证用户总能继续发起新对话。
        return create_conversation(conversations)["id"]

    # 处理重复点击或过期按钮键：保持现有第一个会话可用，不意外删除其他记录。
    _, active_conversation_id = ensure_active_conversation(conversations, None)
    return active_conversation_id
