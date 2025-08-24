"""Main module."""

import csv
import json
import os
import re
import shutil
import stat
import subprocess
import traceback
import uuid
import venv
import yaml
from datetime import datetime
from pathlib import Path

import typer
from rich import print as rprint
from rich.prompt import Prompt

from opendataframework import __version__

PLATFORM_FOLDER = "platform"
IGNORE_PATTERNS = (
    "__pycache__",
    ".DS_Store",
    ".gitkeep",
    ".venv",
    "venv",
)
SRC_PATH = Path(__file__).parent


def colorized_logo() -> str:
    """Returns colorized logo."""
    logo = "\n".join(
        [
            "",
            "█████████████",
            "█████████████",
            "█████████████",
            "█████████████ Open",
            "█████████████ Data",
            "█████████████ Framework",
            "",
        ]
    )
    colorized = ""
    for i, symbol in enumerate(logo):
        if i in {16, 17, 18, 19, 21, 22, 23, 24, 30, 31, 32, 33, 35, 36, 37, 38}:
            colorized += f"[#B36AE2]{symbol}[/#B36AE2]"
        elif i in {57, 58, 59, 60}:
            # Open
            colorized += f"[bright_black]{symbol}[/bright_black]"
        elif i in {76, 77, 78, 79}:
            # Data
            colorized += f"[bright_black]{symbol}[/bright_black]"
        elif i in {95, 96, 97, 98, 99, 100, 101, 102, 103}:
            # Framework
            colorized += f"[bright_black]{symbol}[/bright_black]"
        else:
            colorized += f"[#00FA92]{symbol}[/#00FA92]"
    return colorized


class Layout:
    """Layout names."""

    CUSTOM: str = "custom"
    DATA_ANALYTICS: str = "data_analytics"
    DATA_ENGENEERING: str = "data_engineering"
    DATA_SCIENCE: str = "data_science"
    RESEARCH: str = "research"


class Profile:
    """Profile names."""

    CUSTOM: str = "custom"
    DATA_ANALYTICS: str = "data_analytics"
    DATA_ENGENEERING: str = "data_engineering"
    DATA_SCIENCE: str = "data_science"
    RESEARCH: str = "research"


class Layer:
    """Layer names."""

    ANALYTICS: str = "analytics"
    API: str = "api"
    DEVCONTAINERS: str = "devcontainers"
    STORAGE: str = "storage"
    UTILITY: str = "utility"


class Component:
    """Component names."""

    # ANALYTICS
    SUPERSET: str = "superset"

    # API
    API_DRUID: str = "api-druid"
    API_JSON_KAFKA: str = "api-json-kafka"
    API_POSTGRES: str = "api-postgres"
    INFERENCE: str = "inference"

    # DEVCONTAINERS
    GO: str = "go"
    PYTHON: str = "python"
    R: str = "R"

    # STORAGE
    DRUID: str = "druid"
    KAFKA: str = "kafka"
    POSTGRES: str = "postgres"

    # UTILITY
    TEXLIVE = "texlive"


PROJECT_NAME = "project_name"
JSON_INDENT = 2
FILE_FORMATS = {
    ".csv",
}


class Settings:
    JSON = 'json'
    YAML = 'yaml'


COMPONENTS = {
    Layer.ANALYTICS: [Component.SUPERSET],
    Layer.DEVCONTAINERS: [Component.GO, Component.PYTHON, Component.R],
    Layer.API: [
        Component.API_DRUID,
        Component.API_JSON_KAFKA,
        Component.API_POSTGRES,
        Component.INFERENCE,
    ],
    Layer.STORAGE: [Component.KAFKA, Component.POSTGRES],
    Layer.UTILITY: [Component.TEXLIVE],
}

DEPENDENCIES = {
    # API
    Component.API_JSON_KAFKA: {Layer.STORAGE: [Component.KAFKA]},
    Component.API_POSTGRES: {Layer.STORAGE: [Component.POSTGRES]},
}

ENTIIES = {
    Component.API_POSTGRES: {
        "name": "models",
        "type": "list"
    },
    Component.SUPERSET: {
        "name": "datasets",
        "type": "list"
    },
    Component.POSTGRES: {
        "name": "tables",
        "type": "list"
    }
}


DESCRIPTIONS = {
    # ANALYTICS
    Component.SUPERSET: "Apache Superset is a modern, enterprise-ready business intelligence web application",  # noqa
    # API
    Component.API_DRUID: "REST Data Access for Druid",
    Component.API_JSON_KAFKA: "REST Data Access for Kafka",
    Component.API_POSTGRES: "REST Data Access for Postgres",
    # DEVCONTAINERS
    Component.GO: "VS Code devcontainer for GO",
    Component.PYTHON: "VS Code devcontainer for Python",
    Component.R: "VS Code devcontainer for R",
    # STORAGE
    Component.KAFKA: "Apache Kafka is an open-source distributed event streaming platform",  # noqa
    Component.POSTGRES: "Advanced Relational Database",
    # UTILITY
    Component.TEXLIVE: "TeX Live is intended to be a straightforward way to get up and running with the TeX document production system",  # noqa
}


PORTS = {
    # ANALYTICS
    Component.SUPERSET: "8088",
    # API
    Component.API_DRUID: "8000",
    Component.API_JSON_KAFKA: "8000",
    Component.API_POSTGRES: "8000",
    Component.INFERENCE: "8000",
    # STORAGE
    Component.KAFKA: "9092",
    Component.POSTGRES: "5432",
}


VOLUMES = {
    # UTILITY
    Component.TEXLIVE: {
        Layout.CUSTOM: {
            "./utility/texlive/mnt": "/usr/src/app/mnt",
            "../data": "/usr/src/app/mnt/data",
        },
        Layout.RESEARCH: {
            "../output": "/usr/src/app/mnt/output",
            "../paper": "/usr/src/app/mnt/paper",
        },
    },
}


MOUNTS = {
    Component.GO: {
        "workspaceMount": ",".join(
            ("source=${{localWorkspaceFolder}}", "target=/{project_name}", "type=bind")
        ),
        "workspaceFolder": "/{project_name}",
        "mounts": [
            ",".join(
                (
                    "source=${{localWorkspaceFolder}}/../../../data",
                    "target=/{project_name}/data",
                    "type=bind",
                    "consistency=cached",
                )
            )
        ],
    },
    Component.PYTHON: {
        "workspaceMount": ",".join(
            ("source=${{localWorkspaceFolder}}", "target=/{project_name}", "type=bind")
        ),
        "workspaceFolder": "/{project_name}",
        "mounts": [
            ",".join(
                (
                    "source=${{localWorkspaceFolder}}/../../../data",
                    "target=/{project_name}/data",
                    "type=bind",
                    "consistency=cached",
                )
            )
        ],
    },
    Component.R: {
        "workspaceMount": ",".join(
            ("source=${{localWorkspaceFolder}}", "target=/{project_name}", "type=bind")
        ),
        "workspaceFolder": "/{project_name}",
        "mounts": [
            ",".join(
                (
                    "source=${{localWorkspaceFolder}}/../../../data",
                    "target=/{project_name}/data",
                    "type=bind",
                    "consistency=cached",
                )
            )
        ],
    },
}


LAYOUTS = {Layout.CUSTOM, Layout.RESEARCH}


PROFILES = {Profile.CUSTOM, Profile.RESEARCH}


BADGES = {
    Layer.ANALYTICS: "badge badge-info gap-2",
    Layer.API: "badge badge-accent gap-2",
    Layer.STORAGE: "badge badge-warning gap-2",
    Layer.UTILITY: "badge badge-secondary gap-2",
}


class Field:
    """Field."""

    UID_FIELD = "uid"
    TS_FILED = "ts"

    RESERVED_FIELDS = {UID_FIELD, TS_FILED}

    TS_FRMTS = {"%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M:%S"}

    def __init__(self):
        """Create field instance."""
        self._field_name = None
        self._field_type = None
        self._field_alias = None

    @property
    def field_name(self) -> str:
        """Get field name."""
        return self._field_name

    @field_name.setter
    def field_name(self, value: str) -> None:
        """Set field name."""
        value = re.sub("[^A-Za-z0-9]+", "_", value).lower()
        if not re.compile("^[a-zA-Z0-9_]+$").match(value):
            raise ValueError(f"Invalid field name: {value}")

        if value in self.RESERVED_FIELDS:
            raise ValueError(f"Field names `{self.RESERVED_FIELDS}` are reserved")
        self._field_name = value

    @property
    def field_alias(self) -> str:
        """Get field alias."""
        return self._field_alias

    @field_alias.setter
    def field_alias(self, value: str) -> None:
        """Set field alias."""
        self._field_alias = value

    @property
    def field_type(self) -> str:
        """Get field type."""
        return self._field_type

    @field_type.setter
    def field_type(self, value: str) -> None:
        """Set field type."""
        if value.isdigit():
            self._field_type = "int"
            return

        try:
            float(value)
            self._field_type = "float"
            return
        except ValueError:
            pass

        for ts_frmt in self.TS_FRMTS:
            try:
                datetime.strptime(value, ts_frmt)
                self._field_type = f"datetime|{ts_frmt}"
                return
            except ValueError:
                continue

        self._field_type = "str"

    def to_dict(self) -> dict:
        """Create dict representation."""
        return {self.field_name: {"type": self.field_type, "alias": self.field_alias}}


