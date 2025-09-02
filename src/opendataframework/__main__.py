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
from jinja2 import Environment, FileSystemLoader
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
TEMPLATES_PATH = os.path.join(SRC_PATH, "templates")


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

    STORAGE: str = "storage"


class Component:
    """Component names."""

    # STORAGE
    POSTGRES: str = "postgres"


PROJECT_NAME = "project_name"
JSON_INDENT = 2
FILE_FORMATS = {
    ".csv",
}


class Settings:
    JSON = 'json'
    YAML = 'yaml'


COMPONENTS = {
    Layer.STORAGE: [Component.POSTGRES],
}

DEPENDENCIES = {}

ENTIIES = {
    Component.POSTGRES: {
        "name": "data",
        "type": "list"
    }
}


DESCRIPTIONS = {
    # STORAGE
    Component.POSTGRES: "Advanced Relational Database",
}


PORTS = {
    # STORAGE
    Component.POSTGRES: "5432",
}

LAYOUTS = {Layout.CUSTOM}


PROFILES = {Profile.CUSTOM}


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
            "data": {},
            "platform": {},
            "network": {"name": f"{name}_network", "driver": "bridge"}
        }
        self.name = name
        self.path = path

        self._api_ports = []

        self.services = {}

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

    def ports(self) -> None:
        """Configure ports."""
        for component, settings in self.settings["platform"].items():
            port = PORTS.get(component)
            
            if not port:
                continue

            self._settings["platform"][component]["port"] = port
    
    def configure(self) -> None:
        for component, settings in self.settings["platform"].items():
            path = os.path.join(SRC_PATH, "templates", settings["layer"], component)
            if not os.path.exists(path):
                print(f"{path} does not exist")  # TODO
                continue
            env = Environment(loader=FileSystemLoader(path))
            port = self._settings["platform"][component].get("port")
            if port:
                self._settings["platform"][component].update(yaml.safe_load(env.get_template("config.yaml.j2").render(container_port=port, host_port=port)))
            else:
                self._settings["platform"][component].update(yaml.safe_load(env.get_template("config.yaml.j2").render()))
            self._settings["platform"][component]["env"] = yaml.safe_load(env.get_template(".env.j2").render())
    
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
            if component not in self.settings["platform"]:
            
                self.settings["platform"][component] = {"layer": layer}
                
                if component in ENTIIES:
                    name = ENTIIES[component]["name"]
                    if ENTIIES[component]["type"] == "list":
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
            else:
                if component in ENTIIES and ENTIIES[component]["type"] == "list":
                    self.settings["platform"][component][ENTIIES[component]["name"]].append(entity.plural_name)


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
        
        self.ports()
        self.configure()
        
        if extention == Settings.JSON:
            self.to_json()
        else:
            self.to_yaml()
        rprint(f"[#00FA92]Project `[#B36AE2]{self.name}[/#B36AE2]` created[/#00FA92]")

        rprint(f"{json.dumps(self.settings, indent=JSON_INDENT)}")
        rprint()
    
    def compose(self) -> None:
        """Create docker-compose.yaml."""
        path = os.path.join(self.path, PLATFORM_FOLDER)
        os.makedirs(path, exist_ok=True)
        
        path = os.path.join(path, "docker-compose.yaml")
        
        services = {"services": self.services}
        services.update({"networks": self.settings["network"]})
        
        with open(path, "w") as file:
            yaml.dump(json.loads(json.dumps(services)), file, sort_keys=False)
        
        rprint(f"{path} [green]created[/green]")

    def create(
        self,
        server: bool = True,
    ):
        """Handler for `create` CLI command."""
        self.load()
        # if server:
        #     self.add_server()

        layers = [
            Storage(project=self),
        ]

        for layer in layers:
            layer()

        self.compose()

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


class Storage:
    """Storage layer."""

    def __init__(self, project: Project):
        """Create Storage layer instance."""
        self.project = project

    def postgres(self):
        """Configure Storage `POSTGRES` component."""
        config = self.project.settings["platform"].get(Component.POSTGRES)
        if not config: return

        path = os.path.join(TEMPLATES_PATH, Layer.STORAGE, Component.POSTGRES)
        env = Environment(loader=FileSystemLoader(path))

        # if not config["data"]:
        #     return

        type_map = {
            "str": "TEXT",
            "int": "INTEGER",
            "float": "REAL",
            "datetime": "TIMESTAMP"
        }

        tables = {}
        volumes = {}

        for table_name in config["data"]:
            columns = {}
            fields = self.project.settings["data"][table_name]["fields"]
            for field in fields:
                if "datetime" in fields[field]["type"]:
                    columns[field] = type_map["datetime"]
                else:
                    columns[field] = type_map[fields[field]["type"]]
            tables[table_name] = columns
            volumes[f"../data/{table_name}.csv"] = f"/docker-entrypoint-initdb.d/{table_name}.csv"

        path = os.path.join(self.project.path, PLATFORM_FOLDER, Layer.STORAGE, Component.POSTGRES)
        os.makedirs(path, exist_ok=True)
    
        path = os.path.join(path, "init.sql")
        with open(path, "w") as f:
            f.write(
                env.get_template("init.sql.j2").render(
                    tables=tables
                )
            )
        
        volumes[os.path.join(Layer.STORAGE, Component.POSTGRES, "init.sql")] = "/docker-entrypoint-initdb.d/init.sql"
        
        self.project.services.update(
            yaml.safe_load(
                env.get_template("service.yml.j2").render(
                    service_name=Component.POSTGRES,
                    image=config["image"], 
                    host_port=config["host_port"],
                    container_port=config["container_port"], 
                    env=config["env"],
                    volumes=volumes,
                    network=self.project.settings["network"]
                )
            )
        )
        rprint(f"{path} [green]created[/green]")

    def __call__(self):
        """Call layer."""
        self.postgres()


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
        else:
            raise ValueError(f"Invalid Profile. Supported profiles are: {PROFILES}")
    except Exception:
        rprint(f"[bold red]{traceback.format_exc()}[/bold red]")


@app.command()
def create(
    project: str,
    path: str = "",
    server: bool = True,
):
    """Create PROJECT structure based on settings.json, optionally with a --path."""
    try:
        project = Project(name=project, path=path)
        project.create(server=server)
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


def main():
    """Main function which starts the app."""
    rprint(colorized_logo())
    app()


if __name__ == "__main__":
    main()
