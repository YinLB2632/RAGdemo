"""聊天记录数据库管理模块。"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

# 数据库文件路径
DB_PATH = Path("conversations.db")


def init_database() -> None:
    """初始化数据库表结构。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 创建会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 创建消息表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    """)

    # 创建索引提升查询性能
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
        ON messages (conversation_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
        ON conversations (updated_at DESC)
    """)

    conn.commit()
    conn.close()


def load_all_conversations() -> list[dict]:
    """从数据库加载所有会话（按更新时间降序）。"""
    init_database()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 查询所有会话
    cursor.execute("""
        SELECT id, title, created_at, updated_at
        FROM conversations
        ORDER BY updated_at DESC
    """)

    conversations = []
    for row in cursor.fetchall():
        conversation_id = row["id"]

        # 查询该会话的所有消息
        cursor.execute("""
            SELECT role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id ASC
        """, (conversation_id,))

        messages = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in cursor.fetchall()
        ]

        conversations.append({
            "id": conversation_id,
            "title": row["title"],
            "messages": messages,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        })

    conn.close()
    return conversations


def save_conversation(conversation: dict) -> bool:
    """保存或更新会话到数据库。"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        now = datetime.now().isoformat()

        # 检查会话是否已存在
        cursor.execute("SELECT id FROM conversations WHERE id = ?", (conversation["id"],))
        exists = cursor.fetchone() is not None

        if exists:
            # 更新会话
            cursor.execute("""
                UPDATE conversations
                SET title = ?, updated_at = ?
                WHERE id = ?
            """, (conversation["title"], now, conversation["id"]))
        else:
            # 插入新会话
            created_at = conversation.get("created_at", now)
            cursor.execute("""
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
            """, (conversation["id"], conversation["title"], created_at, now))

        # 删除旧消息
        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation["id"],))

        # 插入所有消息
        for message in conversation["messages"]:
            cursor.execute("""
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
            """, (conversation["id"], message["role"], message["content"], now))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"保存会话失败: {e}")
        return False


def delete_conversation(conversation_id: str) -> bool:
    """从数据库删除会话及其所有消息。"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 由于设置了 ON DELETE CASCADE，删除会话会自动删除关联消息
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

        conn.commit()
        conn.close()
        return True

    except Exception as e:
        print(f"删除会话失败: {e}")
        return False


def get_conversation(conversation_id: str) -> Optional[dict]:
    """根据ID获取单个会话。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, created_at, updated_at
        FROM conversations
        WHERE id = ?
    """, (conversation_id,))

    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    # 查询消息
    cursor.execute("""
        SELECT role, content
        FROM messages
        WHERE conversation_id = ?
        ORDER BY id ASC
    """, (conversation_id,))

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in cursor.fetchall()
    ]

    conn.close()

    return {
        "id": row["id"],
        "title": row["title"],
        "messages": messages,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
