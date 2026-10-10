FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN chmod +x docker-entrypoint.sh && useradd -m scout && chown -R scout /app
USER scout
EXPOSE 8000
# start-period: при первом старте генерируются демо-данные (1–3 минуты), в это время проверки не считаются
HEALTHCHECK --interval=10s --timeout=3s --retries=6 --start-period=600s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/v1/health')"
ENTRYPOINT ["./docker-entrypoint.sh"]
