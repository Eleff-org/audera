FROM debian:trixie-slim

ARG CDSP_VERSION=3.0.1
ARG CDSP_ARCH=amd64

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q "https://github.com/HEnquist/camilladsp/releases/download/v${CDSP_VERSION}/camilladsp-linux-${CDSP_ARCH}.tar.gz" \
        -O /tmp/camilladsp.tar.gz \
    && tar -xzf /tmp/camilladsp.tar.gz -C /usr/local/bin \
    && chmod +x /usr/local/bin/camilladsp \
    && rm /tmp/camilladsp.tar.gz

COPY config.yml /etc/camilladsp/config.yml

EXPOSE 1234

CMD ["camilladsp", "-p", "1234", "/etc/camilladsp/config.yml"]
