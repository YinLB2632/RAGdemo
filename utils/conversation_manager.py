"""聊天窗口状态管理，使用 SQLite 数据库持久化存储。"""

from datetime import datetime
from uuid import uuid4

from utils.database import (
    delete_conversation as db_delete,
    init_database,
    load_all_conversations,
    save_conversation as db_save,
)


def load_conversations_from_db() -> list[dict]:
    """从数据库加载所有会话。"""
    init_database()
    return load_all_conversations()


def create_conversation(conversations: list[dict]) -> dict:
    """创建空会话并追加到显示顺序末尾，同时写入数据库。"""
    conversation = {
        "id": uuid4().hex,
        "title": "新会话",
        "messages": [],
        "created_at": datetime.now().isoformat(),
    }
    conversations.append(conversation)
    db_save(conversation)
    return conversation


def get_conversation(conversations: list[dict], conversation_id: str | None) -> dict | None:
    """按会话 ID 获取记录；找不到时由调用方决定回退策略。"""
    for conversation in conversations:
        if conversation["id"] == conversation_id:
            return conversation
    return None


def save_current_conversation(conversation: dict) -> None:
    """将当前会话状态同步到数据库。"""
    db_save(conversation)


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


def estimate_tokens(text: str) -> int:
    """字符数 ÷ 2，保守估算中英文混合文本的 Token 数量。"""
    return len(text) // 2


def count_messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_tokens(m["content"]) for m in messages)


def generate_summary(messages: list[dict]) -> str:
    """调用 chat_model 将 messages 压缩为 200~300 字摘要。"""
    from model.factory import chat_model
    from langchain_core.messages import HumanMessage

    history = "\n".join(f"[{m['role']}]: {m['content']}" for m in messages)
    prompt = f"请用200~300字总结以下对话历史，保留关键问题和结论：\n\n{history}"
    return chat_model.invoke([HumanMessage(content=prompt)]).content


def maybe_compress_history(
    conversation: dict,
    token_threshold: int,
    keep_recent_turns: int,
) -> None:
    """超过 token_threshold 时，将早期消息替换为摘要，最近 keep_recent_turns 轮始终完整保留。"""
    messages = conversation["messages"]
    keep_count = keep_recent_turns * 2
    if len(messages) <= keep_count:
        return
    if count_messages_tokens(messages) <= token_threshold:
        return

    old = messages[:-keep_count]
    recent = messages[-keep_count:]
    new_summary = generate_summary(old)
    conversation["messages"] = [{"role": "summary", "content": new_summary}] + recent
    db_save(conversation)


def prepare_context_for_agent(messages: list[dict]) -> list[dict]:
    """将内部 summary 标记转换为 Agent 可识别的 system 消息。"""
    if messages and messages[0].get("role") == "summary":
        summary_msg = {"role": "system", "content": f"[对话历史摘要]\n{messages[0]['content']}"}
        return [summary_msg] + messages[1:]
    return messages


def delete_conversation(conversations: list[dict], conversation_id: str) -> str:
    """删除指定会话，并返回删除后应该激活的会话 ID。"""
    for index, conversation in enumerate(conversations):
        if conversation["id"] != conversation_id:
            continue

        conversations.pop(index)
        db_delete(conversation_id)  # 从数据库删除

        if conversations:
            # 优先选中被删除项后面的窗口；若删除的是最后一项，则回退到前一个窗口。
            return conversations[min(index, len(conversations) - 1)]["id"]

        # 删除最后一个会话后立即补建空窗口，保证用户总能继续发起新对话。
        return create_conversation(conversations)["id"]

    # 处理重复点击或过期按钮键：保持现有第一个会话可用，不意外删除其他记录。
    _, active_conversation_id = ensure_active_conversation(conversations, None)
    return active_conversation_id
