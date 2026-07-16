FROM python:3.12-slim

# Unbuffered stdout: otherwise Python block-buffers it when not a TTY, so log
# lines surface late and out of order relative to stderr (observed ~50s skew).
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
