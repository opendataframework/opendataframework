import pytest

from opendataframework.config import Config, load

# --- Config attribute access -------------------------------------------------


def test_scalar_attribute_access():
    cfg = Config({"host": "localhost"})
    assert cfg.host == "localhost"


def test_snake_to_kebab_attribute_access():
    cfg = Config({"database-url": "postgres://localhost/db"})
    assert cfg.database_url == "postgres://localhost/db"


def test_missing_attribute_raises():
    cfg = Config({"host": "localhost"})
    with pytest.raises(AttributeError):
        _ = cfg.missing


# --- Config item access ------------------------------------------------------


def test_item_access_exact_key():
    cfg = Config({"database-url": "postgres://localhost/db"})
    assert cfg["database-url"] == "postgres://localhost/db"


def test_missing_item_raises():
    cfg = Config({"host": "localhost"})
    with pytest.raises(KeyError):
        _ = cfg["missing"]


# --- Config nested access ----------------------------------------------------


def test_nested_dict_returns_config():
    cfg = Config({"storage": {"postgres": {"port": 5432}}})
    assert isinstance(cfg.storage, Config)
    assert isinstance(cfg.storage.postgres, Config)


def test_nested_scalar_access():
    cfg = Config({"storage": {"postgres": {"port": 5432}}})
    assert cfg.storage.postgres.port == 5432


def test_nested_item_access():
    cfg = Config({"storage": {"postgres": {"port": 5432}}})
    assert cfg["storage"]["postgres"]["port"] == 5432


# --- Config.get --------------------------------------------------------------


def test_get_existing_key():
    cfg = Config({"host": "localhost"})
    assert cfg.get("host") == "localhost"


def test_get_missing_key_returns_default():
    cfg = Config({})
    assert cfg.get("missing", "default") == "default"


def test_get_missing_key_returns_empty_config_by_default():
    cfg = Config({})
    sub = cfg.get("missing")
    assert isinstance(sub, Config)
    assert sub.get("anything", "fallback") == "fallback"


def test_get_nested_dict_returns_config():
    cfg = Config({"db": {"host": "localhost"}})
    sub = cfg.get("db")
    assert isinstance(sub, Config)
    assert sub["host"] == "localhost"


def test_get_chained_scoped_access():
    cfg = Config({"postgres": {"port": 5432}})
    sub = cfg.get("postgres")
    assert sub.port == 5432
    assert sub.get("pool-size", 10) == 10


def test_get_missing_section_allows_safe_chaining():
    cfg = Config({})
    sub = cfg.get("postgres")
    assert isinstance(sub, Config)
    assert sub.get("port", 5432) == 5432


# --- load: single file -------------------------------------------------------


def test_load_single_toml_file(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[database]\nurl = "postgres://localhost/db"\n')

    data = load(str(f))
    assert data == {"database": {"url": "postgres://localhost/db"}}


def test_load_flat_values(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('host = "localhost"\nport = 5432\n')

    data = load(str(f))
    assert data == {"host": "localhost", "port": 5432}


# --- load: directory ---------------------------------------------------------


def test_load_directory_merges_files(tmp_path):
    (tmp_path / "a.toml").write_text('[db]\nhost = "localhost"\n')
    (tmp_path / "b.toml").write_text("[db]\nport = 5432\n")

    data = load(str(tmp_path))
    assert data == {"db": {"host": "localhost", "port": 5432}}


def test_load_directory_later_file_overrides(tmp_path):
    (tmp_path / "a.toml").write_text('host = "alpha"\n')
    (tmp_path / "b.toml").write_text('host = "beta"\n')

    data = load(str(tmp_path))
    assert data["host"] == "beta"


def test_load_directory_alphabetical_order(tmp_path):
    (tmp_path / "z.toml").write_text("val = 1\n")
    (tmp_path / "a.toml").write_text("val = 2\n")

    data = load(str(tmp_path))
    assert data["val"] == 1  # z.toml wins: z > a alphabetically, so a first then z overrides


def test_load_empty_directory(tmp_path):
    data = load(str(tmp_path))
    assert data == {}


# --- load: errors ------------------------------------------------------------


def test_load_missing_path_raises():
    with pytest.raises(FileNotFoundError):
        load("/nonexistent/config.toml")
