import time

from dotenv import load_dotenv
load_dotenv()

import streamlit as st
from agent.react_agent import ReactAgent
from rag.vector_store import sync_knowledge_base_once
from utils.config_handler import rag_conf
from utils.conversation_manager import (
    create_conversation,
    delete_conversation,
    ensure_active_conversation,
    load_conversations_from_db,
    maybe_compress_history,
    prepare_context_for_agent,
    save_current_conversation,
    set_first_prompt_title,
)

# 标题
st.title("新能源汽车智能客服")
st.divider()

# 页面会话首次打开时执行增量入库；之后提问不会重复扫描 data 目录，避免影响聊天响应速度。
if "knowledge_base_synced" not in st.session_state:
    with st.spinner("正在同步新增知识库资料..."):
        sync_knowledge_base_once(st.session_state)

if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

if "conversations" not in st.session_state:
    st.session_state["conversations"] = load_conversations_from_db()

if "active_conversation_id" not in st.session_state:
    st.session_state["active_conversation_id"] = None

# 每个会话独立保存消息；该回退确保首次进入、删除最后一个窗口后主聊天区始终有可用会话。
active_conversation, active_conversation_id = ensure_active_conversation(
    st.session_state["conversations"],
    st.session_state["active_conversation_id"],
)
st.session_state["active_conversation_id"] = active_conversation_id

with st.sidebar:
    st.header("聊天会话")
    if st.button("+ 新建会话", use_container_width=True):
        # 新窗口不复制当前历史，避免多轮上下文在不同聊天窗口之间串联。
        new_conversation = create_conversation(st.session_state["conversations"])
        st.session_state["active_conversation_id"] = new_conversation["id"]
        st.rerun()

    for conversation in st.session_state["conversations"]:
        title_column, delete_column = st.columns([4, 1])
        is_active = conversation["id"] == st.session_state["active_conversation_id"]
        if title_column.button(
            conversation["title"],
            key=f"switch_conversation_{conversation['id']}",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state["active_conversation_id"] = conversation["id"]
            st.rerun()

        if delete_column.button("删除", key=f"delete_conversation_{conversation['id']}"):
            fallback_conversation_id = delete_conversation(
                st.session_state["conversations"],
                conversation["id"],
            )
            # 删除非活动窗口时继续停留在当前对话；删除活动窗口时才切换到状态管理器给出的回退窗口。
            if is_active:
                st.session_state["active_conversation_id"] = fallback_conversation_id
            st.rerun()

for message in active_conversation["messages"]:
    if message["role"] == "summary":
        continue
    st.chat_message(message["role"]).write(message["content"])

# 用户输入提示词
prompt = st.chat_input()

if prompt:
    st.chat_message("user").write(prompt)
    set_first_prompt_title(active_conversation, prompt)
    active_conversation["messages"].append({"role": "user", "content": prompt})

    response_messages = []
    with st.spinner("智能客服思考中..."):
        conversation_messages = prepare_context_for_agent(active_conversation["messages"])
        res_stream = st.session_state["agent"].execute_stream(conversation_messages)

        def capture(generator, cache_list):

            for chunk in generator:
                cache_list.append(chunk)

                for char in chunk:
                    time.sleep(0.01)
                    yield char

        st.chat_message("assistant").write_stream(capture(res_stream, response_messages))
        # 助手回复只写入当前窗口；流式结束后保存完整内容，确保该窗口下一轮获得顺序正确的历史。
        active_conversation["messages"].append({"role": "assistant", "content": response_messages[-1]})
        save_current_conversation(active_conversation)
        maybe_compress_history(
            active_conversation,
            rag_conf["token_threshold"],
            rag_conf["keep_recent_turns"],
        )
        st.rerun()
