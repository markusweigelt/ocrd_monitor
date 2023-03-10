from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from ocrdbrowser import ChannelClosed, OcrdBrowserFactory
from ocrdmonitor.server.settings import OcrdBrowserSettings
from tests.fakes import OcrdBrowserFake, OcrdBrowserFakeFactory
from tests.ocrdbrowser.browserdoubles import BrowserSpy, BrowserSpyFactory
from tests.ocrdmonitor.server import scraping
from tests.ocrdmonitor.server.fixtures import WORKSPACE_DIR


@pytest.fixture
def browser_spy(monkeypatch: pytest.MonkeyPatch) -> BrowserSpy:
    browser_spy = BrowserSpy()

    def factory(_: OcrdBrowserSettings) -> OcrdBrowserFactory:
        return BrowserSpyFactory(browser_spy)

    monkeypatch.setattr(OcrdBrowserSettings, "factory", factory)
    return browser_spy


@pytest.fixture
def use_browser_fakes(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    fake_factory = OcrdBrowserFakeFactory()

    def factory(_: OcrdBrowserSettings) -> OcrdBrowserFactory:
        return fake_factory

    monkeypatch.setattr(OcrdBrowserSettings, "factory", factory)
    with fake_factory:
        yield


def test__workspaces__shows_the_workspace_names_starting_from_workspace_root(
    app: TestClient,
) -> None:
    result = app.get("/workspaces")

    texts = scraping.parse_texts(result.content, "li > a")
    assert set(texts) == {"a_workspace", "another workspace", "nested/workspace"}


def test__open_workspace__passes_full_workspace_path_to_ocrdbrowser(
    browser_spy: BrowserSpy,
    app: TestClient,
) -> None:
    _ = app.get("/workspaces/open/a_workspace")

    assert browser_spy.running is True
    assert browser_spy.workspace() == str(WORKSPACE_DIR / "a_workspace")


def test__opened_workspace__when_socket_disconnects_on_broadway_side_while_viewing__shuts_down_browser(
    browser_spy: BrowserSpy,
    app: TestClient,
) -> None:
    class DisconnectingChannel:
        async def send_bytes(self, data: bytes) -> None:
            raise ChannelClosed()

        async def receive_bytes(self) -> bytes:
            raise ChannelClosed()

    browser_spy.channel = DisconnectingChannel()
    _ = app.get("/workspaces/open/a_workspace")

    with app.websocket_connect("/workspaces/view/a_workspace/socket"):
        pass

    assert browser_spy.running is False


@pytest.mark.usefixtures("use_browser_fakes")
def test__opened_workspace_browser_is_ready__when_pinging__returns_ok(
    app: TestClient,
) -> None:
    _ = app.get("/workspaces/open/a_workspace")

    result = app.get("/workspaces/ping/a_workspace")

    assert result.status_code == 200


def test__opened_workspace_browser_not_ready__when_pinging__returns_bad_gateway(
    browser_spy: BrowserSpy,
    app: TestClient,
) -> None:
    """
    We're using a browser spy here, because it's not a real server and therefore will not be reachable
    """
    _ = app.get("/workspaces/open/a_workspace")

    result = app.get("/workspaces/ping/a_workspace")

    assert result.status_code == 502
