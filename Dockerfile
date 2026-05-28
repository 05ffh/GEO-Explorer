FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
# COPY alembic.ini ./      # Added in Task 1.3
# COPY alembic/ ./alembic/  # Added in Task 1.3
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
