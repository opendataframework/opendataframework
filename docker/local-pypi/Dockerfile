FROM python:3.12-slim

RUN pip install --no-cache-dir "pypiserver>=2.0,<3.0"

RUN mkdir -p /data/packages
VOLUME /data/packages

EXPOSE 8080

ENTRYPOINT ["pypi-server", "run"]
CMD ["--host", "0.0.0.0", "--port", "8080", "-a", ".", "-P", ".", "/data/packages"]
