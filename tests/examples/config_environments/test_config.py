from pathlib import Path

from app.components import Greeter

from opendataframework.config import Config, load

# Deliberately builds Greeter directly from a Config rather than going
# through Project/Context — same reason as the other examples' tests, see
# tests/examples/entity_repository/test_books.py.

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "07-config-environments"


def test_dev_config_directory_merges_into_expected_dict():
    config = load(str(EXAMPLE_DIR / "config" / "dev"))

    assert config["project"]["name"] == "config-environments-example"
    assert config["greeter"] == {"greeting": "Yo", "name": "Dev"}


def test_prod_config_directory_merges_into_expected_dict():
    config = load(str(EXAMPLE_DIR / "config" / "prod"))

    assert config["greeter"] == {"greeting": "Hello", "name": "Production"}


def test_greeter_reads_greeting_and_name_from_config():
    greeter = Greeter(Config({"greeter": {"greeting": "Hi", "name": "Test"}}))

    assert greeter.greet() == "Hi, Test!"


def test_greeter_falls_back_to_defaults():
    greeter = Greeter(Config({}))

    assert greeter.greet() == "Hello, World!"
