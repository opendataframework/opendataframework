FROM python:3.11.2
WORKDIR /api

COPY .env pyproject.toml ./


ARG poetry_version=1.3.2
RUN pip install poetry==${poetry_version}
RUN poetry config virtualenvs.create false
RUN poetry install

COPY app/ app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
