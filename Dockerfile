# Agentic Deep Research System - Dockerfile (Backend)

FROM eclipse-temurin:17-jdk-jammy AS source-figure-build
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
RUN git init && git remote add origin https://github.com/allenai/pdffigures2.git \
    && git fetch --depth 1 origin 3d7ad46753d4a315cccd1c2bcab398380e88c534 \
    && git checkout --detach FETCH_HEAD
COPY resources/pdffigures2/build.sbt ./build.sbt
COPY resources/pdffigures2/plugins.sbt ./project/plugins.sbt
RUN curl -fsSL https://repo.maven.apache.org/maven2/org/scala-sbt/sbt-launch/1.7.1/sbt-launch-1.7.1.jar -o /opt/sbt-launch.jar \
    && java -Dsbt.supershell=false -jar /opt/sbt-launch.jar assembly

FROM eclipse-temurin:17-jre-jammy AS source-figure-runtime

FROM python:3.11-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PIP_DEFAULT_TIMEOUT=300
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="/opt/java/openjdk/bin:${PATH}"
COPY --from=source-figure-runtime /opt/java/openjdk /opt/java/openjdk

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    fonts-noto-cjk \
    libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.6.0+cpu
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps chromium

# Copy application code
COPY app/ ./app/
COPY config/ ./config/
COPY resources/research-skills/bookshelf/ ./resources/research-skills/bookshelf/
COPY --from=source-figure-build /build/pdffigures2.jar ./resources/pdffigures2/pdffigures2.jar
COPY --from=source-figure-build /build/LICENSE.txt ./resources/pdffigures2/LICENSE.txt
COPY docs/SPEC.md ./docs/SPEC.md
COPY README.md .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
