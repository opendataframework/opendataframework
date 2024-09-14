# project_name

## Build & setup platform
```sh
chmod +x ./main.sh && source ./main.sh
```

## Expectations
```sh
# [activate venv] source .venv/bin/activate
python expectations.py -d data/raw/
```

## Ingest
```sh
# [activate venv] source .venv/bin/activate
python ingest.py -d data/raw/
```
