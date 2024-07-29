"""Tests for main module."""

from opendataframework.__main__ import app, colorized_logo
from typer.testing import CliRunner

runner = CliRunner()


def test_init():
    """Tests app's `init` command."""
    result = runner.invoke(app, ["init", "PROJECT"])
    assert result.exit_code == 0
    assert "is not intended for use" in result.stdout


def test_setup():
    """Tests app's `setup` command."""
    result = runner.invoke(app, ["setup", "PROJECT"])
    assert result.exit_code == 0
    assert "is not intended for use" in result.stdout


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
