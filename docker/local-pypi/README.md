# Local PyPI server

A throwaway [`pypiserver`](https://github.com/pypiserver/pypiserver) instance,
for testing `opendataframework` publishes/installs before pushing to the real
PyPI. Any contributor can spin it up locally; the uploaded-packages directory
it stores state in (`packages/`) is gitignored, the tooling here isn't.

## Start

```bash
cd docker/local-pypi
docker compose up -d --build
```

The server listens on http://localhost:8080 (package index at
http://localhost:8080/simple/). Uploaded packages land in
`docker/local-pypi/packages/` on the host (bind-mounted, gitignored) and
persist across restarts — delete that directory to reset the index.

## Configure Poetry to publish here

```bash
poetry config repositories.local-pypi http://localhost:8080
poetry config http-basic.local-pypi anyuser anypassword
```

Auth is disabled on the server (`-a . -P .` in the Dockerfile's `CMD`), so the
credentials above just need to be present — their value doesn't matter. Never
run the server this way anywhere but localhost.

## Publish

From the repo root:

```bash
poetry build
poetry publish -r local-pypi
```

## Install from it

```bash
pip install --index-url http://localhost:8080/simple/ opendataframework
```

## Stop

```bash
docker compose down
```
