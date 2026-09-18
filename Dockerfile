FROM python:3.12-slim
WORKDIR /service
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY pyproject.toml ./
# One process is essential: each worker would own a different pool.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-config", "app/logging.json"]
