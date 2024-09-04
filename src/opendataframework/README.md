# project_name

## Build & setup platform
```sh
chmod +x ./main.sh && source ./main.sh
```

## Start platform
```sh
cd platform && ./start.sh && cd ..
```

## Stop platform
```sh
cd platform && ./stop.sh && cd ..
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
