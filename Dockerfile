FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY create_faas.html .

EXPOSE 5000

CMD ["gunicorn", "--timeout", "180","--bind", "0.0.0.0:5000", "app:app"]