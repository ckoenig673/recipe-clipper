FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./app.py
EXPOSE 8791
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8791"]