class Entity:
    """Entity."""

    def __init__(self, name: str, path: str):
        """Create entity instance."""
        self._name = None
        self._path = None
        self._plural_name = None
        self._description = ""

        self.name = name
        self.path = path
        self.plural_name = name

        self._fields = {}

    @property
    def fields(self):
        """Get fields."""
        return self._fields

    @property
    def name(self) -> str:
        """Get name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set name."""
        if not re.compile("^[a-zA-Z0-9_]+$").match(value):
            raise ValueError(f"Invalid name: {value}")
        self._name = value.lower()

    @property
    def plural_name(self) -> str:
        """Get plural name."""
        return self._plural_name

    @plural_name.setter
    def plural_name(self, value: str) -> None:
        """Set plural name."""
        if not re.compile("^[a-zA-Z0-9_]+$").match(value):
            raise ValueError(f"Invalid name: {value}")
        self._plural_name = value

    @property
    def description(self) -> str:
        """Get description."""
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        """Set description."""
        self._description = value

    @property
    def path(self) -> str:
        """Get entity path."""
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        """Set entity path."""
        path = os.path.join(os.getcwd(), value)
        if not path.endswith(".csv"):
            raise ValueError("Path should end with `.csv`")

        if not os.path.exists(path):
            raise ValueError(f"{path} does not exists")

        self._path = path

    def read(self, newline="") -> None:
        """Read field names & types from csv."""
        with open(self.path, newline=newline) as csv_file:
            reader = csv.DictReader(csv_file)
            try:
                row = next(reader)
            except StopIteration:
                return

            for key, value in row.items():
                field = Field()
                field.field_name = key
                field.field_type = value
                field.field_alias = key
                self.add_field(field)

    def add_field(self, field: Field, key: str = None) -> None:
        """Add field."""
        if key:
            self._fields[key] = field
        else:
            self._fields[field.field_name] = field

    def to_dict(self) -> dict:
        """Create dict representation."""
        return {
            self.plural_name: {
                "name": self.name,
                "description": self.description,
                "fields": {
                    k: {"type": v.field_type, "alias": v.field_alias}
                    for k, v in self.fields.items()
                }
            }
        }


