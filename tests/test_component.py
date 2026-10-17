import pytest

from opendataframework.component import Component, McpTool, McpToolsProtocol
from opendataframework.context import Context
from opendataframework.function import Function
from opendataframework.namespace import Namespace


def ping() -> str:
    return "pong"


def test_component_is_namespace_subclass():
    assert issubclass(Component, Namespace)


def test_component_has_own_namespace():
    assert "_namespace" in Component.__dict__


def test_bare_decorator():
    class Foo: ...

    result = Component(Foo)

    assert result is Foo
    assert Component.get("foo") is Foo


def test_factory_decorator():
    class Bar: ...

    result = Component(name="custom-bar")(Bar)

    assert result is Bar
    assert Component.get("custom-bar") is Bar


def test_mcp_tools_protocol_detects_mcp_tools_method():
    class Tooled:
        def mcp_tools(self):
            return [McpTool(name="ping", description="Ping.", handler=ping)]

    assert isinstance(Tooled(), McpToolsProtocol)


def test_mcp_tools_protocol_rejects_component_without_mcp_tools():
    class Untooled:
        def fit(self, data): ...

    assert not isinstance(Untooled(), McpToolsProtocol)


def test_mcp_tool_structured_output_defaults_to_none():
    tool = McpTool(name="ping", description="Ping.", handler=ping)

    assert tool.structured_output is None


# --- McpTool: a described, fully typed handler --------------------------------


def test_mcp_tool_accepts_a_typed_bound_method():
    class Weather:
        def forecast(self, city: str, days: int = 3) -> dict:
            return {"city": city, "days": days}

    weather = Weather()

    tool = McpTool(name="forecast", description="Forecast.", handler=weather.forecast)

    assert tool.handler("Kyiv") == {"city": "Kyiv", "days": 3}


def test_mcp_tool_accepts_a_handler_returning_none():
    def reset() -> None: ...

    McpTool(name="reset", description="Reset.", handler=reset)


def test_mcp_tool_leaves_injected_parameters_of_a_bound_function_out():
    class NS(Namespace): ...

    @NS
    class Db: ...

    @Function
    def load_data(db: Db, path: str) -> int:
        return len(path)

    with Context(namespaces={NS, Function}) as ctx:
        tool = McpTool(name="load", description="Load rows.", handler=ctx.get(load_data))

        assert tool.handler("data.csv") == 8


@pytest.mark.parametrize("description", ["", "   ", "\n"])
def test_mcp_tool_rejects_an_empty_description(description):
    with pytest.raises(ValueError, match="MCP tool 'ping' has an empty description"):
        McpTool(name="ping", description=description, handler=ping)


def test_mcp_tool_rejects_a_handler_that_is_not_callable():
    with pytest.raises(TypeError, match="MCP tool 'ping': handler 'pong' is not callable"):
        McpTool(name="ping", description="Ping.", handler="pong")


def test_mcp_tool_rejects_a_handler_without_a_readable_signature(monkeypatch):
    def unreadable(handler):
        raise ValueError("no signature found")

    monkeypatch.setattr("opendataframework.component.inspect.signature", unreadable)

    with pytest.raises(TypeError, match="signature cannot be read") as excinfo:
        McpTool(name="ping", description="Ping.", handler=ping)

    assert "no signature found" in str(excinfo.value)


def test_mcp_tool_rejects_an_unannotated_parameter():
    def forecast(city, days: int = 3) -> dict: ...

    with pytest.raises(TypeError) as excinfo:
        McpTool(name="forecast", description="Forecast.", handler=forecast)

    message = str(excinfo.value)
    assert "MCP tool 'forecast': the handler must be fully typed" in message
    assert "parameter 'city' is not annotated" in message
    assert "'days'" not in message


def test_mcp_tool_rejects_var_positional():
    def forecast(*cities: str) -> dict: ...

    with pytest.raises(TypeError, match=r"\*cities is not allowed"):
        McpTool(name="forecast", description="Forecast.", handler=forecast)


def test_mcp_tool_rejects_var_keyword():
    def forecast(**options: str) -> dict: ...

    with pytest.raises(TypeError, match=r"\*\*options is not allowed"):
        McpTool(name="forecast", description="Forecast.", handler=forecast)


def test_mcp_tool_rejects_a_missing_return_annotation():
    def forecast(city: str): ...

    with pytest.raises(TypeError, match="the return value is not annotated"):
        McpTool(name="forecast", description="Forecast.", handler=forecast)


def test_mcp_tool_rejects_a_lambda():
    with pytest.raises(TypeError, match="the return value is not annotated"):
        McpTool(name="ping", description="Ping.", handler=lambda: "pong")


def test_mcp_tool_rejects_a_string_parameter_annotation():
    def forecast(city: str) -> dict: ...

    # What `from __future__ import annotations` leaves behind: a string.
    forecast.__annotations__ = {"city": "str", "return": dict}

    with pytest.raises(TypeError) as excinfo:
        McpTool(name="forecast", description="Forecast.", handler=forecast)

    message = str(excinfo.value)
    assert "parameter 'city' has a string annotation" in message
    assert "from __future__ import annotations" in message


def test_mcp_tool_rejects_a_string_return_annotation():
    def forecast(city: str) -> dict: ...

    forecast.__annotations__ = {"city": str, "return": "dict"}

    with pytest.raises(TypeError) as excinfo:
        McpTool(name="forecast", description="Forecast.", handler=forecast)

    message = str(excinfo.value)
    assert "the return value has a string annotation" in message
    assert "from __future__ import annotations" in message


def test_mcp_tool_reports_every_problem_at_once():
    def forecast(city, *rest: str, **options: str): ...

    with pytest.raises(TypeError) as excinfo:
        McpTool(name="forecast", description="Forecast.", handler=forecast)

    message = str(excinfo.value)
    assert "parameter 'city' is not annotated" in message
    assert "*rest is not allowed" in message
    assert "**options is not allowed" in message
    assert "the return value is not annotated" in message
    assert "from __future__ import annotations" not in message
