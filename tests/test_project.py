import sys
from pathlib import Path

import pytest

from opendataframework.config import Config
from opendataframework.context import Context
from opendataframework.namespace import Namespace
from opendataframework.project import Project


def make_ns():
    class Scope(Namespace): ...

    return Scope


# --- lifecycle ----------------------------------------------------------------


def test_start_and_stop():
    NS = make_ns()

    @NS
    class Cfg: ...

    project = Project(context=Context(namespaces={NS}))
    project.start()
    assert isinstance(project.context.instances[Cfg], Cfg)
    project.stop()


def test_context_manager():
    NS = make_ns()

    @NS
    class Cfg: ...

    with Project(context=Context(namespaces={NS})) as project:
        assert isinstance(project.context.instances[Cfg], Cfg)


def test_stop_before_start_is_safe():
    project = Project(context=Context(namespaces=set()))
    project.stop()  # must not raise


def test_service_lifecycle_runs_through_project():
    NS = make_ns()
    calls = []

    @NS
    class Svc:
        def setup(self) -> None:
            calls.append("setup")

        def run(self) -> None: ...

        def stop(self) -> None:
            calls.append("stop")

    with Project(context=Context(namespaces={NS})):
        pass

    assert calls == ["setup", "stop"]


# --- access ------------------------------------------------------------------


def test_context_accessible_before_start():
    project = Project(context=Context(namespaces=set()))
    assert isinstance(project.context, Context)


# --- isolation ----------------------------------------------------------------


def test_multiple_projects_are_independent():
    NS1 = make_ns()
    NS2 = make_ns()

    @NS1
    class Alpha: ...

    @NS2
    class Beta: ...

    with Project(context=Context(namespaces={NS1})) as p1:
        with Project(context=Context(namespaces={NS2})) as p2:
            assert Alpha in p1.context.instances
            assert Alpha not in p2.context.instances
            assert Beta in p2.context.instances
            assert Beta not in p1.context.instances


# --- from_dict / from_config -------------------------------------------------


def test_from_dict_returns_project():
    project = Project.from_dict({"key": "value"})
    assert isinstance(project, Project)


def test_from_dict_exposes_raw_config():
    project = Project.from_dict({"key": "value"})
    assert project.config == {"key": "value"}


def test_from_dict_config_empty_by_default():
    project = Project()
    assert project.config == {}


def test_from_dict_injects_config_into_component():
    NS = make_ns()

    @NS
    class Svc:
        def __init__(self, config: Config) -> None:
            self.config = config

    with Project(context=Context(namespaces={NS}, config={"host": "localhost"})) as project:
        instance = project.context.instances[Svc]
        assert isinstance(instance.config, Config)
        assert instance.config["host"] == "localhost"


def test_from_config_loads_toml_file(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[database]\nurl = "postgres://localhost/db"\n')

    project = Project.from_config(str(f))
    assert project.config == {"database": {"url": "postgres://localhost/db"}}


def test_from_config_merges_directory(tmp_path):
    (tmp_path / "a.toml").write_text('[db]\nhost = "localhost"\n')
    (tmp_path / "b.toml").write_text("[db]\nport = 5432\n")

    project = Project.from_config(str(tmp_path))
    assert project.config == {"db": {"host": "localhost", "port": 5432}}


def test_from_config_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        Project.from_config("/nonexistent/path/config.toml")


# --- app import -----------------------------------------------------------------


@pytest.fixture
def importable_app_package(tmp_path, monkeypatch):
    """Write a throwaway package mirroring the app/ convention used by
    examples/: a Namespace + a class registered on it, imported by the
    package's own __init__.py — isolated from the global Component/
    Service/etc. namespaces used elsewhere in the codebase."""
    pkg = tmp_path / "dummy_app"
    pkg.mkdir()
    (pkg / "ns.py").write_text(
        "from opendataframework.namespace import Namespace\n\nclass NS(Namespace): ...\n"
    )
    (pkg / "components.py").write_text(
        "from dummy_app.ns import NS\n\n@NS\nclass DummyThing: ...\n"
    )
    (pkg / "__init__.py").write_text("from dummy_app import components\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "dummy_app"
    for name in ("dummy_app", "dummy_app.ns", "dummy_app.components"):
        sys.modules.pop(name, None)


def test_from_dict_imports_configured_app(importable_app_package):
    from dummy_app import ns

    Project.from_dict({"project": {"app": importable_app_package}})

    assert ns.NS.get("dummy-thing") is not None


def test_from_dict_missing_app_module_raises():
    with pytest.raises(ImportError):
        Project.from_dict({"project": {"app": "this_module_does_not_exist_xyz"}})


def test_from_dict_app_is_optional():
    project = Project.from_dict({"project": {"log-dir": "custom"}})
    assert isinstance(project, Project)


# --- logging --------------------------------------------------------------------


def test_bare_project_does_not_log_by_default(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with Project(context=Context(namespaces=set())):
        pass

    assert not (tmp_path / "logs").exists()


def test_from_dict_defaults_log_dir_to_logs():
    project = Project.from_dict({})
    assert project.context._log_manager._dir == Path("logs")


def test_from_dict_reads_log_dir_from_config():
    project = Project.from_dict({"project": {"log-dir": "custom"}})
    assert project.context._log_manager._dir == Path("custom")


def test_project_writes_log_files_under_configured_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    NS = make_ns()

    @NS
    class A: ...

    with Project(context=Context(namespaces={NS}, log_dir="logs")):
        pass

    assert (tmp_path / "logs" / "scope.a.jsonl").exists()


# --- logging levels -------------------------------------------------------------


@pytest.mark.parametrize(
    "toml",
    [
        '[project.logging]\nevents = "WARNING"\n\n'
        '[project.logging.task]\nlevel = "ERROR"\nload = "DEBUG"\n',
        '[project.logging]\nevents = "WARNING"\ntask.level = "ERROR"\ntask.load = "DEBUG"\n',
    ],
    ids=["table", "inline"],
)
def test_from_config_passes_project_logging_to_the_context(tmp_path, toml):
    f = tmp_path / "config.toml"
    f.write_text(toml)

    log_manager = Project.from_config(str(f)).context._log_manager
    assert log_manager.threshold("task.load", "events") == 10
    assert log_manager.threshold("task.other", "events") == 40
    assert log_manager.threshold("service.db", "events") == 30


def test_from_dict_rejects_an_unknown_level_name():
    with pytest.raises(ValueError, match="LOUD"):
        Project.from_dict({"project": {"logging": {"level": "LOUD"}}})


def test_from_dict_passes_the_log_format_to_the_context():
    project = Project.from_dict({"project": {"logging": {"format": "text"}}})
    assert project.context._log_manager._format == "text"
