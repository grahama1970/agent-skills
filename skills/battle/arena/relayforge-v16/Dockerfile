ARG RELAYFORGE_BASE_IMAGE
FROM ${RELAYFORGE_BASE_IMAGE}

WORKDIR /opt/relayforge
COPY service.py /opt/relayforge/service.py
COPY rf_a_reference.py /opt/relayforge/rf_a_reference.py
COPY rf_b_reference.py /opt/relayforge/rf_b_reference.py
COPY judge /opt/relayforge/judge

RUN mkdir -p \
      /var/lib/relayforge/sinks/rf-a \
      /var/lib/relayforge/sinks/rf-b \
      /var/lib/relayforge/sinks/rf-c \
      /var/lib/relayforge/state \
    && chown -R 65534:65534 /opt/relayforge /var/lib/relayforge

USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["python", "/opt/relayforge/service.py"]
