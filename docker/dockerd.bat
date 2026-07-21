@echo off
REM ─── Backend (3-layer build) ───
REM 1. Base image (Python + ODBC，Azure SQL 依赖，勿删)
REM docker build -f docker/Dockerfile-backend.base -t nexusrag-python-base:3.11 .
REM 2. Pip image (Python dependencies)
REM docker build -f docker/Dockerfile-backend.pip  -t nexusrag-python-pip:3.11 backend
REM 3. App image (application code)
docker build -f docker/Dockerfile-backend      -t nexusrag-api backend
docker tag nexusrag-api binyancontainerea.azurecr.io/nexusrag-api
docker push binyancontainerea.azurecr.io/nexusrag-api

REM ─── Frontend (ASP.NET + Vue) ───
REM docker build -f docker/Dockerfile-frontend.base -t nexusrag-frontend-base:10.0-node22 .
docker build -t nexusrag-server -f docker/Dockerfile-frontend frontend/NexusRAG
docker tag nexusrag-server binyancontainerea.azurecr.io/nexusrag-server
docker push binyancontainerea.azurecr.io/nexusrag-server
