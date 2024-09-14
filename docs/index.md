# Open Data Framework
Open source, full stack data framework.

## Installation
<!-- termynal -->

```
$ pip install opendataframework
---> 100%
Installed
```
### Create data folder
> Name (required): `data`

<!-- termynal -->

```
$ mkdir data
```
### Create data file

> Name (can be any): `events.csv`

#### Types supported

> int, float, str, datetime

| id | name    | value  | logged_at           |
| -- | ------- | ------ | ------------------- |
| 1  | noname  | 0.1    | 2024-01-01 00:00:00 |

<!-- termynal -->

```
$ cat > data/events.csv << EOF
id,name,value,logged_at
1,noname,0.1,2024-01-01 00:00:00
EOF

$ tree
.
└── data
    └── events.csv
```

### Init
> Name (can be any): `myproject`

<!-- termynal -->

```
$ opendataframework init myproject --profile research
./myproject/settings.json created

$ tree
.
├── data
│   └── events.csv
└── myproject
    ├── data
    │   └── events.csv
    └── settings.json
```

#### settings.json

<!-- termynal -->

```
$ cat myproject/settings.json
{
  "opendataframework": "0.0.2",
  "project": "myproject",
  "profile": "research",
  "layout": "research",
  "entities": {
    "events": {
      "name": "event",
      "description": "events research",
      "fields": {
        "id": "int",
        "name": "str",
        "value": "float",
        "logged_at": "datetime|%Y-%m-%d %H:%M:%S"
      },
      "layers": {
        "devcontainers": {
          "R": {}
        },
        "utility": {
          "texlive": {}
        }
      }
    }
  },
  "mounts": {
    "R": {
      "workspaceMount": "source=${localWorkspaceFolder},target=/myproject,type=bind",
      "workspaceFolder": "/myproject",
      "mounts": [
        "source=${localWorkspaceFolder}/../../../data,target=/myproject/data,type=bind,consistency=cached"
      ]
    }
  },
  "volumes": {
    "texlive": {
      "../output": "/usr/src/app/mnt/output",
      "../paper": "/usr/src/app/mnt/paper"
    }
  },
  "ports": {}
}

```

### Create
<!-- termynal -->

```
$ opendataframework create myproject
events.csv moved to
./myproject/data/raw/events.csv
myproject: research layout created
./myproject/platform/devcontainers/R created
./myproject/platform/utility/texlive created

$ tree
.
├── data
│   └── events.csv
└── myproject
    ├── README.md
    ├── code
    │   ├── build
    │   ├── check
    │   ├── learn
    │   └── share
    ├── data
    │   ├── derived
    │   └── raw
    │       └── events.csv
    ├── env.sh
    ├── expectations.py
    ├── libraries
    ├── logs
    ├── main.sh
    ├── models
    ├── output
    │   ├── figures
    │   └── tables
    ├── paper
    ├── platform
    │   ├── build.sh
    │   ├── devcontainers
    │   │   └── R
    │   ├── docker-compose.yaml
    │   ├── setup.sh
    │   ├── start.sh
    │   ├── stop.sh
    │   └── utility
    │       └── texlive
    │           ├── Dockerfile
    │           └── mnt
    ├── requirements.txt
    └── settings.json
```

### Build platform
Command builds platform's images.

<!-- termynal -->

```
$ opendataframework build myproject
```

### Start platform
Command starts platform's containers.

<!-- termynal -->

```
$ opendataframework start myproject
```

### Setup platform
Command setup platform's containers.

<!-- termynal -->

```
$ opendataframework setup myproject
```

### Install dependencies
Command creates `myproject/.venv/` and installs dependencies from `requirements.txt`.

<!-- termynal -->

```
$ opendataframework install myproject
```

## Build from the source
1. This package requires [poetry](https://python-poetry.org/docs/#installation) to be installed in your system first.
> Optional: Set [virtualenvs.in-project](https://python-poetry.org/docs/configuration/#virtualenvsin-project) to `true` by running `poetry config virtualenvs.in-project true` to create `.venv` inside project's folder.
2. Clone [opendataframework](https://github.com/opendataframework/opendataframework).
3. Install `opendataframework` in [editable mode](https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs) with dependencies by running: `poetry install`.


## Concepts

### Layout
Predefined project layout and scripts to get up & running.

#### Research

```
.
├── code
│   ├── build
│   ├── check
│   ├── learn
│   └── share
├── data
│   ├── derived
│   └── raw
├── libraries
├── logs
├── models
├── output
│   ├── figures
│   └── tables
└── paper
```

#### Custom
> No Layout (default)

### Platform
Data platform. Set of pre-configured, open source, containerized tools used in project, hosted locally or deployed.

#### Layers & Components
Layers of data platform with containerized components.

##### analytics
###### [superset](https://superset.apache.org/)

##### api
###### [fastapi](https://fastapi.tiangolo.com/)

##### devcontainers
###### [python](https://www.python.org/)
###### [R](https://www.r-project.org/)

##### storage
###### [postgresql](https://www.postgresql.org/)

##### utility
###### [nginx](https://nginx.org/en/)
###### [TeX Live](https://hub.docker.com/r/texlive/texlive)

### Profile
Pre-configured layout & data platform.

#### Research
> Configuration for `Research` project.

#### Custom
> Manual configuration via CLI.
