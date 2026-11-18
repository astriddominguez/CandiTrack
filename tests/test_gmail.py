import base64
from datetime import UTC, datetime
from unittest.mock import MagicMock

from canditrack.mail.gmail import NUM_RETRIES, GmailSource, parse_message


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def make_message(msg_id: str = "m1", payload: dict | None = None) -> dict:
    return {
        "id": msg_id,
        "threadId": "t1",
        "internalDate": "1763370000000",
        "snippet": "Gracias por tu candidatura &amp; tu tiempo",
        "payload": payload
        or {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "RRHH <rrhh@empresa.com>"},
                {"name": "Subject", "value": "Tu candidatura"},
            ],
            "body": {"data": b64("Hola, hemos recibido tu candidatura.")},
        },
    }


def test_parse_simple_plain_message():
    email = parse_message(make_message())

    assert email.id == "m1"
    assert email.thread_id == "t1"
    assert email.sender == "RRHH <rrhh@empresa.com>"
    assert email.subject == "Tu candidatura"
    assert email.body == "Hola, hemos recibido tu candidatura."
    assert email.snippet == "Gracias por tu candidatura & tu tiempo"
    assert email.date == datetime.fromtimestamp(1763370000, tz=UTC)


def test_parse_multipart_prefers_plain_text():
    payload = {
        "mimeType": "multipart/alternative",
        "headers": [{"name": "subject", "value": "Entrevista"}],
        "parts": [
            {"mimeType": "text/html", "body": {"data": b64("<p>HTML</p>")}},
            {"mimeType": "text/plain", "body": {"data": b64("Texto plano")}},
        ],
    }
    email = parse_message(make_message(payload=payload))

    assert email.subject == "Entrevista"
    assert email.body == "Texto plano"
    assert email.html_text == "HTML"


def test_parse_html_only_is_converted_to_text():
    html = "<html><style>p{}</style><p>Hola&nbsp;Ana</p><p>Te <b>esperamos</b></p></html>"
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [{"mimeType": "text/html", "body": {"data": b64(html)}}],
    }
    email = parse_message(make_message(payload=payload))

    assert email.body == "Hola\xa0Ana\nTe esperamos"


def test_parse_message_without_body():
    email = parse_message(make_message(payload={"mimeType": "text/plain", "body": {}}))

    assert email.body == ""
    assert email.html_text == ""
    assert email.sender == ""


def test_fetch_follows_pagination_and_respects_max_results():
    service = MagicMock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.side_effect = [
        {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "p2"},
        {"messages": [{"id": "c"}, {"id": "d"}]},
    ]
    messages.get.side_effect = lambda userId, id, format: MagicMock(
        execute=MagicMock(return_value=make_message(msg_id=id))
    )

    emails = GmailSource(service).fetch(query="label:inbox", max_results=3)

    assert [e.id for e in emails] == ["a", "b", "c"]
    assert messages.list.call_count == 2
    assert messages.list.call_args_list[0].kwargs["q"] == "label:inbox"


def test_fetch_retries_on_rate_limit():
    service = MagicMock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value.execute.return_value = {"messages": [{"id": "a"}]}
    get_request = messages.get.return_value
    get_request.execute.return_value = make_message(msg_id="a")

    GmailSource(service).fetch(max_results=1)

    messages.list.return_value.execute.assert_called_once_with(num_retries=NUM_RETRIES)
    get_request.execute.assert_called_once_with(num_retries=NUM_RETRIES)
