from datetime import datetime
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import rag.vector_store as vector_store
from openpyxl import Workbook

from agent.tools import agent_tools
from agent.react_agent import ReactAgent
from utils.conversation_manager import (
    create_conversation,
    delete_conversation,
    ensure_active_conversation,
    get_conversation,
    set_first_prompt_title,
)
from utils.file_handler import excel_loader, html_loader, listdir_with_allowed_type


def response(payload, status_code=200):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def test_react_agent_imports_without_removed_user_id_tool():
    sys.modules.pop("agent.react_agent", None)

    react_agent = importlib.import_module("agent.react_agent")

    assert hasattr(react_agent, "ReactAgent")


def test_react_agent_forwards_complete_multi_turn_history_without_mutation():
    captured_input = {}

    class FakeAgent:
        def stream(self, input_dict, stream_mode, context):
            captured_input["messages"] = input_dict["messages"]
            return [{"messages": [SimpleNamespace(content="晴天")]}]

    history = [
        {"role": "user", "content": "我在合肥"},
        {"role": "assistant", "content": "已记录"},
        {"role": "user", "content": "那边天气如何"},
    ]
    agent = ReactAgent.__new__(ReactAgent)
    agent.agent = FakeAgent()

    assert list(agent.execute_stream(history)) == ["晴天\n"]
    assert captured_input["messages"] == history
    assert history[-1]["content"] == "那边天气如何"


def test_sync_knowledge_base_once_runs_ingestion_only_for_new_session(monkeypatch):
    calls = []

    class FakeVectorStoreService:
        def load_document(self):
            calls.append("load")

    monkeypatch.setattr(vector_store, "VectorStoreService", FakeVectorStoreService)
    session_state = {}

    assert vector_store.sync_knowledge_base_once(session_state) is True
    assert session_state["knowledge_base_synced"] is True
    assert vector_store.sync_knowledge_base_once(session_state) is False
    assert calls == ["load"]


def test_conversations_keep_messages_isolated_and_title_first_prompt():
    conversations = []
    first_conversation = create_conversation(conversations)
    second_conversation = create_conversation(conversations)

    set_first_prompt_title(first_conversation, "请介绍新能源汽车充电基础设施建设的情况")
    first_conversation["messages"].append({"role": "user", "content": "第一段对话"})
    second_conversation["messages"].append({"role": "user", "content": "第二段对话"})

    assert first_conversation["title"] == "请介绍新能源汽车充电基础设施建设…"
    assert get_conversation(conversations, first_conversation["id"])["messages"] == [
        {"role": "user", "content": "第一段对话"}
    ]
    assert get_conversation(conversations, second_conversation["id"])["messages"] == [
        {"role": "user", "content": "第二段对话"}
    ]


def test_deleting_conversations_selects_fallback_and_recreates_last():
    conversations = []
    first_conversation = create_conversation(conversations)
    second_conversation = create_conversation(conversations)

    active_id = delete_conversation(conversations, first_conversation["id"])
    assert active_id == second_conversation["id"]
    assert [conversation["id"] for conversation in conversations] == [second_conversation["id"]]

    active_id = delete_conversation(conversations, second_conversation["id"])
    active_conversation, ensured_active_id = ensure_active_conversation(conversations, active_id)

    assert len(conversations) == 1
    assert active_conversation["id"] == ensured_active_id == active_id
    assert active_conversation["title"] == "新会话"
    assert active_conversation["messages"] == []


def test_get_weather_uses_geocoding_and_current_weather(monkeypatch):
    replies = iter((
        response({"results": [{"name": "Hefei", "latitude": 31.82, "longitude": 117.23}]}),
        response({"current": {"temperature_2m": 28.5, "relative_humidity_2m": 61,
                              "wind_speed_10m": 9.2, "precipitation": 0.4, "weather_code": 61}}),
    ))
    monkeypatch.setattr(agent_tools.requests, "get", lambda *args, **kwargs: next(replies))

    value = agent_tools.get_weather.invoke({"city": "合肥"})

    assert "Hefei" in value
    assert "28.5" in value
    assert "61%" in value
    assert "小雨" in value


