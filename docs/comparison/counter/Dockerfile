FROM python:3.13-alpine@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc
RUN pip install --no-cache-dir requests==2.32.5
EXPOSE 7001 7002
ENTRYPOINT ["python", "/proxy.py"]
