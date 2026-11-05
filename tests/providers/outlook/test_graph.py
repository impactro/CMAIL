"""Focused graph regression tests."""
from urllib.parse import parse_qs, urlsplit
from cmail.graph import MicrosoftGraphProvider, allowed_graph_route
from helpers import (FakeTokenAuth)


def test_graph_provider_uses_only_me_routes_and_normalizes_mail():
    calls = []
    def requester(method, path, token, payload, headers):
        calls.append((method, path, token, payload, headers))
        if path.startswith("/me/mailFolders/inbox?"):
            return 200, {"id": "folder-1"}
        if "mailFolders?" in path:
            return 200, {"value": [{"id": "folder-1", "displayName": "Entrada", "unreadItemCount": 2}]}
        if "messages?" in path:
            return 200, {"value": [{
                "id": "message-1", "subject": "<img src=x onerror=alert(1)>",
                "from": {"emailAddress": {"name": "<b>Remetente</b>", "address": "a@example.com"}},
                "bodyPreview": "Resumo", "isRead": False,
            }]}
        if method == "PATCH": return 200, {"id": "message-1", "isRead": True}
        if path.endswith("/move"): return 201, {"id": "message-2"}
        if path == "/me/sendMail": return 202, {}
        if path == "/me/calendar/getSchedule":
            return 200, {"value": [{"scheduleId": "a@example.com", "availabilityView": "0", "scheduleItems": []}]}
        return 200, {}
    selected = MicrosoftGraphProvider(FakeTokenAuth(), "identity-1", requester=requester)
    folder = selected.folders()[0]
    assert folder["unread"] == 2
    assert folder["wellKnownName"] == "inbox"
    message = selected.messages("folder-1")[0]
    assert message["subject"].startswith("<img")
    assert selected.set_read("message-1", True)["isRead"] is True
    assert selected.move("message-1", "folder-2")["moved"] is True
    assert selected.send(["a@example.com"], "Assunto", "Corpo")["accepted"] is True
    assert selected.availability(
        ["a@example.com"], "2026-09-12T08:00:00", "2026-09-12T09:00:00",
        "E. South America Standard Time", 30,
    )["count"] == 1
    assert all(path.startswith("/me/") for _, path, *_ in calls)
    assert all(token == "memory-only-token" for _, _, token, *_ in calls)
    list_path = next(path for _, path, *_ in calls if "/me/mailFolders?" in path)
    assert "wellKnownName" not in list_path


def test_graph_provider_searches_directory_with_bounded_users_route():
    calls = []

    def requester(method, path, token, payload, headers):
        calls.append((method, path, token, payload, headers))
        assert method == "GET"
        assert payload is None
        assert headers == {"ConsistencyLevel": "eventual"}
        return 200, {"value": [{
            "id": "user-1", "displayName": "Fábio Souza",
            "mail": "fabio@example.test", "userPrincipalName": "fabio@example.test",
        }]}

    selected = MicrosoftGraphProvider(FakeTokenAuth(), "identity-1", requester=requester)
    people = selected.directory("Fábio Souza", 12)

    assert people == [{
        "id": "user-1", "name": "Fábio Souza", "email": "fabio@example.test",
        "department": "", "jobTitle": "",
    }]
    assert len(calls) == 1
    _method, path, token, _payload, _headers = calls[0]
    assert path.startswith("/users?")
    query = parse_qs(urlsplit(path).query)
    assert query["$select"] == ["id,displayName,givenName,surname,mail,userPrincipalName"]
    assert query["$top"] == ["12"]
    assert query["$count"] == ["true"]
    assert query["$search"] == ['"displayName:Fábio Souza" OR "mail:Fábio Souza"']
    assert token == "memory-only-token"
    assert allowed_graph_route("GET", path)
    assert not allowed_graph_route("POST", path)
    assert not allowed_graph_route("GET", "/users/user-1")
