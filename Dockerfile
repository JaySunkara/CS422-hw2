FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-matplotlib ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY *.py servers.csv ./
ENTRYPOINT ["python3", "experiment.py"]
