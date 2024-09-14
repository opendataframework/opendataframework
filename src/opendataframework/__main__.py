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
    API_POSTGRES: str = "api-postgres"

    # DEVCONTAINERS
    PYTHON: str = "python"
    R: str = "R"

    # STORAGE
    POSTGRES: str = "postgres"

    # UTILITY
    NGINX = "nginx"
    TEXLIVE = "texlive"


PROJECT_NAME = "project_name"
JSON_INDENT = 2
FILE_FORMATS = {
    ".csv",
}


COMPONENTS = {
    Layer.ANALYTICS: [Component.SUPERSET],
    Layer.DEVCONTAINERS: [Component.PYTHON, Component.R],
    Layer.API: [Component.API_POSTGRES],
    Layer.STORAGE: [Component.POSTGRES],
    Layer.UTILITY: [Component.NGINX, Component.TEXLIVE],
}

DEPENDENCIES = {
    Component.API_POSTGRES: {Layer.STORAGE: [Component.POSTGRES]},
}


DESCRIPTIONS = {
    # ANALYTICS
    Component.SUPERSET: "Apache Superset is a modern, enterprise-ready business intelligence web application",  # noqa
    # API
    Component.API_POSTGRES: "REST Data Access for Postgres",
    # DEVCONTAINERS
    Component.PYTHON: "VS Code devcontainer for Python",
    Component.R: "VS Code devcontainer for R",
    # STORAGE
    Component.POSTGRES: "Advanced Relational Database",
    # UTILITY
    Component.NGINX: "HTTP and reverse proxy server",
    Component.TEXLIVE: "TeX Live is intended to be a straightforward way to get up and running with the TeX document production system",  # noqa
}


PORTS = {
    # ANALYTICS
    Component.SUPERSET: "8088",
    # API
    Component.API_POSTGRES: "8000",
    # STORAGE
    Component.POSTGRES: "5432",
    # UTILITY
    Component.NGINX: "80",
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
        return {self.field_name: self.field_type}


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
        self._layers = {}

    @property
    def fields(self):
        """Get fields."""
        return self._fields

    @property
    def layers(self):
        """Get layers."""
        return self._layers

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
                "fields": {k: v.field_type for k, v in self.fields.items()},
                "layers": self.layers,
            }
        }

    def register(self, layer: str, component: str) -> None:
        """Register component at entity level."""
        if layer not in COMPONENTS:
            raise ValueError(f"Layer `{layer}` not found")

        if component not in COMPONENTS[layer]:
            raise ValueError(f"Component `{component}` not found")

        if layer not in self.layers:
            self.layers[layer] = {}

        if component in self.layers[layer]:
            raise ValueError(f"Component `{component}` already exists")

        # TODO: setter/validate names | component config
        self.layers[layer][component] = {}

        dependencies = DEPENDENCIES.get(component, {})
        for deps_layer, deps_components in dependencies.items():
            if deps_layer not in self.layers:
                self.layers[deps_layer] = {}
            for deps_component in deps_components:
                if deps_component not in self.layers[deps_layer]:
                    self.layers[deps_layer][deps_component] = {}


