FROM python:3.12-slim

WORKDIR /app

# Install minimal deps for the service
RUN pip install --no-cache-dir fastapi uvicorn loguru pydantic

COPY service.py .

EXPOSE 8787

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8787"]
