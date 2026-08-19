FROM python:3.12-slim

WORKDIR /app

COPY apps/api/pyproject.toml ./pyproject.toml
RUN pip install --no-cache-dir \
    fastapi==0.141.1 \
    uvicorn==0.52.1 \
    openpyxl==3.1.5

COPY apps/api/app ./app

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
