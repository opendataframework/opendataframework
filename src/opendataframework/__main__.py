"""Main module."""

import typer
from rich import print as rprint

from opendataframework import __version__


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


app = typer.Typer()


@app.command()
def init(project, path: str = None):
    """Initialize PROJECT, optionally with a --path."""
    rprint(f"[bright_black]{__version__} is not intended for use[/bright_black]")


@app.command()
def setup(project, path: str = None):
    """Setup PROJECT, optionally with a --path."""
    rprint(f"[bright_black]{__version__} is not intended for use[/bright_black]")


def main():
    """Main function which starts the app."""
    rprint(colorized_logo())
    app()


if __name__ == "__main__":
    main()
