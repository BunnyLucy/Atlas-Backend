FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN groupadd --system atlas && useradd --system --gid atlas atlas
COPY pyproject.toml ./
COPY atlas_api ./atlas_api
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .

USER atlas
EXPOSE 8790
CMD ["uvicorn", "atlas_api.main:app", "--host", "0.0.0.0", "--port", "8790"]

