"""Open Data Framework package."""
import csv
import os
import re
import yaml
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader


__version__ = "0.0.4"


@dataclass
class Constants:
    DATA_FOLDER: str = "data"
    PLATFORM_FOLDER: str = "platform"
    SRC_PATH: str = Path(__file__).parent
    TEMPLATES_PATH: str = os.path.join(SRC_PATH, "templates")


class DataType(StrEnum):
    STRUCTURED = "STRUCTURED"
    SEMI_STRUCTURED = "SEMI_STRUCTURED"
    UNSTRUCTURED = "UNSTRUCTURED"


class Field:
    """Data Field."""

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

    def __init__(self, name: str, path: str, *args, **kwargs):
        """Create entity instance."""
        self._name = None
        self._path = None
        self._description = ""

        self.name = name
        self.path = path
        
        self._file_name = os.path.basename(self.path)

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
    def file_name(self) -> str:
        return self._file_name

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

        if not os.path.exists(path):
            raise ValueError(f"{path} does not exists")

        self._path = path


class StructuredEntity(Entity):
    DATA_TYPE = DataType.STRUCTURED

    def __init__(self, name: str, path: str, *args, **kwargs):
        super().__init__(name, path)
        self._plural_name = None
        self._fields = {}

        self.plural_name = name
    
    @property
    def fields(self):
        """Get fields."""
        return self._fields
    
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
                "type": self.DATA_TYPE.lower(),
                "fields": {
                    k: {"type": v.field_type, "alias": v.field_alias}
                    for k, v in self.fields.items()
                }
            }
        }


class SemiStructuredEntity(Entity):
    ...


class UnstructuredEntity(Entity):
    ...


class CSVEntity(StructuredEntity):
    def __init__(self, name: str, path: str, newline="", *args, **kwargs):
        super().__init__(name, path)

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


class JSONEntity(SemiStructuredEntity):
    ...


class TXTEntity(UnstructuredEntity):
    ...


class Template:
    def __init__(self, name: str, path: str) -> None:
        self._name = name
        self._path = path
        self._env = Environment(loader=FileSystemLoader(self._path))
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def path(self) -> str:
        return self._path
    
    def render(self, *args: Any, **kwargs: Any) -> str:
        return self._env.get_template(self.name).render(*args, **kwargs)

    def load_yaml(self, *args: Any, **kwargs: Any) -> dict:
        return yaml.safe_load(self.render(*args, **kwargs))

    def write(self, name: str, path: str, *args: Any, **kwargs: Any) -> None:
        with open(os.path.join(path, name), "w") as f:
            f.write(self.render(*args, **kwargs))


class Component:
    def __init__(self, path: str):
        self._path = Path(path)
        self._env = {}
        self._config = {}
    
    @property
    def path(self) -> str:
        return self._path
    
    @property
    def name(self) -> str:
        return self._path.name
    
    @property
    def layer(self) -> str:
        return self._path.parent.name

    @property
    def env(self) -> dict:
        return self._env

    @property
    def config(self) -> dict:
        return self._config
    
    def __call__(self, *args, **kwds):
        raise NotImplementedError


class Postgres(Component):

    def __call__(self, 
                 path: str, 
                 data: list[CSVEntity] = None, 
                 *args, **kwargs):
        env = Template(name=".env.j2", path=self.path)
        self._env = env.load_yaml()

        type_map = {
            "str": "TEXT",
            "int": "INTEGER",
            "float": "REAL",
            "datetime": "TIMESTAMP"
        }

        tables = {}
        
        volumes = [
            f"./{Constants.PLATFORM_FOLDER}/{self.layer}/{self.name}/init.sql:/docker-entrypoint-initdb.d/init.sql",
            f"./{Constants.PLATFORM_FOLDER}/{self.layer}/{self.name}/data:/var/lib/postgresql/data"
        ]

        for entity in data:
            volume = f"./{Constants.DATA_FOLDER}/{entity.file_name}:/docker-entrypoint-initdb.d/{entity.file_name}"
            volumes.append(volume)
            
            columns = {}
            for column, field in entity.fields.items():
                if "datetime" in field.field_type:
                    columns[column] = type_map["datetime"]
                else:
                    columns[column] = type_map[field.field_type]
            tables[entity.name] = columns

        config = Template(name="config.yaml.j2", path=self.path)
        self._config = config.load_yaml(
            service_name=self.name, 
            environment=[f"{k}=${k}" for k in self.env], 
            volumes=volumes
        )

        template = Template(name="init.sql.j2", path=self.path)
        template.write(name="init.sql", path=path, tables=tables)
        

class Layer:
    ...


class Layout:
    ...


class Profile:
    ...


class Settings:
    ...


class Project:
    ...
