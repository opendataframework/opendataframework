"""Tests for main module."""

import os
import shutil

import pytest
from opendataframework import __version__
from opendataframework.__main__ import (
    SRC_PATH,
    Component,
    Entity,
    Field,
    Layer,
    Layout,
    Profile,
    Project,
    app,
    colorized_logo,
)
from typer.testing import CliRunner

TEMP_DIR = os.path.join(os.getcwd(), "tests/temp")
DATA_DIR = os.path.join(os.getcwd(), "tests/data")
CSV_FILE = os.path.join(DATA_DIR, "events.csv")
TEST_PROJECT_NAME = "myproject"
TEST_ENTITY_NAME = "event"
TEST_ENTITY_PLURAL_NAME = "events"

runner = CliRunner()


@pytest.fixture
def temp_dir():
    """Create/delete TEMP_DIR fixture."""
    assert not os.path.exists(TEMP_DIR)
    os.mkdir(TEMP_DIR)
    try:
        yield
    finally:
        shutil.rmtree(TEMP_DIR)


@pytest.fixture
def settings():
    """Creates settings.json for project configuration."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.plural_name = TEST_ENTITY_PLURAL_NAME
    entity.read()
    entity.register(Layer.API, Component.API_POSTGRES)
    project.register(entity)
    project.to_json()


def test_init(temp_dir):
    """Tests app's `init` command."""
    result = runner.invoke(
        app,
        [
            "init",
            TEST_PROJECT_NAME,
            "--path",
            TEMP_DIR,
            "--data",
            DATA_DIR,
            "--profile",
            Profile.RESEARCH,
        ],
    )
    assert result.exit_code == 0


def test_create(temp_dir, settings):
    """Tests app's `create` command."""
    result = runner.invoke(app, ["create", TEST_PROJECT_NAME, "--path", TEMP_DIR])
    assert result.exit_code == 0
    assert os.listdir(os.path.join(TEMP_DIR, TEST_PROJECT_NAME)) == [
        "ingest.py",
        "settings.json",
        "requirements.txt",
        "main.sh",
        "platform",
        "README.md",
        "expectations.py",
        "env.sh",
        "data",
    ]


def test_colorized_logo():
    """Tests `colorized_logo` function."""
    expected = "".join(
        [
            "[#00FA92]\n[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]\n[/#00FA92]",
            "[#00FA92]█[/#00FA92][#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2]",
            "[#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2][#00FA92]█[/#00FA92]",
            "[#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2]",
            "[#B36AE2]█[/#B36AE2][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]\n[/#00FA92][#00FA92]█[/#00FA92]",
            "[#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2]",
            "[#B36AE2]█[/#B36AE2][#00FA92]█[/#00FA92][#B36AE2]█[/#B36AE2]",
            "[#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2][#B36AE2]█[/#B36AE2]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]\n[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92] [/#00FA92]",
            "[bright_black]O[/bright_black][bright_black]p[/bright_black]",
            "[bright_black]e[/bright_black][bright_black]n[/bright_black]",
            "[#00FA92]\n[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92] [/#00FA92]",
            "[bright_black]D[/bright_black][bright_black]a[/bright_black]",
            "[bright_black]t[/bright_black][bright_black]a[/bright_black]",
            "[#00FA92]\n[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92]█[/#00FA92]",
            "[#00FA92]█[/#00FA92][#00FA92]█[/#00FA92][#00FA92] [/#00FA92]",
            "[bright_black]F[/bright_black][bright_black]r[/bright_black]",
            "[bright_black]a[/bright_black][bright_black]m[/bright_black]",
            "[bright_black]e[/bright_black][bright_black]w[/bright_black]",
            "[bright_black]o[/bright_black][bright_black]r[/bright_black]",
            "[bright_black]k[/bright_black][#00FA92]\n[/#00FA92]",
        ]
    )
    assert colorized_logo() == expected


def test_project_invalid_name():
    """Tests project creation with invalid name."""
    with pytest.raises(ValueError):
        Project(name="myproject!")


def test_project_relative_path(temp_dir):
    """Tests project creation using relative path."""
    path = os.path.join(TEMP_DIR, TEST_PROJECT_NAME)
    project = Project(name=TEST_PROJECT_NAME, path="tests/temp", data=DATA_DIR)
    assert project.path == path
    assert os.path.isdir(path)