class Project:
    """Project."""

    def __init__(self, name: str, path: str = "", data: str = ""):
        """Create project instance."""
        self._name = None
        self._path = None
        self._profile = Profile.CUSTOM
        self._layout = Layout.CUSTOM
        if data:
            self._data = os.path.join(os.getcwd(), data)
        else:
            self._data = os.path.join(os.getcwd(), "data")

        self._settings = {
            "opendataframework": __version__,
            "project": "",
            "profile": self._profile,
            "layout": self._layout,
            "entities": {},
            "mounts": {},
            "volumes": {},
            "ports": {},
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

        if "mounts" not in value:
            raise ValueError("`mounts` field does not exist")
        if "opendataframework" not in value:
            raise ValueError("`opendataframework` field does not exist")
        if "entities" not in value:
            raise ValueError("`entities` field does not exist")
        if "volumes" not in value:
            raise ValueError("`volumes` field does not exist")
        if "ports" not in value:
            raise ValueError("`ports` field does not exist")
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
            raise ValueError(f"{path} does not exists")
        with open(path, "r") as file:
            self.settings = json.load(file)

    def mounts(self, entity: Entity) -> None:
        """Configure mounts."""
        for layer, components in entity.layers.items():
            for component in components:
                if component not in MOUNTS:
                    continue

                if component in self._settings["mounts"]:
                    continue

                self._settings["mounts"][component] = {}

                if layer is Layer.DEVCONTAINERS:
                    workspace_mount = MOUNTS[component]["workspaceMount"].format(
                        project_name=self.name
                    )
                    self._settings["mounts"][component]["workspaceMount"] = (
                        workspace_mount
                    )

                    workspace_folder = MOUNTS[component]["workspaceFolder"].format(
                        project_name=self.name
                    )
                    self._settings["mounts"][component]["workspaceFolder"] = (
                        workspace_folder
                    )

                    mounts = [
                        mnt.format(project_name=self.name)
                        for mnt in MOUNTS[component]["mounts"]
                    ]
                    self._settings["mounts"][component]["mounts"] = mounts

    def volumes(self, entity: Entity) -> None:
        """Configure volumes."""
        for layer, components in entity.layers.items():
            for component in components:
                if component not in VOLUMES:
                    continue

                if component in self._settings["volumes"]:
                    continue

                self._settings["volumes"][component] = {}
                self._settings["volumes"][component].update(
                    VOLUMES[component].get(self.layout, {})
                )

    def ports(self, entity: Entity) -> None:
        """Configure ports."""
        for layer, components in entity.layers.items():
            for component in components:
                if component not in PORTS:
                    continue

                if layer is Layer.API:
                    if not self._api_ports:
                        port = int(PORTS.get(component))

                    else:
                        port = int(self._api_ports[-1])
                        port += 1
                    port = str(port)
                    self._api_ports.append(port)
                    self._settings["entities"][entity.plural_name]["layers"][layer][
                        component
                    ]["port"] = port
                    continue

                if component in self._settings["ports"]:
                    continue

                port = PORTS.get(component)
                if not port:
                    continue

                self._settings["ports"][component] = port

    def register(self, entity: Entity):
        """Register entity."""
        if entity.plural_name in self.settings["entities"]:
            raise ValueError(f"`{entity.plural_name}` already exists")
        self.settings["entities"].update(entity.to_dict())
        self.mounts(entity)
        self.volumes(entity)
        self.ports(entity)

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

    def init(self):
        """Handler for `init` CLI command."""
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

                for layer, components in COMPONENTS.items():
                    if not components:
                        continue
                    rprint()
                    rprint(f"[#B36AE2]{entity.name} | {layer}[/#B36AE2]")
                    for component in components:
                        if component in entity.layers.get(layer, {}):
                            rprint(f"[bright_black]{component}: y[/bright_black]")
                            continue
                        user_input = (
                            Prompt.ask(f"[#00FA92]{component}[/#00FA92]")
                            .strip()
                            .lower()
                        )
                        if user_input in {"y", "yes"}:
                            entity.register(layer, component)
                    rprint()

                rprint()
                rprint(f"{json.dumps(entity.to_dict(), indent=JSON_INDENT)}")
                rprint()
                self.register(entity)
                rprint(
                    "[#00FA92]Entity[/#00FA92]",
                    f"`[#B36AE2]{entity.name}[/#B36AE2]`",
                    "[#00FA92]created[/#00FA92]",
                )
                rprint()

        self.to_json()
        rprint(f"[#00FA92]Project `[#B36AE2]{self.name}[/#B36AE2]` created[/#00FA92]")

        rprint(f"{json.dumps(self.settings, indent=JSON_INDENT)}")
        rprint()

    def create(
        self,
        docs: bool = True,
        hooks: bool = True,
        workflows: bool = False,
        tests: bool = True,
    ):
        """Handler for `create` CLI command."""
        self.from_json()
        self.add_layout()
        if docs:
            self.add_docs()
        if hooks:
            self.add_hooks()
        if workflows:
            self.add_workflows()
        if tests:
            self.add_tests()

        layers = [
            Analytics(project=self),
            API(project=self),
            Devcontainers(project=self),
            Storage(project=self),
            Utility(project=self),
        ]

        for layer in layers:
            layer()

        self.collect()

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
    def copy(from_path: str, to_path: str, file_name: str):
        """Copy file."""
        src_path = os.path.join(from_path, file_name)
        if not os.path.exists(src_path):
            raise ValueError(f"{src_path} not found")

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

        scripts = ["build.sh", "setup.sh", "start.sh", "stop.sh", "requirements.txt"]

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

        self.copy(from_path, self.path, "env.sh")
        self.copy(from_path, self.path, "expectations.py")
        self.copy(from_path, self.path, "main.sh")
        self.copy(from_path, self.path, "README.md")

        self.replace(os.path.join(self.path, "README.md"), f"{PROJECT_NAME}", self.name)
        self.replace(os.path.join(self.path, "main.sh"), f"{PROJECT_NAME}", self.name)

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
                            current_file_data[:4],
                            current_file_data[4:],
                        )
                        header = [line for line in header if line != "\n"]
                    with open(f"{to_path}/{file_name}", "w") as file:
                        file.write(
                            "\n".join(
                                [*header, src_file_data, *lines, *current_file_data]
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
                lines = files_data[file_name]
                file_path = f"{to_path}/{file_name}"

                # exclude docker compose header
                lines = lines[0].split("\n")[2:]
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
        from_path = os.path.join(SRC_PATH, Layer.ANALYTICS, Component.SUPERSET)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.ANALYTICS, Component.SUPERSET
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("entities", {})
        ports = self.project.settings.get("ports", {})

        to_setup = os.path.join(to_path, "setup.sh")

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.ANALYTICS, {})
            if Component.SUPERSET not in components:
                continue

            if not os.path.exists(to_path):
                shutil.copytree(
                    from_path,
                    to_path,
                    ignore=shutil.ignore_patterns(*IGNORE_PATTERNS, *("database",)),
                )

            storages = settings["layers"].get(Layer.STORAGE, {})
            if not storages:
                continue

            for storage in storages:
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
                    from_path, "database", f"{storage}", "create.sh"
                )

                with open(f"{from_create}", "r") as file:
                    content = file.read()
                    content = content.replace("table-name", f"{plural_name}")

                with open(f"{to_setup}", "a") as file:
                    file.write("&& " + content)

                if PORTS.get(storage) and ports.get(storage):
                    Project.replace(to_setup, PORTS.get(storage), ports.get(storage))

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

        Project.replace(to_setup, PORTS[Component.SUPERSET], ports[Component.SUPERSET])

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
            f"{ports[Component.SUPERSET]}:",
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

    def api_postgres(self):
        """Configure API `API_POSTGRES` component."""
        from_path = os.path.join(SRC_PATH, Layer.API, Component.API_POSTGRES)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        entities = self.project.settings.get("entities", {})

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

            for field_name, field_type in settings["fields"].items():
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

    def __call__(self):
        """Call layer."""
        self.api_postgres()


