"""Configuration loading and typed access.

``load()`` reads TOML files/directories into a plain dict; ``Config``
wraps that dict with normalised attribute/item access. ``Project``
resolves a ``Config`` instance into the container automatically, so
components declare it like any other constructor dependency.
"""

import tomllib
from pathlib import Path

from opendataframework.utils import normalize


class Config:
    """Immutable view over a configuration dictionary.

    Wraps a nested dict and provides attribute and item access with automatic
    name normalisation (snake_case and kebab-case are interchangeable). Nested
    dicts are returned as ``Config`` objects, so access can be chained.

    Registered automatically by ``Project.from_config`` and
    ``Project.from_dict`` — components that declare ``config: Config`` as a
    constructor dependency receive this instance via DI.

    Example:
        >>> cfg = Config({"database-url": "postgres://localhost/db"})
        >>> cfg.database_url
        'postgres://localhost/db'
        >>> cfg["database-url"]
        'postgres://localhost/db'

        Nested access::

            cfg = Config({"storage": {"postgres": {"port": 5432}}})
            cfg.storage.postgres.port  # → 5432
    """

    def __init__(self, data: dict) -> None:
        """Wrap ``data``, a (possibly nested) configuration dict."""
        self._data = data

    def __getattr__(self, name: str) -> Config | object:
        """Return value by snake_case attribute name, normalised to kebab-case.

        Args:
            name: Attribute name (snake_case or kebab-case).

        Returns:
            A ``Config`` wrapping the value if it is a dict, otherwise the
            raw value.

        Raises:
            AttributeError: If the key is not present.
        """
        try:
            value = self._data[normalize(name)]
        except KeyError as err:
            raise AttributeError(name) from err
        return Config(value) if isinstance(value, dict) else value

    def __getitem__(self, key: str) -> Config | object:
        """Return value by key (any name form accepted).

        Args:
            key: Config key in any supported form.

        Returns:
            A ``Config`` wrapping the value if it is a dict, otherwise the
            raw value.

        Raises:
            KeyError: If the key is not present.
        """
        try:
            value = self._data[key]
        except KeyError as err:
            raise KeyError(key) from err
        return Config(value) if isinstance(value, dict) else value

    def get(self, key: str, default: object = None) -> Config | object | None:
        """Return value by key, or ``default`` if absent.

        If ``default`` is not given and the key is absent, an empty
        ``Config`` is returned instead of ``None``, so callers can safely
        scope into a section and chain further ``.get()``/attribute access
        without guarding against it being missing:

            cfg = config.get("postgres")
            url = cfg.database_url          # AttributeError if missing
            port = cfg.get("port", 5432)    # safe fallback

        Args:
            key: Config key.
            default: Fallback value when the key is not present.

        Returns:
            A ``Config`` wrapping the value if it is a dict, the raw value
            if it is a scalar, ``default`` if given and the key is absent,
            or an empty ``Config`` if the key is absent and no default was
            given.
        """
        value = self._data.get(key)
        if value is None:
            return default if default is not None else Config({})
        return Config(value) if isinstance(value, dict) else value


def load(path: str) -> dict:
    """Load configuration from a TOML file or directory of TOML files.

    When given a directory, all ``*.toml`` files are loaded in alphabetical
    order and deep-merged — later files override earlier ones for scalar
    values; dicts are merged recursively.

    Args:
        path: Path to a ``.toml`` file or a directory containing ``.toml``
            files.

    Returns:
        Merged configuration as a plain dict.

    Raises:
        FileNotFoundError: If ``path`` does not exist.

    Example:
        >>> config = load("config.toml")
        >>> config["postgres"]["database-url"]
        'postgresql://localhost/mydb'
    """
    p = Path(path)
    if p.is_file():
        return _load_file(p)
    if p.is_dir():
        result: dict = {}
        for f in sorted(p.glob("*.toml")):
            result = _deep_merge(result, _load_file(f))
        return result
    raise FileNotFoundError(f"Config path not found: {path}")


def _load_file(path: Path) -> dict:
    """Parse a single TOML file into a dict."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge ``override`` into ``base``, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
