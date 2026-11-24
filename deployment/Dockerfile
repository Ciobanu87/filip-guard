FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    FG_CUSTOMER_AUTH_DB=/var/lib/filip-guard/accounts.sqlite \
    FG_CUSTOMER_DATA_ROOT=/var/lib/filip-guard/workspaces \
    FG_MONITOR_DB=/var/lib/filip-guard/monitor.sqlite \
    FG_AI_LEDGER_DB=/var/lib/filip-guard/advisor.sqlite
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin guard \
    && mkdir -p /var/lib/filip-guard \
    && chown 10001:10001 /var/lib/filip-guard \
    && chmod 0700 /var/lib/filip-guard
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install -r requirements.txt
COPY . .
USER 10001:10001
VOLUME ["/var/lib/filip-guard"]
EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=2).read()"
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
