# A deliberately small image used only to execute repository tests in isolation.
FROM python:3.11-slim

# pytest is installed in the image; a production deployment needs a controlled
# dependency-preparation step before test execution.
RUN pip install --no-cache-dir pytest==8.3.3 ruff==0.8.1
WORKDIR /workspace
CMD ["python", "-m", "pytest", "-q"]
