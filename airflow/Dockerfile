FROM apache/airflow:2.10.5-python3.11

ARG AIRFLOW_VERSION=2.10.5
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
