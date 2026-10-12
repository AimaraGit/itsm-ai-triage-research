# Reproducible CPU environment (exact pins)
FROM python:3.11.9-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Fail the build if the unit tests do not pass
RUN python -m unittest discover -s tests

CMD ["python", "-m", "src.benchmark", "--config", "configs/config.yaml"]
