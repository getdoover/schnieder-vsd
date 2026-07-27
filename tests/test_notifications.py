"""Notification payload tests.

The server (doover-data `NotificationChannelMessagePayload`) parses the
`notifications` channel payload with serde and, on failure, falls back to
using the *raw JSON* as the notification text. That fallback is silent, so a
malformed payload shows up only as unreadable notifications on someone's
phone — hence these tests guard the wire format.
"""

import pytest

from pydoover.models import NotificationSeverity

from schneider_vsd.application import SchneiderVsdApplication


# Exact variant names accepted by the server enum. The enum has no serde
# repr, so integers and lowercase names are both rejected.
VALID_SEVERITIES = {"Trace", "Debug", "Info", "Warn", "Critical"}


class _CaptureApp:
    """Minimal stand-in exposing just what `_notify` touches."""

    def __init__(self):
        self.messages = []

    async def create_message(self, channel, data):
        self.messages.append((channel, data))

    _notify = SchneiderVsdApplication._notify


@pytest.mark.asyncio
async def test_notify_payload_shape():
    app = _CaptureApp()
    await app._notify(
        message="Drain VSD motor stopped",
        title="Drain VSD stopped",
        severity=NotificationSeverity.Info,
    )

    channel, payload = app.messages[0]
    assert channel == "notifications"
    assert payload == {
        "message": "Drain VSD motor stopped",
        "severity": "Info",
        "title": "Drain VSD stopped",
    }


@pytest.mark.asyncio
async def test_notify_severity_is_variant_name_not_int():
    app = _CaptureApp()
    for severity in NotificationSeverity:
        await app._notify(message="m", severity=severity)

    for _, payload in app.messages:
        assert payload["severity"] in VALID_SEVERITIES
        assert not isinstance(payload["severity"], int)


@pytest.mark.asyncio
async def test_notify_omits_title_when_unset():
    app = _CaptureApp()
    await app._notify(message="m")

    _, payload = app.messages[0]
    assert "title" not in payload
    # `body` is not part of the server payload — sending it is harmless but
    # it was never rendered, so it must not creep back in.
    assert "body" not in payload
    assert payload["severity"] == "Info"
