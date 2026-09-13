from opendataframework.component import Component, McpTool, McpToolsProtocol
from opendataframework.namespace import Namespace


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
            return [McpTool(name="ping", description="Ping.", handler=lambda: "pong")]

    assert isinstance(Tooled(), McpToolsProtocol)


def test_mcp_tools_protocol_rejects_component_without_mcp_tools():
    class Untooled:
        def fit(self, data): ...

    assert not isinstance(Untooled(), McpToolsProtocol)


def test_mcp_tool_structured_output_defaults_to_none():
    tool = McpTool(name="ping", description="Ping.", handler=lambda: "pong")

    assert tool.structured_output is None