class Project:
    """Project."""

    def __init__(self, name: str, path: str = "", data: str = "", models: str = ""):
        """Create project instance."""
        self._name = None
        self._path = None
        self._profile = Profile.CUSTOM
        self._layout = Layout.CUSTOM
        self._models = None

        if data:
            self._data = os.path.join(os.getcwd(), data)
        else:
            self._data = os.path.join(os.getcwd(), "data")
        if models:
            self._models = os.path.join(os.getcwd(), models)

        self._settings = {
            "opendataframework": __version__,
            "project": "",
            "profile": self._profile,
            "layout": self._layout,
            "data": {},
            "platform": {}
        }
        self.name = name
        self.path = path

        self._api_ports = []

    @property
    def name(self) -> str:
        """Get project name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set project name."""
        if not re.compile("^[a-zA-Z0-9_]+$").match(value):
            raise ValueError(f"Invalid name: {value}")
        self._name = value.lower()
        self._settings["project"] = self._name

    @property
    def path(self) -> str:
        """Get project path."""
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        """Set project path."""
        path = os.path.join(os.getcwd(), value)

        if not os.path.exists(path):
            raise ValueError(f"{path} does not exists")

        path = os.path.join(path, self.name)
        if not os.path.exists(path):
            os.mkdir(path)
            rprint(f"{path}[green] created[/green]")

        data_path = os.path.join(path, "data")
        if not os.path.exists(data_path):
            os.mkdir(data_path)
            rprint(f"{data_path}[green] created[/green]")

            if not os.path.exists(self._data):
                raise ValueError(f"{self._data} not found")

            for file_name in os.listdir(self._data):
                if file_name.endswith(".csv"):
                    source_path = os.path.join(self._data)
                    dest_path = os.path.join(data_path)
                    self.copy(source_path, dest_path, file_name)
                    rprint(f"{file_name}[green] copied to [/green]{dest_path}")

        self._path = path

        if not self._models:
            models = os.path.join(os.getcwd(), "models")
            if not os.path.exists(models):
                return
            self._models = models

        models_path = os.path.join(path, "models")
        if not os.path.exists(models_path):
            os.mkdir(models_path)
            rprint(f"{models_path}[green] created[/green]")

            for folder in os.listdir(self._models):
                source_path = os.path.join(self._models, folder)
                if os.path.isdir(source_path):
                    dest_path = os.path.join(models_path, folder)
                    if not os.path.exists(dest_path):
                        os.mkdir(dest_path)

                    for file_name in os.listdir(source_path):
                        supported = [
                            file_name.strip().lower() == "model.pkl",
                            file_name.strip().lower() == "model.json",
                            file_name.strip().lower() == "requirements.txt",
                        ]
                        if not any(supported):
                            continue
                        self.copy(source_path, dest_path, file_name)
                        rprint(f"{file_name}[green] copied to [/green]{dest_path}")

    @property
    def settings(self) -> dict:
        """Get project settings."""
        return self._settings

    @settings.setter
    def settings(self, value: dict) -> None:
        """Set project settings."""
        if "project" not in value:
            raise ValueError("`project` field does not exist")

        if "layout" not in value:
            raise ValueError("`layout` field does not exist")

        self.layout = value["layout"]

        if "opendataframework" not in value:
            raise ValueError("`opendataframework` field does not exist")
        if "data" not in value:
            raise ValueError("`data` field does not exist")
        if "platform" not in value:
            raise ValueError("`platform` field does not exist")
        # TODO: validate layer & component names
        self._settings = value

    def to_json(self, indent=JSON_INDENT) -> None:
        """Dump settings to json."""
        path = os.path.join(self.path, "settings.json")
        if os.path.exists(path):
            raise ValueError(f"{path} already exists")
        with open(path, "w") as file:
            json.dump(self.settings, file, indent=indent)
            rprint(f"{path} [green]created[/green]")

    def from_json(self) -> None:
        """Load settings from json."""
        path = os.path.join(self.path, "settings.json")
        if not os.path.exists(path):
            raise ValueError(f"{path} does not exists")  # TODO: "does not exist"
        with open(path, "r") as file:
            self.settings = json.load(file)
    
    def to_yaml(self) -> None:
        """Dump settings to yaml."""
        path = os.path.join(self.path, "settings.yaml")
        if os.path.exists(path):
            raise ValueError(f"{path} already exists")
        with open(path, "w") as file:
            settings = json.loads(json.dumps(self.settings))
            yaml.dump(settings, file, sort_keys=False)
            rprint(f"{path} [green]created[/green]")

    def from_yaml(self) -> None:
        """Load settings from yaml."""
        path = os.path.join(self.path, "settings.yaml")
        if not os.path.exists(path):
            raise ValueError(f"{path} does not exist")
        with open(path, "r") as file:
            self.settings = yaml.safe_load(file)
    
    def load(self) -> None:
        try:
            self.from_json()
            return
        except ValueError:
            pass
            
        try:
            self.from_yaml()
            return
        except ValueError :
            pass

        raise ValueError(f"{os.path.join(self.path)}: settings file does not exist")


    def mounts(self) -> None:
        """Configure mounts."""
        for component, settings in self.settings["platform"].items():
            if component not in MOUNTS:
                continue

            self._settings["platform"][component]["mounts"] = {}

            layer = settings["layer"]

            if layer is Layer.DEVCONTAINERS:
                workspace_mount = MOUNTS[component]["workspaceMount"].format(
                    project_name=self.name
                )
                self._settings["platform"][component]["mounts"]["workspaceMount"] = (
                    workspace_mount
                )

                workspace_folder = MOUNTS[component]["workspaceFolder"].format(
                    project_name=self.name
                )
                self._settings["platform"][component]["mounts"]["workspaceFolder"] = (
                    workspace_folder
                )

                mounts = [
                    mnt.format(project_name=self.name)
                    for mnt in MOUNTS[component]["mounts"]
                ]
                self._settings["platform"][component]["mounts"]["mounts"] = mounts

    def volumes(self) -> None:
        """Configure volumes."""
        for component in self.settings["platform"]:
            if component not in VOLUMES:
                continue
            self._settings["platform"][component]["volumes"] = VOLUMES[component].get(self.layout, {})

    def ports(self) -> None:
        """Configure ports."""
        for component, settings in self.settings["platform"].items():
            port = PORTS.get(component)

            layer = settings["layer"]
            if layer is Layer.API:
                if not self._api_ports:
                    name = component
                    if settings.get("storage"):
                        name = f'{layer}-{settings["storage"]}'
                    port = PORTS.get(name)
                else:
                    port = int(self._api_ports[-1])
                    port += 1
                port = str(port)
                self._api_ports.append(port)
            
            if not port:
                continue

            self._settings["platform"][component]["port"] = port
        
    
    def register(self, layer: str = None, component: str = None, entity: Entity = None) -> None:
        """Register component or entity at project level."""
        assert (layer and component) or entity, "Eather `layer` AND `component` OR entity should be set"

        if not (layer and component) and entity:
            if entity.plural_name in self.settings["data"]:
                raise ValueError(f"`{entity.plural_name}` already exists")
            self.settings["data"].update(entity.to_dict())

        if layer and layer not in COMPONENTS:
            raise ValueError(f"Layer `{layer}` not found")

        if layer and component:
            if component not in COMPONENTS[layer]:
                raise ValueError(f"Component `{component}` not found")
            if component in self.settings["platform"]:
                raise ValueError(f"Component `{component}` already exists")
            
            if entity and layer == Layer.API:
                self.settings["platform"][entity.plural_name] = {"layer": layer}
                storage = DEPENDENCIES.get(component, {}).get(Layer.STORAGE, [None])[0]
                if storage:
                    self.settings["platform"][entity.plural_name]["storage"] = storage
            else:
                self.settings["platform"][component] = {"layer": layer}
            
            if component in ENTIIES:
                name = ENTIIES[component]["name"]
                if ENTIIES[component]["type"] == "list":
                    if layer == Layer.API:
                        self.settings["platform"][entity.plural_name][name] = [entity.plural_name]
                    else:
                        self.settings["platform"][component][name] = [entity.plural_name]
            
            for layer, components in DEPENDENCIES.get(component, {}).items():
                for component in components:
                    if component in self.settings["platform"]:
                        if component in ENTIIES and ENTIIES[component]["type"] == "list":
                            self.settings["platform"][component][ENTIIES[component]["name"]].append(entity.plural_name)
                    else:
                        self.settings["platform"][component] = {"layer": layer}
                        if component in ENTIIES and ENTIIES[component]["type"] == "list":
                            self.settings["platform"][component][ENTIIES[component]["name"]] = [entity.plural_name]

    @property
    def layout(self):
        """Get project layout name."""
        return self._layout

    @layout.setter
    def layout(self, value: str):
        """Set project layout name."""
        value = value.strip().lower()
        if value not in LAYOUTS:
            raise ValueError(
                f"Invalid layout name `{value}`. Valid names are: {LAYOUTS}"
            )
        self._layout = value
        self._settings["layout"] = self._layout

    @property
    def profile(self):
        """Get project profile name."""
        return self._profile

    @profile.setter
    def profile(self, value: str):
        """Set project profile name."""
        value = value.strip().lower()
        if value not in PROFILES:
            raise ValueError(
                f"Invalid profile name `{value}`. Valid names are: {PROFILES}"
            )
        self._profile = value
        self._settings["profile"] = self._profile

    def add_layout(self):
        """Add project layout."""
        if self.layout == Layout.CUSTOM:
            return

        from_path = os.path.join(SRC_PATH, "layouts", self.layout)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path)

        shutil.copytree(
            from_path,
            to_path,
            ignore=shutil.ignore_patterns(*IGNORE_PATTERNS, *("data")),
            dirs_exist_ok=True,
        )

        shutil.copytree(
            os.path.join(from_path, "data"),
            os.path.join(to_path, "data"),
            ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            dirs_exist_ok=True,
        )

        data_path = os.path.join(to_path, "data")
        for file_name in os.listdir(data_path):
            if file_name.endswith(".csv"):
                source_path = os.path.join(data_path, file_name)
                dest_path = os.path.join(data_path, "raw", file_name)
                shutil.move(source_path, dest_path)
                rprint(f"{file_name}[green] moved to [/green]{dest_path}")

        rprint(f"{self.name}: {self.layout} layout[green] created[/green]")

    def add_docs(self):
        """Add project docs."""
        from_path = os.path.join(SRC_PATH, "docs")
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path, "docs")
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        shutil.copytree(
            from_path,
            to_path,
            ignore=shutil.ignore_patterns(
                *IGNORE_PATTERNS, *("mkdocs.yml", "requirements.txt")
            ),
        )

        if os.path.exists(os.path.join(self.path, "requirements.txt")):
            with open(os.path.join(from_path, "requirements.txt"), "r") as file:
                src_file_data = file.read()
            with open(os.path.join(self.path, "requirements.txt"), "a") as file:
                file.write(src_file_data)
        else:
            self.copy(from_path, self.path, "requirements.txt")

        self.copy(from_path, self.path, "mkdocs.yml")
        self.replace(
            os.path.join(self.path, "docs", "index.md"), PROJECT_NAME, self.name
        )
        self.replace(os.path.join(self.path, "mkdocs.yml"), PROJECT_NAME, self.name)

        rprint(f"{self.name}: docs[green] created[/green]")

    def add_hooks(self):
        """Add project pre-commit hooks."""
        from_path = os.path.join(SRC_PATH, "hooks")
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        if os.path.exists(os.path.join(self.path, ".pre-commit-config.yaml")):
            raise ValueError(
                f'{os.path.join(self.path, ".pre-commit-config.yaml")} already exists'
            )

        self.copy(from_path, self.path, ".pre-commit-config.yaml")

        if os.path.exists(os.path.join(self.path, "requirements.txt")):
            with open(os.path.join(from_path, "requirements.txt"), "r") as file:
                src_file_data = file.read()
            with open(os.path.join(self.path, "requirements.txt"), "a") as file:
                file.write(src_file_data)
        else:
            self.copy(from_path, self.path, "requirements.txt")

        rprint(f"{self.name}: .pre-commit-config.yaml[green] created[/green]")

    def add_workflows(self):
        """Add github workflows (github pages ci for docs)."""
        from_path = os.path.join(SRC_PATH, "github")
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path, ".github")
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        shutil.copytree(
            from_path,
            to_path,
            ignore=shutil.ignore_patterns(
                *IGNORE_PATTERNS,
            ),
        )

        rprint(f"{self.name}: github workflows[green] created[/green]")

    def add_tests(self):
        """Add project tests."""
        from_path = os.path.join(SRC_PATH, "tests")
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path, "tests")
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        shutil.copytree(
            from_path,
            to_path,
            ignore=shutil.ignore_patterns(*IGNORE_PATTERNS, *("requirements.txt",)),
        )

        if os.path.exists(os.path.join(self.path, "requirements.txt")):
            with open(os.path.join(from_path, "requirements.txt"), "r") as file:
                src_file_data = file.read()
            with open(os.path.join(self.path, "requirements.txt"), "a") as file:
                file.write(src_file_data)
        else:
            self.copy(from_path, self.path, "requirements.txt")

        rprint(f"{self.name}: tests[green] created[/green]")

    def add_server(self):
        """Add project server."""
        from_path = os.path.join(SRC_PATH, "server")
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path, "server")
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        shutil.copytree(
            from_path,
            to_path,
            ignore=shutil.ignore_patterns(
                *IGNORE_PATTERNS, *("requirements.txt",)
            ),
        )

        if os.path.exists(os.path.join(self.path, "requirements.txt")):
            with open(os.path.join(from_path, "requirements.txt"), "r") as file:
                src_file_data = file.read()
            with open(os.path.join(self.path, "requirements.txt"), "a") as file:
                file.write(src_file_data)
        else:
            self.copy(from_path, self.path, "requirements.txt")

        host = "http://localhost"
        target_path = os.path.join(to_path, "static", "index.html")

        Project.replace(target_path, PROJECT_NAME, self.settings["project"])

        with open(target_path, "r") as file:
            filedata = file.read()

        data = {}
        nav = ["<nav>"]
        content = ['<div class="main-content" id="mainContent">']
        section = '  <section id="{layer}" class="{section}">\n    <div class="grid" id="grid-{layer}"></div>\n  </section>'

        def html(data, layer, nav, content, host, port, plural_name=None):
            if not data.get(layer):
                data[layer] = {}
                if len(nav) == 1:
                    a = f'    <a href="#" class="active" data-section="{layer}">{layer.capitalize()}</a>'
                else:
                    a = f'    <a href="#" data-section="{layer}">{layer.capitalize()}</a>'
                nav.append(a)

                if len(content) == 1:
                    header = f'  <div class="header" id="sectionHeader" style="color: #00FA92;">{layer.capitalize()}</div>'
                    content.append(header)
                    content.append(section.format(layer=layer, section="section active"))
                else:
                    content.append(section.format(layer=layer, section="section"))
            
            if plural_name:
                data[layer].update({f"{plural_name}": {"url": f"{host}:{port}/"}})
            else:
                data[layer].update({component: {"url": f"{host}:{port}/"}})

        for component, settings in self._settings["platform"].items():
            layer = settings["layer"]
            port = settings.get("port")
            if not port:
                continue
            if layer == Layer.API:
                html(data, layer, nav, content, host, port, component)
            else:
                html(data, layer, nav, content, host, port)
        
        nav.append("  </nav>")
        content.append("</div>")
        
        filedata = filedata.replace("<nav></nav>", "\n".join(nav))
        filedata = filedata.replace('<div class="main-content" id="mainContent"></div>', "\n".join(content))
        filedata = filedata.replace("const components = {}", f"const components = {data}")

        with open(target_path, "w") as file:
            file.write(filedata)

        rprint(f"{self.name}: server[green] created[/green]")
    
    def init(self, extention=Settings.JSON):
        """Handler for `init` CLI command."""
        entities = []
        rprint()
        while True:
            user_input = (
                Prompt.ask(f"[#00FA92]- Layout ({self.layout})[/#00FA92]")
                .strip()
                .lower()
            )
            if not user_input:
                break
            try:
                self.layout = user_input
                break
            except ValueError as e:
                rprint(f"[bold red] {e} [/bold red]")
                continue
        data_path = os.path.join(self.path, "data")
        if not os.listdir(data_path):
            raise ValueError(f"{data_path} is empty, supported formats: {FILE_FORMATS}")
        for file_name in os.listdir(data_path):
            if file_name.endswith(".csv"):
                file_path = os.path.join(data_path, file_name)

                rprint(f"[#B36AE2]Entity: {file_name}[/#B36AE2]")
                name = file_name.split(".csv")[0]
                if name.endswith("s"):
                    name = name[:-1]
                while True:
                    user_input = (
                        Prompt.ask(f"[#00FA92]- Name[/#00FA92] ({name})")
                        .strip()
                        .lower()
                    )
                    if user_input:
                        name = user_input
                    try:
                        entity = Entity(name=name, path=file_path)
                        break
                    except ValueError as e:
                        rprint(f"[bold red] {e} [/bold red]")
                        continue

                if entity.name.endswith("s"):
                    plural_name = entity.name
                else:
                    plural_name = entity.name + "s"

                while True:
                    user_input = (
                        Prompt.ask(f"[#00FA92]- Plural[/#00FA92] ({plural_name})")
                        .strip()
                        .lower()
                    )
                    if user_input:
                        plural_name = user_input
                    try:
                        entity.plural_name = plural_name
                        break
                    except ValueError as e:
                        rprint(f"[bold red] {e} [/bold red]")
                        continue

                description = ""
                while True:
                    user_input = (
                        Prompt.ask("[#00FA92]- Description[/#00FA92]").strip().lower()
                    )
                    if user_input:
                        description = user_input
                    try:
                        entity.description = description
                        break
                    except ValueError as e:
                        rprint(f"[bold red] {e} [/bold red]")
                        continue

                entity.read()

                rprint()
                rprint(f"{json.dumps(entity.to_dict(), indent=JSON_INDENT)}")
                rprint()
                self.register(entity=entity)
                rprint(
                    "[#00FA92]Entity[/#00FA92]",
                    f"`[#B36AE2]{entity.name}[/#B36AE2]`",
                    "[#00FA92]created[/#00FA92]",
                )
                rprint()
                entities.append(entity)

        for layer, components in COMPONENTS.items():
            if not components:
                continue
            rprint()
            rprint(f"[#B36AE2]{layer}[/#B36AE2]")
            for component in components:
                if self.settings["platform"].get(component):
                    rprint(f"[bright_black]{component}: y[/bright_black]")
                    continue
                user_input = (
                    Prompt.ask(f"[#00FA92]{component}[/#00FA92]")
                    .strip()
                    .lower()
                )
                if user_input in {"y", "yes"}:
                    if component in ENTIIES:
                        for entity in entities:
                            user_input = (
                                Prompt.ask(f"[#00FA92]Add {entity.plural_name} to {component}?[/#00FA92]")
                                .strip()
                                .lower()
                            )
                            if user_input in {"y", "yes"}:
                                self.register(layer=layer, component=component, entity=entity)
                    else:
                        self.register(layer=layer, component=component)
            rprint()
        
        self.mounts()
        self.volumes()
        self.ports()
        
        if extention == Settings.JSON:
            self.to_json()
        else:
            self.to_yaml()
        rprint(f"[#00FA92]Project `[#B36AE2]{self.name}[/#B36AE2]` created[/#00FA92]")

        rprint(f"{json.dumps(self.settings, indent=JSON_INDENT)}")
        rprint()

    def create(
        self,
        docs: bool = True,
        hooks: bool = True,
        workflows: bool = False,
        tests: bool = True,
        server: bool = True,
    ):
        """Handler for `create` CLI command."""
        self.load()
        self.add_layout()
        if docs:
            self.add_docs()
        if hooks:
            self.add_hooks()
        if workflows:
            self.add_workflows()
        if tests:
            self.add_tests()
        if server:
            self.add_server()

        layers = [
            Analytics(project=self),
            # API(project=self),
            # Devcontainers(project=self),
            # Storage(project=self),
            # Utility(project=self),
        ]

        for layer in layers:
            layer()

        # self.collect()

    @staticmethod
    def replace(path: str, text: str, new_text: str):
        """Method to replace text in a file."""
        with open(path, "r") as file:
            filedata = file.read()

        filedata = filedata.replace(text, new_text)

        with open(path, "w") as file:
            file.write(filedata)

    @staticmethod
    def walk(path: str, file_names: list, ignore_dirs: list = None) -> tuple:
        """Walk over dirs based on path and collect file data based on file names."""
        from collections import defaultdict

        if ignore_dirs is None:
            ignore_dirs = []

        data = defaultdict(list)
        paths = []

        for dir_path, dirs, files in os.walk(path):
            for ignore_dir in ignore_dirs:
                if ignore_dir in dir_path:
                    continue
            if dir_path == path:
                continue
            for file_name in files:
                if file_name in file_names:
                    file_path = os.path.join(dir_path, file_name)

                    with open(file_path, "r") as file:
                        file_data = file.read()
                        data[file_name].append(file_data)
                        paths.append(file_path)

        return data, paths

    @staticmethod
    def copy(from_path: str, to_path: str, file_name: str, make_dirs: bool = False):
        """Copy file."""
        src_path = os.path.join(from_path, file_name)
        if not os.path.exists(src_path):
            raise ValueError(f"{src_path} not found")

        if make_dirs:
            os.makedirs(to_path, exist_ok=True)

        target_path = os.path.join(to_path, file_name)
        if os.path.exists(target_path):
            raise ValueError(f"{target_path} already exists")

        shutil.copyfile(src_path, target_path)

    @staticmethod
    def remove(paths: list) -> None:
        """Remove files/dirs."""
        for file_path in paths:
            os.remove(file_path)

    def collect(self):
        """Collect scripts."""
        from_path = SRC_PATH
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(self.path, PLATFORM_FOLDER)
        if not os.path.exists(to_path):
            raise ValueError(f"{to_path} does not exist")

        scripts = ["setup.sh", "requirements.txt"]

        for file_name in scripts:
            if file_name == "requirements.txt":
                if os.path.exists(os.path.join(self.path, file_name)):
                    with open(os.path.join(from_path, file_name), "r") as file:
                        src_file_data = file.read()
                    with open(os.path.join(self.path, file_name), "a") as file:
                        file.write(src_file_data)
                else:
                    self.copy(from_path, self.path, file_name)
            else:
                self.copy(from_path, to_path, file_name)

        self.copy(from_path, to_path, "docker-compose.yaml")
        self.copy(from_path, self.path, "expectations.py")
        self.copy(from_path, self.path, "README.md")

        self.replace(os.path.join(self.path, "README.md"), f"{PROJECT_NAME}", self.name)

        for layer in COMPONENTS:
            if layer is Layer.DEVCONTAINERS:
                continue

            target_path = os.path.join(to_path, layer)
            if not os.path.exists(target_path):
                continue

            src_path = os.path.join(from_path, layer)
            if not os.path.exists(src_path):
                raise ValueError(f"{src_path} does not exist")

            if layer is Layer.API:
                self.copy(os.path.join(from_path, Layer.API), self.path, "ingest.py")
            files_data, paths = self.walk(target_path, scripts)

            for file_name in scripts:
                lines = files_data[file_name] if paths else []

                file_path = f"{src_path}/{file_name}"

                if not os.path.exists(file_path):
                    continue

                with open(file_path, "r") as file:
                    src_file_data = file.read()

                if lines and layer == Layer.STORAGE and file_name == "setup.sh":
                    # put storage setup logic on top of setup.sh
                    with open(f"{to_path}/{file_name}", "r") as file:
                        current_file_data = file.readlines()
                        # keep shebang on top of the file
                        header, current_file_data = (
                            current_file_data[:3],
                            current_file_data[3:],
                        )
                        header = [line for line in header if line != "\n"]
                        header = "".join([*header])
                        current_file_data = "".join([*current_file_data])
                    with open(f"{to_path}/{file_name}", "w") as file:
                        file.write(
                            "\n".join(
                                [header, src_file_data, *lines, current_file_data]
                            )
                        )

                else:
                    path = self.path if file_name == "requirements.txt" else to_path
                    with open(f"{path}/{file_name}", "a") as file:
                        file.write(src_file_data)
                        file.write("\n".join(lines))

            if paths:
                self.remove(paths)

            file_name = "docker-compose.yaml"
            files_data, paths = self.walk(target_path, [file_name])
            if paths:
                contents = files_data[file_name]
                file_path = f"{to_path}/{file_name}"

                # exclude docker compose header
                for content in contents:
                    lines = content.split("\n")[2:]
                    lines = ["\n".join(lines)]

                    with open(file_path, "a") as file:
                        file.write("\n".join(lines))

                self.remove(paths)

        with open(os.path.join(to_path, "docker-compose.yaml"), "a") as file:
            file.write("networks:\n")
            file.write(f"  {self.name}_default:\n")
            file.write(f"    name: {self.name}_default\n")


