FROM golang:1.25-bookworm AS build

ENV GO111MODULE=on

# Copy local gphotos-cdp source code
COPY gphotos-cdp /build/gphotos-cdp
WORKDIR /build/gphotos-cdp

# Build gphotos-cdp from local sources
RUN go build -o /go/bin/gphotos-cdp .

FROM debian:bookworm-slim

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
    RUN_ON_STARTUP=false

RUN apt-get update && apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        cron \
        exiftool \
        jq \
        wget \
        sudo \
    --no-install-recommends && \
    wget https://dl.google.com/linux/direct/$CHROME_PACKAGE && \
    apt install -y ./$CHROME_PACKAGE && \
    rm ./$CHROME_PACKAGE && \
    rm -rf /var/lib/apt/lists/*

COPY --from=build /go/bin/gphotos-cdp /usr/bin/
COPY src ./app/
RUN chmod +x /app/*.sh

USER root
ENTRYPOINT ["/app/start.sh"]
CMD [""]
