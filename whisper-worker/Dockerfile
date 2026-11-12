FROM python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ./app.py
EXPOSE 8791
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8791"]
