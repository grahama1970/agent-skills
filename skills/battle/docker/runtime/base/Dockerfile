FROM debian:bookworm-slim

LABEL org.opencontainers.image.title="battle-base"
LABEL org.opencontainers.image.description="Minimal Battle target runtime foundation with non-root execution and receipt utilities"
LABEL org.opencontainers.image.vendor="agent-skills battle"
LABEL org.opencontainers.image.version="2026.06.30"

ENV DEBIAN_FRONTEND=noninteractive
ENV BATTLE_RUNTIME_IMAGE_ID=battle-base
ENV BATTLE_RUNTIME_VERSION=2026.06.30
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        apache2-utils \
        bash \
        ca-certificates \
        coreutils \
        curl \
        dnsmasq-base \
        dnsutils \
        dosfstools \
        exfatprogs \
        file \
        findutils \
        gawk \
        grep \
        hping3 \
        hostapd \
        gzip \
        iptables \
        iproute2 \
        iw \
        jq \
        mtools \
        netcat-openbsd \
        nftables \
        nmap \
        parted \
        procps \
        rfkill \
        sed \
        socat \
        tar \
        tcpdump \
        tini \
        traceroute \
        udev \
        unzip \
        util-linux \
        usbutils \
        wireless-tools \
        wpasupplicant \
        xz-utils \
        zip \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 battle \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash battle \
    && mkdir -p /workspace /battle/artifacts \
    && chown -R battle:battle /workspace /battle /home/battle

COPY battle-runtime-info /usr/local/bin/battle-runtime-info
COPY battle-http-junk /usr/local/bin/battle-http-junk
RUN chmod 0755 /usr/local/bin/battle-runtime-info /usr/local/bin/battle-http-junk

WORKDIR /workspace
USER 1000:1000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["battle-runtime-info"]