class Devcontainers:
    """Devcontainers layer."""

    def __init__(self, project: Project):
        """Create Devcontainers layer instance."""
        self.project = project

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

        entities = self.project.settings.get("entities", {})

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

        entities = self.project.settings.get("entities", {})

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
        self.python()
        self.r()


class Storage:
    """Storage layer."""

    def __init__(self, project: Project):
        """Create Storage layer instance."""
        self.project = project

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

        entities = self.project.settings.get("entities", {})
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
        self.postgres()


class Utility:
    """Utility layer."""

    def __init__(self, project: Project):
        """Create Utility layer instance."""
        self.project = project

    def nginx(self):
        """Configure Analytics `NGINX` component."""
        from_path = os.path.join(SRC_PATH, Layer.UTILITY, Component.NGINX)
        if not os.path.exists(from_path):
            raise ValueError(f"{from_path} does not exist")

        to_path = os.path.join(
            self.project.path, PLATFORM_FOLDER, Layer.UTILITY, Component.NGINX
        )
        if os.path.exists(to_path):
            raise ValueError(f"{to_path} already exists")

        entities = self.project.settings.get("entities", {})

        for plural_name, settings in entities.items():
            components = settings["layers"].get(Layer.UTILITY, {})
            if Component.NGINX not in components:
                continue

            if os.path.exists(to_path):
                raise ValueError(f"{to_path} already exists")

            shutil.copytree(
                from_path,
                to_path,
                ignore=shutil.ignore_patterns(*IGNORE_PATTERNS),
            )

            break

        if not os.path.exists(to_path):
            return

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            PROJECT_NAME,
            self.project.settings["project"],
        )

        ports = self.project.settings.get("ports", {})

        Project.replace(
            os.path.join(to_path, "docker-compose.yaml"),
            f"{PORTS[Component.NGINX]}:",
            f"{ports[Component.NGINX]}:",
        )

        host = "http://localhost"
        target_path = os.path.join(to_path, "static", "index.html")

        Project.replace(target_path, PROJECT_NAME, self.project.settings["project"])

        with open(target_path, "r") as file:
            filedata = file.read()

        header = filedata.split("<tbody>")[0]
        template, _ = filedata.split("<tbody>")[1].split("</tbody>")
        footer = filedata.split("</tbody>")[1]

        lines = [header]

        for component, port in ports.items():
            layer = None
            for current_layer, components in COMPONENTS.items():
                if component in components:
                    layer = current_layer
                    break
            if not layer:
                continue

            tr = template.replace(
                'class="badge badge-info gap-2">layer_name',
                f'class="{BADGES[layer]}">{layer}',
            )
            tr = tr.replace("component_name", f"{component}")
            tr = tr.replace("http://host:port/", f"{host}:{port}/")
            lines.append(tr)

        entities = self.project.settings.get("entities", {})

        for plural_name, settings in entities.items():
            layers = settings.get("layers", {})

            if Component.NGINX not in layers.get(Layer.UTILITY, {}):
                continue

            for layer, components in layers.items():
                for component in components:
                    port = components[component].get("port")
                    if not port:
                        continue

                    tr = template.replace(
                        'class="badge badge-info gap-2">layer_name',
                        f'class="{BADGES[layer]}">{layer}',
                    )
                    tr = tr.replace("component_name", f"{component} | {plural_name}")
                    tr = tr.replace("http://host:port/", f"{host}:{port}/")
                    lines.append(tr)

        lines.append(footer)
        filedata = "\n".join(lines)
        with open(target_path, "w") as file:
            file.write(filedata)

        rprint(f"{to_path}[green] created[/green]")

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

        entities = self.project.settings.get("entities", {})

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
        self.nginx()
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
                entity.register(Layer.DEVCONTAINERS, Component.R)
                entity.register(Layer.UTILITY, Component.TEXLIVE)

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
):
    """Initialize PROJECT settings.json, optionally with a --path."""
    try:
        project = Project(name=project, path=path, data=data)
        profile = profile.strip().lower()
        if profile == Profile.CUSTOM:
            project.init()
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
):
    """Create PROJECT structure based on settings.json, optionally with a --path."""
    try:
        project = Project(name=project, path=path)
        project.create(docs=docs, hooks=hooks, workflows=workflows, tests=tests)
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


def main():
    """Main function which starts the app."""
    rprint(colorized_logo())
    app()


if __name__ == "__main__":
    main()