class Analytics:
    """Analytics layer."""

    def __init__(self, project: Project):
        """Create Analytics layer instance."""
        self.project = project

    def superset(self):
        """Configure Analytics `SUPERSET` component."""
        settings = self.project.settings.get("platform", {}).get(Component.SUPERSET)
        if not settings:
            return

        from_path = os.path.join(SRC_PATH, Layer.ANALYTICS, Component.SUPERSET)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.ANALYTICS, Component.SUPERSET
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})
        storages = {storage: config for storage, config in self.project.settings["platform"].items() if config["layer"] == Layer.STORAGE}
        port = settings["port"]

        to_setup = os.path.join(to_path, "setup.sh")

        for plural_name in entities:
            if plural_name not in settings["datasets"]:
                continue

            if not os.path.exists(to_path):
                shutil.copytree(
                    from_path,
                    to_path,
                    ignore=shutil.ignore_patterns(*IGNORE_PATTERNS, *("database",)),
                )

            storage = None

            for name, config in storages.items():
                for table in config["tables"]:
                    if table == plural_name:
                        storage = name
            
            if not storage:
                continue

            from_setup = os.path.join(
                from_path, "database", f"{storage}", "setup.sh"
            )

            if not os.path.exists(from_setup):
                continue

            with open(f"{from_setup}", "r") as file:
                content = file.read()

            with open(f"{to_setup}", "a") as file:
                file.write("&& " + content)

            from_create = os.path.join(
                from_path, "database", f"{storage}", "dataset.sh"
            )

            with open(f"{from_create}", "r") as file:
                content = file.read()
                content = content.replace("table-name", f"{plural_name}")

            with open(f"{to_setup}", "a") as file:
                file.write("&& " + content)

            if PORTS.get(storage) and storages[storage].get("port"):
                Project.replace(to_setup, PORTS.get(storage), storages[storage].get("port"))

            with open(f"{to_setup}", "a") as file:
                file.write("\n")

        if not os.path.exists(to_path):
            return

        Project.replace(
            os.path.join(to_path, ".env"),
            'SUPERSET_SECRET_KEY=""',
            f'SUPERSET_SECRET_KEY="{uuid.uuid4()}"',
        )

        Project.replace(
            os.path.join(to_path, "setup.sh"), f"{PROJECT_NAME}", self.project.name
        )

        Project.replace(to_setup, PORTS[Component.SUPERSET], port)

        hostname = self.project.settings["project"].replace("_", "-")

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"hostname: {PROJECT_NAME}-{Component.SUPERSET}",
            f"hostname: {hostname}-{Component.SUPERSET}",
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PORTS[Component.SUPERSET]}:",
            f"{port}:",
        )

        rprint(f"{to_path}[green] created[/green]")

    def __call__(self):
        """Call layer."""
        self.superset()


