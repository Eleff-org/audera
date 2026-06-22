FROM debian:trixie-slim

ARG CDSP_VERSION=3.0.1
ARG CDSP_ARCH=x86_64

RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL \
    "https://github.com/HEnquist/camilladsp/releases/download/v${CDSP_VERSION}/camilladsp-linux-${CDSP_ARCH}.tar.gz" \
    | tar -xz -C /usr/local/bin

COPY config.yml /etc/camilladsp/config.yml

EXPOSE 1234

CMD ["camilladsp", "-p", "1234", "/etc/camilladsp/config.yml"]
