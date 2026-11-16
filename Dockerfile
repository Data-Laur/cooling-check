# Cooling Check web app.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt
COPY pipeline.py ./
COPY app/ ./app/
COPY samples/ ./samples/
ENV PORT=8000
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
