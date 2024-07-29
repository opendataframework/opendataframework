# Open Data Framework

![logo](images/logo.svg) <br/>

## Build from the source
1. This package requires [poetry](https://python-poetry.org/docs/#installation) to be installed in your system first. <br /> Optional: Set [virtualenvs.in-project](https://python-poetry.org/docs/configuration/#virtualenvsin-project) to `true` by running `poetry config virtualenvs.in-project true` to create `.venv` inside project's folder.
2. Clone [opendataframework](https://github.com/opendataframework/opendataframework).
2. Install `opendataframework` in [editable mode](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs) with dependencies by running `poetry install`.
3. Run app: `python -m opendataframework --help`

## Project layout
    docs/
        images/
            logo.svg
        stylesheets/
            extra.css
        index.md
    src/
        opendataframework/
            __init__.py
            __main__.py
    tests/
        __init__.py
        test_main.py
    .gitignore
    .pre-commit-config.yaml
    CITATION.cff
    LICENSE
    mkdocs.yml
    poetry.lock
    pyproject.toml
    README.md