class API:
    """API layer."""

    def __init__(self, project: Project):
        """Create API layer instance."""
        self.project = project

    def api_druid(self):
        """Configure API `API_DRUID` component."""
        from_path = os.path.join(SRC_PATH, Layer.API, Component.API_DRUID)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.API, {})
            if Component.API_DRUID not in components:
                continue

            to_path = os.path.join(
                self.project.path,
                PLATFORM_FOLDER,
                Layer.API,
                Component.API_DRUID,
                plural_name,
            )
            if os.path.exists(to_path):
                raise ValueError(f"{to_path} already exists")

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(
                    *IGNORE_PATTERNS,
                ),
            )

            hostname = self.project.settings["project"].replace("_", "-")

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"hostname: {PROJECT_NAME}-{Component.API_DRUID}",
                f"hostname: {hostname}-{Component.API_DRUID}",
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PROJECT_NAME}",
                self.project.settings["project"],
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"), "entity", plural_name
            )

            port = components[Component.API_DRUID]["port"]
            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PORTS[Component.API_DRUID]}:",
                f"{port}:",
            )

            # model
            model_path = os.path.join(to_path, "app", "models.py")
            new_text = "# fields"

            for field_name, value in settings["fields"].items():
                field_type, _ = value["type"], value["alias"]
                if field_name in Field.RESERVED_FIELDS:
                    raise ValueError(
                        f"Field names `{self.RESERVED_FIELDS}` are reserved"
                    )
                if "datetime" in field_type:
                    # TODO: format validator
                    field_type = "datetime"

                new_text += f"\n    {field_name}: {field_type}"

            Project.replace(model_path, "# extra fields", new_text)
            Project.replace(model_path, "entities", plural_name)
            Project.replace(model_path, "Entity", settings["name"].capitalize())

            # crud
            crud_path = os.path.join(to_path, "app", "crud.py")
            Project.replace(crud_path, "entity", settings["name"])
            Project.replace(crud_path, "entities", plural_name)
            Project.replace(crud_path, "Entity", settings["name"].capitalize())

            # router
            router_path = os.path.join(to_path, "app", "router.py")
            Project.replace(router_path, "entity", settings["name"])
            Project.replace(router_path, "entities", plural_name)
            Project.replace(router_path, "Entity", settings["name"].capitalize())

            # env
            port = self.project.settings["ports"].get(Component.DRUID)
            env_path = os.path.join(to_path, ".env")
            Project.replace(
                env_path, f"{PROJECT_NAME}", self.project.settings["project"]
            )
            Project.replace(env_path, "description", settings["description"])
            if port:
                Project.replace(env_path, PORTS[Component.POSTGRES], port)

            # main
            main_path = os.path.join(to_path, "app", "main.py")
            Project.replace(main_path, "entity", settings["name"])

            rprint(f"{to_path}[green] created[/green]")

    def api_json_kafka(self):
        """Configure API `API_JSON_KAFKA` component."""
        from_path = os.path.join(SRC_PATH, Layer.API, Component.API_JSON_KAFKA)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.API, {})
            if Component.API_JSON_KAFKA not in components:
                continue

            to_path = os.path.join(
                self.project.path,
                PLATFORM_FOLDER,
                Layer.API,
                Component.API_JSON_KAFKA,
                plural_name,
            )
            if os.path.exists(to_path):
                raise ValueError(f"{to_path} already exists")

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(
                    *IGNORE_PATTERNS,
                ),
            )

            hostname = self.project.settings["project"].replace("_", "-")

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"hostname: {PROJECT_NAME}-{Component.API_JSON_KAFKA}",
                f"hostname: {hostname}-{Component.API_JSON_KAFKA}",
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PROJECT_NAME}",
                self.project.settings["project"],
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"), "entity", plural_name
            )

            port = components[Component.API_JSON_KAFKA]["port"]
            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PORTS[Component.API_JSON_KAFKA]}:",
                f"{port}:",
            )

            # model
            model_path = os.path.join(to_path, "app", "models.py")
            new_text = "# fields"

            for field_name, value in settings["fields"].items():
                field_type, _ = value["type"], value["alias"]
                if field_name in Field.RESERVED_FIELDS:
                    raise ValueError(
                        f"Field names `{self.RESERVED_FIELDS}` are reserved"
                    )
                if "datetime" in field_type:
                    # TODO: format validator
                    field_type = "datetime"

                new_text += f"\n    {field_name}: {field_type}"

            Project.replace(model_path, "# extra fields", new_text)
            Project.replace(model_path, "entities", plural_name)
            Project.replace(model_path, "Entity", settings["name"].capitalize())

            # crud
            crud_path = os.path.join(to_path, "app", "crud.py")
            Project.replace(crud_path, "entity", settings["name"])
            Project.replace(crud_path, "entities", plural_name)
            Project.replace(crud_path, "Entity", settings["name"].capitalize())

            # router
            router_path = os.path.join(to_path, "app", "router.py")
            Project.replace(router_path, "entity", settings["name"])
            Project.replace(router_path, "entities", plural_name)
            Project.replace(router_path, "Entity", settings["name"].capitalize())

            # env
            port = self.project.settings["ports"][Component.KAFKA]
            env_path = os.path.join(to_path, ".env")
            Project.replace(
                env_path, f"{PROJECT_NAME}", self.project.settings["project"]
            )
            Project.replace(env_path, "description", settings["description"])
            Project.replace(env_path, PORTS[Component.KAFKA], port)
            Project.replace(env_path, "Entities", plural_name.capitalize())
            Project.replace(env_path, "entities", plural_name)

            # main
            main_path = os.path.join(to_path, "app", "main.py")
            Project.replace(main_path, "entity", settings["name"])

            rprint(f"{to_path}[green] created[/green]")

    def api_postgres(self):
        """Configure API `API_POSTGRES` component."""
        from_path = os.path.join(SRC_PATH, Layer.API, Component.API_POSTGRES)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.API, {})
            if Component.API_POSTGRES not in components:
                continue

            to_path = os.path.join(
                self.project.path,
                PLATFORM_FOLDER,
                Layer.API,
                Component.API_POSTGRES,
                plural_name,
            )
            if os.path.exists(to_path):
                raise ValueError(f"{to_path} already exists")

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(
                    *IGNORE_PATTERNS,
                ),
            )

            hostname = self.project.settings["project"].replace("_", "-")

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"hostname: {PROJECT_NAME}-{Component.API_POSTGRES}",
                f"hostname: {hostname}-{Component.API_POSTGRES}",
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PROJECT_NAME}",
                self.project.settings["project"],
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"), "entity", plural_name
            )

            port = components[Component.API_POSTGRES]["port"]
            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PORTS[Component.API_POSTGRES]}:",
                f"{port}:",
            )

            # model
            model_path = os.path.join(to_path, "app", "models.py")
            new_text = "# fields"

            for field_name, value in settings["fields"].items():
                field_type, _ = value["type"], value["alias"]
                if field_name in Field.RESERVED_FIELDS:
                    raise ValueError(
                        f"Field names `{self.RESERVED_FIELDS}` are reserved"
                    )
                if "datetime" in field_type:
                    # TODO: format validator
                    field_type = "datetime"

                new_text += f"\n    {field_name}: {field_type}"

            Project.replace(model_path, "# extra fields", new_text)
            Project.replace(model_path, "entities", plural_name)
            Project.replace(model_path, "Entity", settings["name"].capitalize())

            # crud
            crud_path = os.path.join(to_path, "app", "crud.py")
            Project.replace(crud_path, "entity", settings["name"])
            Project.replace(crud_path, "entities", plural_name)
            Project.replace(crud_path, "Entity", settings["name"].capitalize())

            # router
            router_path = os.path.join(to_path, "app", "router.py")
            Project.replace(router_path, "entity", settings["name"])
            Project.replace(router_path, "entities", plural_name)
            Project.replace(router_path, "Entity", settings["name"].capitalize())

            # env
            port = self.project.settings["ports"][Component.POSTGRES]
            env_path = os.path.join(to_path, ".env")
            Project.replace(
                env_path, f"{PROJECT_NAME}", self.project.settings["project"]
            )
            Project.replace(env_path, "description", settings["description"])
            Project.replace(env_path, PORTS[Component.POSTGRES], port)

            # main
            main_path = os.path.join(to_path, "app", "main.py")
            Project.replace(main_path, "entity", settings["name"])

            rprint(f"{to_path}[green] created[/green]")

    def inference(self):
        """Configure API `INFERENCE` component."""
        from_path = os.path.join(SRC_PATH, Layer.API, Component.INFERENCE)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.API, {})
            if Component.INFERENCE not in components:
                continue

            to_path = os.path.join(
                self.project.path,
                PLATFORM_FOLDER,
                Layer.API,
                Component.INFERENCE,
                plural_name,
            )
            if os.path.exists(to_path):
                raise ValueError(f"{to_path} already exists")

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(
                    *IGNORE_PATTERNS,
                ),
            )

            model_path = os.path.join(self.project.path, "models", plural_name)
            if not os.path.exists(os.path.join(model_path, "model.json")):
                raise ValueError(f"{model_path}/model.json does not exist")

            app_models_path = os.path.join(to_path, "app", ".models", str(uuid.uuid4()))

            Project.copy(model_path, app_models_path, "model.json", make_dirs=True)

            for field_name, value in settings["fields"].items():
                _, field_alias = value["type"], value["alias"]

                Project.replace(
                    os.path.join(app_models_path, "model.json"),
                    field_alias,
                    field_name,
                )

            if os.path.exists(os.path.join(model_path, "model.pkl")):
                Project.copy(model_path, app_models_path, "model.pkl")

            if os.path.exists(os.path.join(model_path, "requirements.txt")):
                with open(os.path.join(model_path, "requirements.txt"), "r") as file:
                    filedata = file.read()
                    new_filedata = []
                    for line in filedata.split("\n"):
                        if not line:
                            continue
                        packet, version = line.split("==")
                        new_line = f'{packet} = "{version}"'
                        new_filedata.append(new_line)
                    filedata = "\n".join(new_filedata)

                    Project.replace(
                        os.path.join(to_path, "pyproject.toml"),
                        "# dependencies",
                        filedata,
                    )

            hostname = self.project.settings["project"].replace("_", "-")

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"hostname: {PROJECT_NAME}-{Component.INFERENCE}",
                f"hostname: {hostname}-{Component.INFERENCE}",
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PROJECT_NAME}",
                self.project.settings["project"],
            )

            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"), "entity", plural_name
            )

            port = components[Component.INFERENCE]["port"]
            Project.replace(
                os.path.join(to_path, "docker-compose.yaml"),
                f"{PORTS[Component.INFERENCE]}:",
                f"{port}:",
            )

            # model
            model_path = os.path.join(to_path, "app", "models.py")

            with open(os.path.join(app_models_path, "model.json"), "r") as file:
                inference_config = json.load(file)
                parameters = inference_config.get("parameters")
                fit = inference_config.get("fit")
                predict = inference_config.get("predict")
                prediction = inference_config.get("prediction")
                assert parameters and isinstance(parameters, dict)
                assert fit and isinstance(fit, dict)
                assert predict and isinstance(predict, dict)
                assert prediction

                new_text = "# fields"

                for key, value in parameters.items():
                    if isinstance(value, dict):
                        new_text += f"\n    {key}: dict"
                    elif isinstance(value, list):
                        new_text += f"\n    {key}: list"
                    elif isinstance(value, int):
                        new_text += f"\n    {key}: int"
                    elif isinstance(value, float):
                        new_text += f"\n    {key}: float"
                    elif isinstance(value, str):
                        new_text += f"\n    {key}: str"

                Project.replace(model_path, "# parameters fields", new_text)

                new_text = "# fields"

                for key, records in fit.items():
                    assert isinstance(records, list)
                    assert all(isinstance(record, dict) for record in records)
                    new_text += f"\n    {key}: list[dict]"

                Project.replace(model_path, "# fit fields", new_text)

                new_text = "# fields"

                for key, records in predict.items():
                    assert isinstance(records, list)
                    assert all(isinstance(record, dict) for record in records)
                    new_text += f"\n    {key}: list[dict]"

                Project.replace(model_path, "# predict fields", new_text)

                new_text = "# fields"

                if isinstance(prediction, dict):
                    new_text += "\n    value: dict"
                elif isinstance(prediction, list):
                    new_text += "\n    value: list"
                elif isinstance(prediction, int):
                    new_text += "\n    value: int"
                elif isinstance(prediction, float):
                    new_text += "\n    value: float"
                elif isinstance(prediction, str):
                    new_text += "\n    value: str"

                Project.replace(model_path, "# prediction fields", new_text)

            # crud
            # crud_path = os.path.join(to_path, "app", "crud.py")
            # Project.replace(crud_path, "entity", settings["name"])
            # Project.replace(crud_path, "entities", plural_name)
            # Project.replace(crud_path, "Entity", settings["name"].capitalize())

            # inference
            inference_path = os.path.join(to_path, "app", "inference.py")
            Project.replace(
                inference_path,
                "PACKAGE_NAME = None",
                f'PACKAGE_NAME = "{inference_config["package"]}"',
            )
            Project.replace(
                inference_path,
                "MODEL_NAME = None",
                f'MODEL_NAME = "{inference_config["model"]}"',
            )

            # router
            router_path = os.path.join(to_path, "app", "router.py")
            Project.replace(router_path, "entity", settings["name"])
            Project.replace(router_path, "entities", plural_name)
            Project.replace(router_path, "Entity", settings["name"].capitalize())

            # env
            env_path = os.path.join(to_path, ".env")
            Project.replace(
                env_path, f"{PROJECT_NAME}", self.project.settings["project"]
            )
            Project.replace(env_path, "description", settings["description"])

            # main
            main_path = os.path.join(to_path, "app", "main.py")
            Project.replace(main_path, "entity", settings["name"])

            rprint(f"{to_path}[green] created[/green]")

    def __call__(self):
        """Call layer."""
        self.api_druid()
        self.api_json_kafka()
        self.api_postgres()
        self.inference()