def test_project_absolute_path(temp_dir):
    """Tests project creation using absolute path."""
    path = os.path.join(TEMP_DIR, TEST_PROJECT_NAME)
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    assert project.path == path
    assert os.path.isdir(path)


def test_project_invalid_data_path(temp_dir):
    """Tests project creation using invalid data path."""
    if "data" in os.listdir():
        pytest.skip(f"`data` folder exist in {os.getcwd()}")

    with pytest.raises(ValueError):
        Project(name=TEST_PROJECT_NAME, path=TEMP_DIR)


def test_project_attrs_initialize(temp_dir):
    """Tests initialized attrs on project creation."""
    path = os.path.join(TEMP_DIR, TEST_PROJECT_NAME)
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    assert project.path == path
    assert os.path.isdir(path)
    assert project.layout == Layout.CUSTOM
    assert project.settings == {
        "opendataframework": __version__,
        "project": TEST_PROJECT_NAME,
        "profile": Profile.CUSTOM,
        "layout": Layout.CUSTOM,
        "entities": {},
        "mounts": {},
        "volumes": {},
        "ports": {},
    }
    assert project._data == DATA_DIR
    assert project._api_ports == []


def test_add_custom_layout(temp_dir):
    """Tests add custom layout to project."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    assert project.layout == Layout.CUSTOM
    assert os.listdir(project.path) == ["data"]


def test_add_research_layout(temp_dir):
    """Tests add research layout to project."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    project.layout = Layout.RESEARCH
    project.add_layout()
    assert os.listdir(project.path) == os.listdir(
        os.path.join(SRC_PATH, "layouts", Layout.RESEARCH)
    )
    assert os.listdir(DATA_DIR) == os.listdir(os.path.join(project.path, "data", "raw"))


def test_entity_invalid_name():
    """Tests entity creation with invalid name."""
    with pytest.raises(ValueError):
        Entity(name="entity!", path=CSV_FILE)


def test_entity_invalid_plural_name():
    """Tests entity creation with invalid plural name."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    with pytest.raises(ValueError):
        entity.plural_name = "myproject!"


def test_entity_invalid_path():
    """Tests entity creation with invalid path."""
    with pytest.raises(ValueError):
        Entity(name=TEST_ENTITY_NAME, path=DATA_DIR)


def test_entity_attrs_initialize():
    """Tests initialized attrs on entity creation."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    assert entity.name == TEST_ENTITY_NAME
    assert entity.path == CSV_FILE


def test_entity_add_field():
    """Tests add field to entity."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)

    field = Field()
    field.field_name = "value"
    field.field_type = "1.0"
    assert field.field_type == "float"

    entity.add_field(field)
    assert entity.fields == {"value": field}


def test_field_to_dict():
    """Tests field to dict."""
    field = Field()
    field.field_name = "value"
    field.field_type = "1.0"
    assert field.to_dict() == {"value": "float"}


def test_field_timestamp():
    """Tests timestamp field."""
    field = Field()
    field.field_name = "logget_at"
    field.field_type = "2024-01-01 00:00:00"
    assert field.field_type == "datetime|%Y-%m-%d %H:%M:%S"


def test_entity_read():
    """Tests entity read."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    assert entity.fields == {}

    entity.read()
    assert list(entity.fields.keys()) == ["id", "name", "value", "logged_at"]

    fields = {field.field_name: field.field_type for field in entity.fields.values()}
    expected = {
        "id": "int",
        "name": "str",
        "value": "float",
        "logged_at": "datetime|%Y-%m-%d %H:%M:%S",
    }
    assert fields == expected


def test_entity_register():
    """Tests entity register."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.read()
    assert entity.layers == {}
    entity.register(Layer.API, Component.API_POSTGRES)
    assert entity.layers == {"api": {"api-postgres": {}}, "storage": {"postgres": {}}}


def test_entity_register_invalid_layer():
    """Tests entity register invalid layer name."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.read()
    with pytest.raises(ValueError):
        entity.register("UNDEFINED", Component.API_POSTGRES)


