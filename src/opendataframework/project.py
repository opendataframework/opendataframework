"""``Project`` — the framework's composition root.

``Project`` owns a ``Context`` and exposes ``start()``/``stop()`` as a
pure DI lifecycle boundary. It has no knowledge of any UI/CLI/MCP layer
— those are composed on top of it by consuming packages (e.g. ``odf``).
"""

from opendataframework.config import load as load_config
from opendataframework.context import Context


class Project:
    """Composition root that owns the ``Context``.

    ``Project`` is the single entry point for starting and stopping an
    application. It resolves all registered components and drives their
    lifecycle. Use ``project.context.get(cls)`` for typed access to any
    resolved instance after ``start()`` returns.

    Args:
        context: The ``Context`` to use. If omitted, a default ``Context``
            (collecting from all built-in namespaces) is created automatically.
            Pass an explicit ``Context`` to control which namespaces are
            collected — primarily useful in tests.

    Example:
        Typical usage with context manager::

            with Project() as project:
                project.context.get(Users).all()
                project.context.get(MetricsFetcher).execute()

        Explicit start/stop::

            project = Project()
            project.start()

            results = project.context.get(Users).all()

            project.stop()

        Test isolation — pass a scoped ``Context``::

            ctx = Context(namespaces={NS})
            with Project(context=ctx) as project:
                assert isinstance(project.context.instances[Svc], Svc)
    """

    def __init__(
        self,
        context: Context | None = None,
        config: dict | None = None,
    ) -> None:
        """Store ``config`` and use ``context``, or a default ``Context`` if omitted."""
        self._context = context if context is not None else Context()
        self._config = config

    @property
    def config(self) -> dict:
        """Raw configuration dict, populated by ``from_config`` or ``from_dict``.

        Returns:
            The configuration dict, or an empty dict if no config was provided.
        """
        return self._config or {}

    @property
    def context(self) -> Context:
        """The underlying ``Context`` instance.

        Available before and after ``start()``. Primarily useful for
        framework extension authors and lower-level access.

        Returns:
            The ``Context`` owned by this project.
        """
        return self._context

    def start(self) -> None:
        """Resolve all components and drive their startup lifecycle.

        Calls ``Context.open()``. Blocks until all components have completed
        their initialisation stage.

        Raises:
            ValueError: If a circular dependency is detected.
        """
        self._context.open()

    def stop(self) -> None:
        """Tear down all components in reverse dependency order.

        Calls ``Context.close()``. Safe to call even if ``start()`` was
        never called.
        """
        self._context.close()

    def __enter__(self) -> Project:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    @classmethod
    def from_config(cls, path: str) -> Project:
        """Create a ``Project`` from a config file or directory.

        Parses the TOML file at ``path``, or deep-merges all ``*.toml``
        files in the directory at ``path`` (alphabetical order), then
        delegates to :meth:`from_dict`.

        Args:
            path: Path to a ``.toml`` config file or a directory of
                ``.toml`` files to be merged.

        Returns:
            A new ``Project`` configured from the given path.

        Raises:
            FileNotFoundError: If ``path`` does not exist.

        Example:
            Single file::

                project = Project.from_config("config.toml")

            Directory — all ``*.toml`` files are merged::

                project = Project.from_config("config/prod/")
        """
        return cls.from_dict(load_config(path))

    @classmethod
    def from_dict(cls, config: dict) -> Project:
        """Create a ``Project`` from a config dictionary.

        Stores the config and pre-seeds a :class:`~opendataframework.config.Config`
        instance into the ``Context`` so that components which declare
        ``config: Config`` in their constructors receive it via DI.

        Also enables per-component file logging under ``[project] log-dir``
        (default ``"logs"``, relative to the current working directory) —
        see ``opendataframework.logger.LogManager``.

        Args:
            config: Mapping of configuration values, equivalent to what
                ``from_config`` would parse from a ``.toml`` file.

        Returns:
            A new ``Project`` configured from the given dict.

        Example:
            ::

                project = Project.from_dict({
                    "storage": {
                        "postgres": {"database-url": "postgresql://localhost/db"}
                    }
                })
        """
        log_dir = config.get("project", {}).get("log-dir", "logs")
        return cls(context=Context(config=config, log_dir=log_dir), config=config)
