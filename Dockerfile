FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "src/pipeline/run_full_pipeline.py", "--raw-dir", "data/raw", "--processed-dir", "data/processed", "--charts-dir", "outputs/charts", "--dashboard-file", "outputs/dashboard/marketplace_command_center_dashboard.html", "--dashboard-demo-file", "outputs/dashboard/marketplace_command_center_dashboard_demo.html", "--dashboard-demo-max-orders", "25000", "--monte-carlo-iterations", "2000", "--schema-file", "schemas/v1/schema_contracts.json", "--reports-dir", "reports"]