def test_entity_register_invalid_component():
    """Tests entity register invalid component name."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.read()
    with pytest.raises(ValueError):
        entity.register(Layer.API, "UNDEFINED")


def test_entity_to_dict():
    """Tests entity to dict."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.plural_name = TEST_ENTITY_PLURAL_NAME
    entity.read()
    assert entity.to_dict() == {
        TEST_ENTITY_PLURAL_NAME: {
            "description": "",
            "fields": {
                "id": "int",
                "logged_at": "datetime|%Y-%m-%d %H:%M:%S",
                "name": "str",
                "value": "float",
            },
            "layers": {},
            "name": TEST_ENTITY_NAME,
        }
    }


def test_entity_undefined_plural_name():
    """Tests entity undefined plural name."""
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    assert entity.plural_name == TEST_ENTITY_NAME


def test_project_register(temp_dir):
    """Tests project register."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.plural_name = TEST_ENTITY_PLURAL_NAME
    entity.read()
    entity.register(Layer.DEVCONTAINERS, Component.R)
    entity.register(Layer.UTILITY, Component.TEXLIVE)
    entity.register(Layer.API, Component.API_POSTGRES)
    project.register(entity)

    assert project.settings["entities"] == entity.to_dict()
    assert project.settings["mounts"][Component.R] == {
        "mounts": [
            ",".join(
                (
                    "source=${localWorkspaceFolder}/../../../data",
                    f"target=/{TEST_PROJECT_NAME}/data,type=bind,consistency=cached",
                )
            )
        ],
        "workspaceFolder": f"/{TEST_PROJECT_NAME}",
        "workspaceMount": ",".join(
            ("source=${localWorkspaceFolder}", f"target=/{TEST_PROJECT_NAME},type=bind")
        ),
    }
    assert project.settings["volumes"] == {
        "texlive": {
            "../data": "/usr/src/app/mnt/data",
            "./utility/texlive/mnt": "/usr/src/app/mnt",
        }
    }
    assert project.settings["opendataframework"] == __version__
    assert project.settings["project"] == project.name
    assert project.settings["ports"] == {"postgres": "5432"}


def test_project_to_json(temp_dir):
    """Tests project to json."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR, data=DATA_DIR)
    entity = Entity(name=TEST_ENTITY_NAME, path=CSV_FILE)
    entity.plural_name = TEST_ENTITY_PLURAL_NAME
    entity.read()
    entity.register(Layer.DEVCONTAINERS, Component.R)
    entity.register(Layer.UTILITY, Component.TEXLIVE)
    entity.register(Layer.API, Component.API_POSTGRES)
    project.register(entity)
    settings = project.settings

    project.to_json()
    assert os.path.exists(os.path.join(project.path, "settings.json"))

    project.from_json()
    assert settings == project.settings


def test_project_from_json(temp_dir, settings):
    """Tests project from json."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR)
    project.from_json()
    settings = {
        "entities": {
            TEST_ENTITY_PLURAL_NAME: {
                "description": "",
                "fields": {
                    "id": "int",
                    "logged_at": "datetime|%Y-%m-%d %H:%M:%S",
                    "name": "str",
                    "value": "float",
                },
                "layers": {
                    "api": {
                        "api-postgres": {
                            "port": "8000",
                        },
                    },
                    "storage": {
                        "postgres": {},
                    },
                },
                "name": TEST_ENTITY_NAME,
            },
        },
        "profile": Profile.CUSTOM,
        "layout": Layout.CUSTOM,
        "mounts": {},
        "opendataframework": __version__,
        "ports": {
            "postgres": "5432",
        },
        "project": TEST_PROJECT_NAME,
        "volumes": {},
    }
    assert project.settings == settings


def test_project_create(temp_dir, settings):
    """Tests project create."""
    project = Project(name=TEST_PROJECT_NAME, path=TEMP_DIR)
    project.create()
    assert os.listdir(project.path) == [
        "ingest.py",
        "settings.json",
        "requirements.txt",
        "main.sh",
        "platform",
        "README.md",
        "expectations.py",
        "env.sh",
        "data",
    ]

    assert os.listdir(os.path.join(project.path, "platform")) == [
        "setup.sh",
        "docker-compose.yaml",
        "storage",
        "build.sh",
        "api",
        "stop.sh",
        "start.sh",
    ]

    assert os.listdir(os.path.join(project.path, "platform", "api")) == ["api-postgres"]
    assert os.listdir(os.path.join(project.path, "platform", "storage")) == ["postgres"]
