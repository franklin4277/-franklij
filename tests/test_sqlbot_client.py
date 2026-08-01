"""集成测试：SqlBotClient（需要 SQLBot 服务运行）

跳过条件：环境变量 SQLBOT_TEST_SKIP=1 或 SQLBot 不可达
"""
import os

import pytest

from mini_agent.data_agent import (
    SqlBotClient,
    SqlBotConfig,
    SqlBotError,
    Session,
    SessionStore,
    decode_sql_b64,
    parse_data_envelope,
)


SQLBOT_BASE = os.environ.get("SQLBOT_API_BASE", "http://localhost:18000")
SKIP = os.environ.get("SQLBOT_TEST_SKIP") == "1"


@pytest.fixture
def client():
    if SKIP:
        pytest.skip("SQLBOT_TEST_SKIP=1")
    cfg = SqlBotConfig(api_base=SQLBOT_BASE, image_base=SQLBOT_BASE.replace(":18000", ":18001"))
    return SqlBotClient(cfg)


def test_login(client):
    """login() returns access token string directly."""
    token = client.login()
    assert isinstance(token, str)
    assert len(token) > 50


def test_start_session(client):
    """start_session() returns (token, chat_id)."""
    token = client.login()
    new_token, chat_id = client.start_session(token)
    assert isinstance(new_token, str)
    assert isinstance(chat_id, int)
    assert chat_id > 0


def test_list_workspaces(client):
    token = client.login()
    ws = client.list_workspaces(token)
    assert isinstance(ws, list)
    assert len(ws) >= 1
    assert "id" in ws[0]


def test_list_datasources(client):
    token = client.login()
    ds = client.list_datasources(token)
    assert isinstance(ds, list)


def test_full_session_via_sessionstore(client, tmp_path):
    """完整流程：SessionStore + QueryService."""
    store = SessionStore(client, tmp_path)
    sess = store.create()
    assert isinstance(sess, Session)
    assert sess.is_valid()

    from mini_agent.api.deps import AskService
    service = AskService(sqlbot=client, store=store)
    ids = store.list_ids()
    sess2 = store.get(ids[0])
    ds_list = client.list_datasources(sess2.token)
    if not ds_list:
        pytest.skip("no datasources configured")

    resp = client.ask(
        token=sess2.token, chat_id=sess2.chat_id,
        question="测试问题", datasource_id=ds_list[0]["id"],
        return_img=False,
    )
    assert "success" in resp


def test_parse_helpers():
    """Response helpers work without SQLBot."""
    # decode_sql_b64
    import base64
    b64 = base64.b64encode(b"SELECT 1").decode()
    assert decode_sql_b64({"sql": b64}) == "SELECT 1"
    assert decode_sql_b64(None) == ""
    # parse_data_envelope
    fields, rows = parse_data_envelope({"fields": ["a"], "data": [{"a": 1}]})
    assert fields == ["a"] and rows == [{"a": 1}]
    fields, rows = parse_data_envelope(None)
    assert fields == [] and rows == []


if __name__ == "__main__":
    import subprocess
    subprocess.run(["pytest", __file__, "-v"])