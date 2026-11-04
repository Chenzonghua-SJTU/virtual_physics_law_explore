ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url ${PIP_INDEX_URL} numpy==2.0.2 scipy==1.13.1 sympy==1.13.3 matplotlib==3.9.4
COPY runner.py /opt/shore/runner.py
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg PYTHONDONTWRITEBYTECODE=1
WORKDIR /work
USER 65534:65534
ENTRYPOINT ["python", "-I", "/opt/shore/runner.py"]