def test_get_weather_raises_when_city_is_not_found(monkeypatch):
    monkeypatch.setattr(agent_tools.requests, "get", lambda *args, **kwargs: response({"results": []}))

    with pytest.raises(RuntimeError, match="无法找到城市"):
        agent_tools.get_weather.invoke({"city": "不存在城市"})


def test_get_user_location_returns_city_from_ip_service(monkeypatch):
    monkeypatch.setattr(
        agent_tools.requests,
        "get",
        lambda *args, **kwargs: response({"success": True, "city": "Hangzhou"}),
    )

    assert agent_tools.get_user_location.invoke({}) == "Hangzhou"


def test_get_user_location_raises_when_ip_service_fails(monkeypatch):
    monkeypatch.setattr(
        agent_tools.requests,
        "get",
        lambda *args, **kwargs: response({"success": False, "message": "blocked"}),
    )

    with pytest.raises(RuntimeError, match="获取用户位置失败"):
        agent_tools.get_user_location.invoke({})


def test_get_current_month_uses_system_clock(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 7, 23, 12, 0, 0)

    monkeypatch.setattr(agent_tools, "datetime", FixedDateTime)

    assert agent_tools.get_current_month.invoke({}) == "2026-07"


def test_external_record_tools_are_not_exposed():
    assert not hasattr(agent_tools, "fetch_external_data")
    assert not hasattr(agent_tools, "generate_external_data")


@pytest.mark.parametrize(
    ("suffix", "expected_loader"),
    (
        (".txt", "txt_loader"),
        (".pdf", "pdf_loader"),
        (".md", "markdown_loader"),
        (".docx", "docx_loader"),
        (".csv", "csv_loader"),
        (".xlsx", "excel_loader"),
        (".html", "html_loader"),
    ),
)
def test_get_file_documents_dispatches_case_insensitively(monkeypatch, suffix, expected_loader):
    expected_documents = [object()]

    for loader_name in (
        "txt_loader",
        "pdf_loader",
        "markdown_loader",
        "docx_loader",
        "csv_loader",
        "excel_loader",
        "html_loader",
    ):
        documents = expected_documents if loader_name == expected_loader else []
        monkeypatch.setattr(vector_store, loader_name, lambda _path, value=documents: value, raising=False)

    assert vector_store.get_file_documents(f"knowledge{suffix.upper()}") is expected_documents


def test_get_file_documents_returns_empty_list_for_unsupported_suffix():
    assert vector_store.get_file_documents("knowledge.epub") == []


def test_listdir_with_allowed_type_matches_uppercase_suffix(tmp_path):
    manual_path = Path(tmp_path) / "manual.DOCX"
    manual_path.write_text("content", encoding="utf-8")
    (Path(tmp_path) / "reportnotdocx").write_text("content", encoding="utf-8")
    (Path(tmp_path) / "folder.DOCX").mkdir()

    assert listdir_with_allowed_type(str(tmp_path), ("docx",)) == (str(manual_path),)
    assert listdir_with_allowed_type(str(tmp_path), (".docx",)) == (str(manual_path),)


def test_html_loader_reads_utf8_chinese_page_content(tmp_path):
    html_path = Path(tmp_path) / "ev_policy.html"
    html_path.write_text(
        "<html><head><title>政策</title></head><body><p>新能源汽车充电基础设施建设</p></body></html>",
        encoding="utf-8",
    )

    documents = html_loader(str(html_path))

    assert "新能源汽车充电基础设施建设" in documents[0].page_content


def test_excel_loader_parses_minimal_workbook(tmp_path):
    excel_path = tmp_path / "smoke.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(["topic", "value"])
    worksheet.append(["spreadsheet smoke", 42])
    workbook.save(excel_path)

    excel_documents = excel_loader(str(excel_path))

    assert excel_documents
    assert "spreadsheet smoke" in " ".join(document.page_content for document in excel_documents)
