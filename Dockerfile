FROM golang:1.25-bookworm AS build

ENV GO111MODULE=on

WORKDIR /build/gphotos-cdp

# Copy go.mod and go.sum first for better caching
COPY gphotos-cdp/go.mod gphotos-cdp/go.sum ./

# Download dependencies
RUN go mod download

# Copy the rest of the source code
COPY gphotos-cdp/ ./

# Build gphotos-cdp from local sources
# Update go.mod for new internal packages, then clean and rebuild
RUN go mod tidy && \
    go clean -cache -modcache -i -r && \
    go mod download && \
    go build -a -o /go/bin/gphotos-cdp .

FROM debian:bookworm-slim

ARG BUILD_DATE="unknown"
ARG IMAGE_VERSION="dev"

ENV \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CRON_SCHEDULE="0 0 * * *" \
    RESTART_SCHEDULE= \
    CHROME_PACKAGE=google-chrome-stable_current_amd64.deb \
    DEBIAN_FRONTEND=noninteractive \
    LOGLEVEL=INFO \
    HEALTHCHECK_HOST="https://hc-ping.com" \
    HEALTHCHECK_ID= \
    ALBUMS= \
    WORKER_COUNT=6 \
    GPHOTOS_CDP_ARGS= \
    RUN_ON_STARTUP=false \
    BUILD_DATE=${BUILD_DATE} \
    IMAGE_VERSION=${IMAGE_VERSION}

RUN apt-get update && apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        cron \
        exiftool \
        jq \
        wget \
        sudo \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        procps \
    --no-install-recommends && \
    wget https://dl.google.com/linux/direct/$CHROME_PACKAGE && \
    apt install -y ./$CHROME_PACKAGE && \
    rm ./$CHROME_PACKAGE && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /go/bin/gphotos-cdp /usr/bin/
COPY src ./app/
COPY --from=build /build/gphotos-cdp/months-config.json /app/
RUN chmod +x /app/*.sh

USER root
ENTRYPOINT ["/app/start.sh"]
CMD [""]
