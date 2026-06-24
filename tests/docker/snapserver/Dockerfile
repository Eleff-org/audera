FROM debian:bookworm-slim

RUN echo 'deb http://deb.debian.org/debian bookworm-backports main' >> /etc/apt/sources.list \
    && apt-get update -qq \
    && DEBIAN_FRONTEND=noninteractive apt-get install -t bookworm-backports -y \
       --no-install-recommends \
       -o Dpkg::Options::=--force-confold \
       snapserver snapclient \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 1780

ENTRYPOINT ["/entrypoint.sh"]
