FROM python:3.12-slim-bookworm

# The build script exports the selected target's uv.lock into this minimal context.
# Neither the source repository nor any environment files are sent to docker build.
COPY requirements.txt /opt/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /opt/requirements.txt \
    && python -c "import pytest,pytest_jsonreport; assert pytest.__version__ == '9.0.2'" \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --no-create-home sandbox
COPY herta_pytest_report.py /opt/herta_pytest_report.py
ENV PYTHONPATH=/opt:/workspace:/workspace/backend \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
    HERTA_SANDBOX=1 \
    HOME=/tmp
USER 10001:10001
WORKDIR /workspace
