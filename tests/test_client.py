from fanbox_archiver.client import FanboxClient
import httpx
import fanbox_archiver.client as client_module


def test_supporting_creators_accepts_current_plans_response(monkeypatch):
    client = FanboxClient(cookie="test")
    monkeypatch.setattr(client, "_get", lambda path: {"body": {"plans": [
        {"creatorId": "alice", "user": {"name": "Alice"}, "id": "plan-1"},
        {"creatorId": "alice", "user": {"name": "Alice"}, "id": "plan-2"},
        {"creatorId": "bob", "user": {"name": "Bob"}, "id": "plan-3"},
        {"user": {"name": "missing id"}},
        None,
    ]}})
    try:
        creators = client.supporting_creators()
    finally:
        client.close()
    assert [(item.creator_id, item.name) for item in creators] == [
        ("alice", "Alice"), ("bob", "Bob")
    ]


def test_supporting_creators_remains_compatible_with_items_response(monkeypatch):
    client = FanboxClient(cookie="test")
    monkeypatch.setattr(client, "_get", lambda path: {"body": {"items": [
        {"creator_id": "legacy", "creatorName": "Legacy"},
    ]}})
    try:
        creators = client.supporting_creators()
    finally:
        client.close()
    assert [(item.creator_id, item.name) for item in creators] == [("legacy", "Legacy")]


def test_creator_pagination_accepts_current_page_urls_and_posts(monkeypatch):
    client = FanboxClient(cookie="test")
    responses = {
        "post.paginateCreator": {"body": {"pageUrls": ["https://api.fanbox.cc/page/1"]}},
        "https://api.fanbox.cc/page/1": {"body": {"posts": [{
            "id": "123", "title": "Post", "updatedDatetime": "2026-01-02T03:04:05+09:00",
            "isPinned": True,
        }]}},
    }
    monkeypatch.setattr(client, "_get", lambda path, params=None: responses[path])
    try:
        pages = client.creator_post_pages("alice")
        posts = client.creator_page(pages[0])
    finally:
        client.close()
    assert pages == ["https://api.fanbox.cc/page/1"]
    assert [(item.post_id, item.title, item.updated_at, item.is_restricted) for item in posts] == [
        ("123", "Post", "2026-01-02T03:04:05+09:00", False)
    ]
    assert posts[0].is_pinned is True


def test_metadata_requests_apply_configured_interval(monkeypatch):
    clock = {"now": 100.0}
    sleeps = []

    monkeypatch.setattr(client_module.time, "monotonic", lambda: clock["now"])

    def sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(client_module.time, "sleep", sleep)
    client = FanboxClient(cookie="test", request_interval=3.0)
    client.http.close()
    client.http = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"body": []})
    ))
    try:
        client._get("plan.listSupporting")
        clock["now"] += 0.5
        client._get("plan.listSupporting")
    finally:
        client.close()
    assert sleeps == [2.5]


def test_post_can_use_authenticated_browser_payload_fetcher():
    client = FanboxClient(cookie="flattened-cookie", request_interval=0)
    client.post_payload_fetcher = lambda post_id: {"body": {
        "id": post_id, "creatorId": "alice", "title": "Public post",
        "type": "text", "body": {"text": "ok"},
    }}
    try:
        post = client.post("12810903")
    finally:
        client.close()
    assert post.post_id == "12810903"
    assert post.title == "Public post"
