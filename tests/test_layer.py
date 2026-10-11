import pytest

from opendataframework.component import Component
from opendataframework.function import Function
from opendataframework.layer import Analytics, Api, Layer, Messaging, Monitoring, Security, Storage
from opendataframework.namespace import Namespace


def test_layer_is_namespace_subclass():
    assert issubclass(Layer, Namespace)


def test_bare_decorator_registers_layer():
    @Layer
    class Infra(Namespace): ...

    assert Layer.get("infra") is Infra


def test_layer_class_is_namespace_subclass():
    @Layer
    class Infra(Namespace): ...

    assert issubclass(Infra, Namespace)


def test_bare_decorator_derives_kebab_name():
    @Layer
    class MachineLearning(Namespace): ...

    assert Layer.get("machine-learning") is MachineLearning


def test_positional_name_overrides_derived():
    @Layer("ml")
    class MachineLearning(Namespace): ...

    assert Layer.get("ml") is MachineLearning


def test_keyword_name_overrides_derived():
    @Layer(name="ml-kw")
    class MachineLearning(Namespace): ...

    assert Layer.get("ml-kw") is MachineLearning


def test_layer_registers_tagged_class():
    @Layer
    class Infra(Namespace): ...

    @Infra
    @Component
    class Depot: ...

    assert Infra.get("depot") is Depot


def test_layer_returns_user_class_unchanged():
    @Layer
    class Infra(Namespace): ...

    @Component
    class Depot: ...

    original = Depot
    Depot = Infra(Depot)

    assert Depot is original


def test_layer_registers_tagged_function():
    @Layer
    class Infra(Namespace): ...

    @Infra
    @Function
    def load_data(): ...

    assert Function.get("load-data") is load_data
    assert Infra.get("load-data") is load_data


def test_layer_factory_registers_function_under_custom_name():
    @Layer
    class Infra(Namespace): ...

    @Infra(name="loader")
    @Function
    def load_data(): ...

    assert dict(Infra.items()) == {"loader": load_data}


def test_layer_accepts_class_registered_in_a_custom_namespace():
    class Custom(Namespace): ...

    @Layer
    class Infra(Namespace): ...

    @Infra
    @Custom
    class Depot: ...

    assert Infra.get("depot") is Depot


def test_layer_on_unregistered_class_raises():
    @Layer
    class Infra(Namespace): ...

    with pytest.raises(TypeError, match="Infra is a layer .* got class 'Depot' — .*@Component"):

        @Infra
        class Depot: ...

    assert dict(Infra.items()) == {}


def test_layer_on_unregistered_function_raises():
    @Layer
    class Infra(Namespace): ...

    with pytest.raises(
        TypeError, match="Infra is a layer .* got function 'load_data' — .*@Function"
    ):

        @Infra(name="loader")
        def load_data(): ...

    assert dict(Infra.items()) == {}


def test_layer_under_execution_type_raises():
    """The layer runs first here, so it sees a class nothing has registered yet."""

    @Layer
    class Infra(Namespace): ...

    with pytest.raises(TypeError, match="with @Infra on top"):

        @Component
        @Infra
        class Depot: ...


def test_class_tagged_by_another_layer_only_is_not_registered():
    @Layer
    class Infra(Namespace): ...

    @Layer
    class Edge(Namespace): ...

    @Infra
    @Component
    class Depot: ...

    class Cache: ...

    Infra._namespace["cache"] = Cache

    with pytest.raises(TypeError, match="Edge is a layer"):
        Edge(Cache)


def test_builtin_layer_on_unregistered_class_raises():
    with pytest.raises(TypeError, match="Storage is a layer"):

        @Storage
        class Depot: ...


def test_plain_namespace_subclass_is_not_a_layer():
    class Infra(Namespace): ...

    @Infra
    class Depot: ...

    assert Infra.get("depot") is Depot


def test_layer_registered_in_namespace():
    @Layer
    class CustomInfra(Namespace): ...

    assert Layer.get("custom-infra") is CustomInfra


def test_get_returns_none_for_unknown():
    assert Layer.get("does-not-exist") is None


def test_layer_rejects_non_namespace_class():
    with pytest.raises(TypeError, match="must inherit from Namespace"):

        @Layer
        class Plain: ...


def test_layer_factory_rejects_non_namespace_class():
    with pytest.raises(TypeError, match="must inherit from Namespace"):

        @Layer("plain")
        class Plain: ...

    assert Layer.get("plain") is None


def test_builtin_layers_are_namespace_subclasses():
    for builtin in (Api, Storage, Analytics, Messaging, Monitoring, Security):
        assert issubclass(builtin, Namespace)


def test_builtin_layer_names():
    assert Layer.get("api") is Api
    assert Layer.get("storage") is Storage
    assert Layer.get("analytics") is Analytics
    assert Layer.get("messaging") is Messaging
    assert Layer.get("monitoring") is Monitoring
    assert Layer.get("security") is Security


def test_layer_and_component_namespaces_are_independent():
    @Layer
    class Infra(Namespace): ...

    @Infra
    @Component
    class Processor: ...

    assert Component.get("processor") is Processor
    assert Infra.get("processor") is Processor


def test_layer_rejects_function():
    with pytest.raises(TypeError, match="Layer can only decorate a class, got function 'infra'"):

        @Layer
        def infra(): ...

    assert Layer.get("infra") is None