class Devcontainers:
    """Devcontainers layer."""

    def __init__(self, project: Project):
        """Create Devcontainers layer instance."""
        self.project = project

    def go(self):
        """Configure Devcontainers `GO` component."""
        from_path = os.path.join(SRC_PATH, Layer.DEVCONTAINERS, Component.GO)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.DEVCONTAINERS, Component.GO
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.DEVCONTAINERS, {})
            if Component.GO not in components:
                continue

            if os.path.exists(to_path):
                break

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

            mounts = self.project.settings["mounts"].get(Component.GO)

            if not mounts:
                break

            config_path = os.path.join(to_path, ".devcontainer", "devcontainer.json")
            if not os.path.exists(os.path.join(config_path)):
                raise ValueError(f"{config_path} does not exist")

            with open(config_path, "r") as file:
                config = json.load(file)
                config["name"] = self.project.settings["project"]
                config["workspaceMount"] = mounts.get("workspaceMount", "")
                config["workspaceFolder"] = mounts.get("workspaceFolder", "")
                config["mounts"] = mounts.get("mounts", [])

            with open(config_path, "w") as file:
                json.dump(config, file, indent=JSON_INDENT)

            rprint(f"{to_path}[green] created[/green]")
    

    def python(self):
        """Configure Devcontainers `PYTHON` component."""
        from_path = os.path.join(SRC_PATH, Layer.DEVCONTAINERS, Component.PYTHON)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.DEVCONTAINERS, Component.PYTHON
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.DEVCONTAINERS, {})
            if Component.PYTHON not in components:
                continue

            if os.path.exists(to_path):
                break

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

            mounts = self.project.settings["mounts"].get(Component.PYTHON)

            if not mounts:
                break

            config_path = os.path.join(to_path, ".devcontainer", "devcontainer.json")
            if not os.path.exists(os.path.join(config_path)):
                raise ValueError(f"{config_path} does not exist")

            with open(config_path, "r") as file:
                config = json.load(file)
                config["name"] = self.project.settings["project"]
                config["workspaceMount"] = mounts.get("workspaceMount", "")
                config["workspaceFolder"] = mounts.get("workspaceFolder", "")
                config["mounts"] = mounts.get("mounts", [])

            with open(config_path, "w") as file:
                json.dump(config, file, indent=JSON_INDENT)

            rprint(f"{to_path}[green] created[/green]")

    def r(self):
        """Configure Devcontainers `R` component."""
        from_path = os.path.join(SRC_PATH, Layer.DEVCONTAINERS, Component.R)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.DEVCONTAINERS, Component.R
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.DEVCONTAINERS, {})
            if Component.R not in components:
                continue

            if os.path.exists(to_path):
                break

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

            mounts = self.project.settings["mounts"].get(Component.R)

            if not mounts:
                break

            config_path = os.path.join(to_path, ".devcontainer", "devcontainer.json")
            if not os.path.exists(os.path.join(config_path)):
                raise ValueError(f"{config_path} does not exist")

            with open(config_path, "r") as file:
                config = json.load(file)
                config["name"] = self.project.settings["project"]
                config["workspaceMount"] = mounts.get("workspaceMount", "")
                config["workspaceFolder"] = mounts.get("workspaceFolder", "")
                config["mounts"] = mounts.get("mounts", [])

            with open(config_path, "w") as file:
                json.dump(config, file, indent=JSON_INDENT)

            rprint(f"{to_path}[green] created[/green]")

    def __call__(self):
        """Call layer."""
        self.go()
        self.python()
        self.r()


