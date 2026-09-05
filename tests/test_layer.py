from opendataframework.component import Component
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
    class Infra2(Namespace): ...

    @Infra2
    class Database: ...

    assert Infra2.get("database") is Database


def test_layer_returns_user_class_unchanged():
    @Layer
    class Infra3(Namespace): ...

    class Database: ...

    original = Database
    Database = Infra3(Database)

    assert Database is original


def test_layer_registered_in_namespace():
    @Layer
    class CustomInfra(Namespace): ...

    assert Layer.get("custom-infra") is CustomInfra


def test_get_returns_none_for_unknown():
    assert Layer.get("does-not-exist") is None


def test_layer_rejects_non_namespace_class():
    import pytest

    with pytest.raises(TypeError, match="must inherit from Namespace"):

        @Layer
        class Plain: ...


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
    class Infra4(Namespace): ...

    @Infra4
    @Component
    class Processor: ...

    assert Component.get("processor") is Processor
    assert Infra4.get("processor") is Processor
