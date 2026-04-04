FROM python:3.12-slim

RUN groupadd -r chutes && useradd -r -g chutes -m chutes

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py client.py backends.yml ./

USER chutes

EXPOSE 8630

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8630", "--log-level", "info"]
