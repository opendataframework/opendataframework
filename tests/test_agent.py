import pytest

from opendataframework.agent import Agent, AgentProtocol
from opendataframework.component import Component
from opendataframework.namespace import Namespace


def test_agent_is_namespace_subclass():
    assert issubclass(Agent, Namespace)


def test_agent_has_own_namespace():
    assert "_namespace" in Agent.__dict__


def test_agent_namespace_is_independent_from_component():
    assert Agent._namespace is not Component._namespace


def test_bare_decorator():
    class Researcher:
        def invoke(self, question): ...

    result = Agent(Researcher)

    assert result is Researcher
    assert Agent.get("researcher") is Researcher


def test_keyword_name():
    class Researcher:
        def invoke(self, question): ...

    result = Agent(name="researcher-kw")(Researcher)

    assert result is Researcher
    assert Agent.get("researcher-kw") is Researcher


def test_positional_name():
    class Researcher:
        def invoke(self, question): ...

    result = Agent("researcher-pos")(Researcher)

    assert result is Researcher
    assert Agent.get("researcher-pos") is Researcher


def test_get_accepts_any_casing():
    @Agent
    class CatalogueAssistant:
        def invoke(self): ...

    assert Agent.get("CatalogueAssistant") is CatalogueAssistant
    assert Agent.get("catalogue_assistant") is CatalogueAssistant
    assert Agent.get("catalogue-assistant") is CatalogueAssistant


def test_get_returns_none_for_unknown_name():
    assert Agent.get("unknown") is None


def test_registration_does_not_leak_to_component():
    class Standalone:
        def invoke(self): ...

    Agent(Standalone)

    assert Component.get("standalone") is None


def test_bare_decorator_requires_invoke():
    class NoInvoke: ...

    with pytest.raises(TypeError, match=r"defines invoke\(\), got 'NoInvoke'"):
        Agent(NoInvoke)

    assert Agent.get("no-invoke") is None


def test_factory_decorator_requires_invoke():
    class NoInvoke: ...

    with pytest.raises(TypeError, match=r"defines invoke\(\), got 'NoInvoke'"):
        Agent(name="no-invoke-kw")(NoInvoke)

    assert Agent.get("no-invoke-kw") is None


def test_non_callable_invoke_is_rejected():
    class NotAMethod:
        invoke = "nope"

    with pytest.raises(TypeError, match=r"defines invoke\(\)"):
        Agent(NotAMethod)


def test_inherited_invoke_is_accepted():
    class Base:
        def invoke(self): ...

    class Child(Base): ...

    assert Agent(Child) is Child


def test_bare_decorator_rejects_a_function():
    def researcher(): ...

    with pytest.raises(TypeError, match="can only decorate a class"):
        Agent(researcher)


def test_factory_decorator_rejects_a_function():
    def researcher(): ...

    with pytest.raises(TypeError, match="can only decorate a class"):
        Agent(name="researcher-fn")(researcher)


def test_agent_protocol_satisfied_by_invoke():
    class Researcher:
        def invoke(self, question: str) -> str: ...

    assert isinstance(Researcher(), AgentProtocol)


def test_agent_protocol_not_satisfied_without_invoke():
    class NotAnAgent: ...

    assert not isinstance(NotAnAgent(), AgentProtocol)