class Storage:
    """Storage layer."""

    def __init__(self, project: Project):
        """Create Storage layer instance."""
        self.project = project

    def kafka(self):
        """Configure Storage `KAFKA` component."""
        from_path = os.path.join(SRC_PATH, Layer.STORAGE, Component.KAFKA)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.STORAGE, Component.KAFKA
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})
        ports = self.project.settings.get("ports", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.STORAGE, {})
            if Component.KAFKA not in components:
                continue

            if os.path.exists(to_path):
                break

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

        if not os.path.exists(to_path):
            return

        hostname = self.project.settings["project"].replace("_", "-")

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PROJECT_NAME}-{Component.KAFKA}",
            f"{hostname}-{Component.KAFKA}",
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        with open(os.path.join(to_path, "setup.sh"), "r") as file:
            setup_script = file.read()

        with open(os.path.join(to_path, "setup.sh"), "w") as file:
            lines = []
            for plural_name, settings in entities.items():
                components = settings["layers"].get(Layer.STORAGE, {})
                if Component.KAFKA not in components:
                    continue
                line = setup_script.split("\n")[1].replace("entities", plural_name)
                lines.append(line)
            file.write("\n".join(lines))
            file.write("\n")

        Project.replace(
            os.path.join(to_path, "setup.sh"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PORTS[Component.KAFKA]}:",
            f"{ports[Component.KAFKA]}:",
        )

        rprint(f"{to_path}[green] created[/green]")

    def postgres(self):
        """Configure Storage `POSTGRES` component."""
        from_path = os.path.join(SRC_PATH, Layer.STORAGE, Component.POSTGRES)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.STORAGE, Component.POSTGRES
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})
        ports = self.project.settings.get("ports", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.STORAGE, {})
            if Component.POSTGRES not in components:
                continue

            if os.path.exists(to_path):
                break

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

        if not os.path.exists(to_path):
            return

        hostname = self.project.settings["project"].replace("_", "-")

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"hostname: {PROJECT_NAME}-{Component.POSTGRES}",
            f"hostname: {hostname}-{Component.POSTGRES}",
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        Project.replace(
            os.path.join(to_path, "setup.sh"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PORTS[Component.POSTGRES]}:",
            f"{ports[Component.POSTGRES]}:",
        )

        rprint(f"{to_path}[green] created[/green]")

    def __call__(self):
        """Call layer."""
        self.kafka()
        self.postgres()


class Utility:
    """Utility layer."""

    def __init__(self, project: Project):
        """Create Utility layer instance."""
        self.project = project
    
    def texlive(self):
        """Configure Analytics `TEXLIVE` component."""
        from_path = os.path.join(SRC_PATH, Layer.UTILITY, Component.TEXLIVE)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.UTILITY, Component.TEXLIVE
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("data", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.UTILITY, {})
            if Component.TEXLIVE not in components:
                continue

            if not os.path.exists(to_path):
                shutil.copytree(
                    from_path,
                    to_path,
                    ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
                )

        if not os.path.exists(to_path):
            return

        volumes = self.project.settings["volumes"].get(Component.TEXLIVE)

        if volumes:
            with open(os.path.join(to_path, "docker-compose.yaml"), "a") as file:
                lines = [" " * 4 + "volumes:"]
                for key, value in volumes.items():
                    lines.append(" " * 6 + "- " + f"{key}:{value}")
                file.write("\n".join(lines))
                file.write("\n")

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PROJECT_NAME}",
            self.project.settings["project"],
        )

        rprint(f"{to_path}[green] created[/green]")

    def __call__(self):
        """Call layer."""
        self.texlive()


class Research:
    """Reasearch Profile."""

    def __init__(self, project: Project):
        """Reasearch Profile instance."""
        self.project = project

    def __call__(self):
        """Call Profile."""
        self.project.layout = Layout.RESEARCH
        self.project.profile = Profile.RESEARCH
        data_path = os.path.join(self.project.path, "data")
        for file_name in os.listdir(data_path):
            if file_name.endswith(".csv"):
                file_path = os.path.join(data_path, file_name)
                name = file_name.split(".csv")[0]
                if name.endswith("s"):
                    name = name[:-1]

                entity = Entity(name=name, path=file_path)
                entity.plural_name = entity.name + "s"
                entity.description = f"{entity.plural_name} {Profile.RESEARCH}"
                entity.read()
                self.project.register(layer=Layer.DEVCONTAINERS, component=Component.R)
                self.project.register(layer=Layer.UTILITY, component=Component.TEXLIVE)

                self.project.register(entity)
        self.project.to_json()


# CLI

app = typer.Typer()


@app.command()
def init(
    project: str,
    path: str = "",
    data: str = "",
    profile: str = Profile.CUSTOM,
    extention: str = Settings.JSON
):
    """Initialize PROJECT settings.json, optionally with a --path."""
    try:
        project = Project(name=project, path=path, data=data)
        profile = profile.strip().lower()
        if profile == Profile.CUSTOM:
            project.init(extention=extention)
        elif profile == Profile.RESEARCH:
            Research(project)()
        else:
            raise ValueError(f"Invalid Profile. Supported profiles are: {PROFILES}")
    except Exception:
        rprint(f"[bold red]{traceback.format_exc()}[/bold red]")


