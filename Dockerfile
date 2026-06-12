FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "src/pipeline/run_full_pipeline.py", "--raw-dir", "data/raw", "--processed-dir", "data/processed", "--charts-dir", ".tmp/charts", "--dashboard-file", "outputs/dashboard/executive-marketplace-command-center.html", "--pages-dashboard-file", ".pages/executive-marketplace-command-center.html", "--pages-index-file", ".pages/index.html", "--monte-carlo-iterations", "2000", "--schema-file", "config/contracts/v1/schema_contracts.json", "--metric-contract-file", "config/contracts/v1/metric_governance_contract.csv", "--schema-history-dir", "config/contracts/history", "--reports-dir", "reports", "--required-release-state", "decision-support only"]
