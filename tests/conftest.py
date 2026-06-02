import sys
from unittest.mock import MagicMock


# Create a master mock that can return sub-mocks for anything
class MissingModuleMock(MagicMock):
    @classmethod
    def __getattr__(cls, name):
        return MagicMock()


# Mock dependencies
sys.modules["loguru"] = MagicMock()
sys.modules["rich"] = MissingModuleMock()
sys.modules["rich.console"] = MagicMock()
sys.modules["rich.panel"] = MagicMock()
sys.modules["rich.table"] = MagicMock()
sys.modules["rich.text"] = MagicMock()
sys.modules["rich.markup"] = MagicMock()
sys.modules["rich.prompt"] = MagicMock()
sys.modules["rich.live"] = MagicMock()
sys.modules["rich.syntax"] = MagicMock()
sys.modules["rich.theme"] = MagicMock()
sys.modules["rich._emoji_codes"] = MagicMock()
sys.modules["requests"] = MissingModuleMock()


class MockRequestException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.response = kwargs.get("response")


class MockHTTPError(MockRequestException):
    pass


sys.modules["requests"].HTTPError = MockHTTPError
sys.modules["requests"].RequestException = MockRequestException
sys.modules["requests.exceptions"] = MagicMock()
sys.modules["requests.exceptions"].HTTPError = MockHTTPError
sys.modules["requests.exceptions"].RequestException = MockRequestException

sys.modules["mcp"] = MagicMock()
sys.modules["mcp.client"] = MagicMock()
sys.modules["mcp.client.stdio"] = MagicMock()
sys.modules["mcp.client.session"] = MagicMock()
sys.modules["mcp.types"] = MagicMock()
sys.modules["vlc"] = MagicMock()
sys.modules["numpy"] = MagicMock()
sys.modules["sounddevice"] = MagicMock()
sys.modules["yaml"] = MagicMock()
sys.modules["selenium"] = MagicMock()
sys.modules["openai"] = MagicMock()
sys.modules["playwright"] = MagicMock()
