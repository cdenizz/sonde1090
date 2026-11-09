FROM python:3.11-alpine
WORKDIR /app
COPY sonde1090/ ./sonde1090/
CMD ["python", "-m", "sonde1090"]
