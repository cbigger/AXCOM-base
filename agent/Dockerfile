FROM python:3.13-slim

WORKDIR /agent

COPY agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY controller/openrouter_kdr.py .
COPY agent/entrypoint.py .

ENTRYPOINT ["python", "-u", "entrypoint.py"]