@app.command()
def create(
    project: str,
    path: str = "",
    docs: bool = True,
    hooks: bool = True,
    workflows: bool = False,
    tests: bool = True,
    server: bool = True,
):
    """Create PROJECT structure based on settings.json, optionally with a --path."""
    try:
        project = Project(name=project, path=path)
        project.create(docs=docs, hooks=hooks, workflows=workflows, tests=tests, server=server)
    except Exception:
        rprint(f"[bold red] {traceback.format_exc()} [/bold red]")


@app.command()
def install(project: str = "", path: str = ""):
    """Install dependencies into .venv from requirements.txt under cwd/path."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project)
        venv_path = os.path.join(path, ".venv")
        if os.path.exists(venv_path):
            raise ValueError(f"{venv_path} already exists")

        requirements_path = os.path.join(path, "requirements.txt")
        if not os.path.exists(requirements_path):
            raise ValueError(f"{requirements_path} not exists")

        venv.create(venv_path, with_pip=True)
        subprocess.run(["bin/pip", "install", "-r", requirements_path], cwd=venv_path)
    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def build(project: str = "", path: str = ""):
    """Run `docker compose --profile {layer} build`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project, "platform")

        compose_path = os.path.join(path, "docker-compose.yaml")
        if not os.path.exists(compose_path):
            raise ValueError(f"{compose_path} not exists")

        for layer in COMPONENTS:
            subprocess.run(
                ["docker", "compose", "--profile", f"{layer}", "build"], cwd=path
            )

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def start(project: str = "", path: str = ""):
    """Run `docker compose --profile {layer} up -d`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project, "platform")

        compose_path = os.path.join(path, "docker-compose.yaml")
        if not os.path.exists(compose_path):
            raise ValueError(f"{compose_path} not exists")

        for layer in COMPONENTS:
            subprocess.run(
                ["docker", "compose", "--profile", f"{layer}", "up", "-d"], cwd=path
            )

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def stop(project: str = "", path: str = ""):
    """Run `docker compose --profile {layer} stop`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project, "platform")

        compose_path = os.path.join(path, "docker-compose.yaml")
        if not os.path.exists(compose_path):
            raise ValueError(f"{compose_path} not exists")

        for layer in COMPONENTS:
            subprocess.run(
                ["docker", "compose", "--profile", f"{layer}", "stop"], cwd=path
            )

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def status(project: str = "", path: str = ""):
    """Run `docker compose ps`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project, "platform")

        compose_path = os.path.join(path, "docker-compose.yaml")
        if not os.path.exists(compose_path):
            raise ValueError(f"{compose_path} not exists")

        subprocess.run(["docker", "compose", "ps", "--all"], cwd=path)

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def setup(project: str = "", path: str = ""):
    """Run `platform/setup.sh`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exists")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project, "platform")

        setup_path = os.path.join(path, "setup.sh")
        if not os.path.exists(setup_path):
            raise ValueError(f"{setup_path} not exists")

        os.chmod(setup_path, os.stat(setup_path).st_mode | stat.S_IEXEC)
        subprocess.run(["./setup.sh"], cwd=path)

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def check(project: str = "", path: str = ""):
    """Run `pre-commit run --all-files`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exist")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project)
        venv_path = os.path.join(path, ".venv")
        if not os.path.exists(venv_path):
            raise ValueError(f"{venv_path} does not exist")

        pre_commit_path = os.path.join(path, ".pre-commit-config.yaml")
        if not os.path.exists(pre_commit_path):
            raise ValueError(f"{pre_commit_path} does not exist")

        subprocess.run([".venv/bin/pre-commit", "run", "--all-files"], cwd=path)
    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def docs(project: str = "", path: str = ""):
    """Run `mkdocs serve`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exist")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project)
        venv_path = os.path.join(path, ".venv")
        if not os.path.exists(venv_path):
            raise ValueError(f"{venv_path} does not exist")

        docs_path = os.path.join(path, "mkdocs.yml")
        if not os.path.exists(docs_path):
            raise ValueError(f"{docs_path} does not exist")

        subprocess.run([".venv/bin/mkdocs", "serve"], cwd=path)
    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def test(project: str = "", path: str = "", cov: str = ""):
    """Run `pytest --cov={cov} tests`."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exist")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project)
        venv_path = os.path.join(path, ".venv")
        if not os.path.exists(venv_path):
            raise ValueError(f"{venv_path} does not exist")

        test_path = os.path.join(path, "tests")
        if not os.path.exists(test_path):
            raise ValueError(f"{test_path} does not exist")

        if cov:
            cov_path = os.path.join(path, cov)
            if not os.path.exists(cov_path):
                raise ValueError(f"{cov_path} does not exist")

            subprocess.run([".venv/bin/pytest", f"--cov={cov}", "tests"], cwd=path)
        else:
            subprocess.run([".venv/bin/pytest", "tests"], cwd=path)
    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")


@app.command()
def server(project: str = "", path: str = "", host: str = "127.0.0.1", port: str = "8080", reload: bool = False):
    """Run `uvicorn server.main:app` inside project."""
    try:
        if path and not os.path.exists(path):
            raise ValueError(f"{path} does not exist")
        elif not path:
            path = os.getcwd()
        path = os.path.join(path, project)
        venv_path = os.path.join(path, ".venv")
        if not os.path.exists(venv_path):
            raise ValueError(f"{venv_path} does not exist")

        main_path = os.path.join(path, "server", "main.py")
        if not os.path.exists(main_path):
            raise ValueError(f"{main_path} does not exist")
        
        params = [
            ".venv/bin/uvicorn",
            "server.main:app",
            "--host", f"{host}",
            "--port", f"{port}"
        ]
        if reload:
            params.append("--reload")
        
        subprocess.run(params, cwd=path)

    except Exception as e:
        rprint(f"[bold red] {e} [/bold red]")

@app.command()
def chat():
    """Project configuration based on prompt.

    Example:
    Input:
    "I have a csv file. Prepare environment for storage and analytics,
    so I can upload my files, transform the data using SQL
    and visualize results on a dashboard."

    Output:
    analytics
    - superset
    storage
    - postgres
    """
    import difflib
    from collections import Counter

    KEYWORDS = {
        # ANALYTICS
        Component.SUPERSET: {
            "exploration",
            "visualization",
            "business",
            "intelligence",
            "bi",
            "chart",
            "sql",
            "analytics",
            "query",
            "file",
            "upload",
            "csv",
            "dashboard",
            "transform",
            "bar",
            "geospatial",
        },
        # API
        Component.API_POSTGRES: {
            "api",
            "serve",
            "endpoint",
            "url",
            "postgres",
            "postgresql",
            "postgre",
        },
        Component.INFERENCE: {"inference", "api", "model", "ml", "predict", "endpoint"},
        # DEVCONTAINERS
        Component.GO: {
            "devcontainer",
            "golang",
            "env",
            "isolated",
            "containerized",
            "go",
            "lang",
        },
        Component.PYTHON: {
            "devcontainer",
            "python",
            "env",
            "isolated",
            "containerized",
            "py",
            "lang",
        },
        Component.R: {
            "devcontainer",
            "r",
            "env",
            "isolated",
            "containerized",
            "rlang",
            "lang",
        },
        # STORAGE
        Component.POSTGRES: {
            "structured",
            "sql",
            "relational",
            "transaction",
            "csv",
            "storage",
            "db",
            "database",
            "insert",
            "postgresql",
            "postgre",
            "postgres",
        },
        # UTILITY
        Component.TEXLIVE: {
            "typesetting",
            "TeX",
            "mathematical",
            "formulae",
            "texlive",
        },
    }

    THRESHOLD = 3

    try:
        prompt = Prompt.ask("[#00FA92]Prompt[/#00FA92]").strip().lower().split()
        rprint()

        counters = {}
        for layer, components in COMPONENTS.items():
            counters[layer] = Counter()
            for component in components:
                keywords = KEYWORDS.get(component, {})
                for keyword in keywords:
                    matches = difflib.get_close_matches(keyword, prompt)
                    if matches:
                        counters[layer].update({component: 1})

        is_match = False

        for layer, counter in counters.items():
            components = []
            for component, score in counter.items():
                if score >= THRESHOLD:
                    components.append(component)
            if components:
                is_match = True
                rprint(f"[#B36AE2]{layer}[/#B36AE2]")
                for component in components:
                    rprint(f"[#00FA92][blue]\[x] [/blue]{component}[/#00FA92]")

        if not is_match:
            rprint("[yellow]No match.[/yellow]")

    except Exception:
        rprint(f"[bold red] {traceback.format_exc()} [/bold red]")


def main():
    """Main function which starts the app."""
    rprint(colorized_logo())
    app()


if __name__ == "__main__":
    main()
