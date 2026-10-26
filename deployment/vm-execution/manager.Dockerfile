# Build only in the isolated image-preparation stage. All arguments are mandatory pins.
ARG DEBIAN_BASE
FROM ${DEBIAN_BASE}
ARG DEBIAN_BASE
ARG DEBIAN_SNAPSHOT
ARG QEMU_PACKAGE_VERSION
ARG FIRMWARE_PACKAGE_VERSION
ARG CLOUD_UTILS_PACKAGE_VERSION
ARG PYTHON_PACKAGE_VERSION
RUN printf '%s' "$DEBIAN_BASE" | grep -Eq '@sha256:[a-f0-9]{64}$' \
 && printf '%s' "$DEBIAN_SNAPSHOT" | grep -Eq '^[0-9]{8}T[0-9]{6}Z$' \
 && test -n "$DEBIAN_SNAPSHOT" && test -n "$QEMU_PACKAGE_VERSION" && test -n "$FIRMWARE_PACKAGE_VERSION" && test -n "$CLOUD_UTILS_PACKAGE_VERSION" && test -n "$PYTHON_PACKAGE_VERSION" \
 && rm -f /etc/apt/sources.list.d/debian.sources \
 && printf 'deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/%s/ trixie main\n' "$DEBIAN_SNAPSHOT" > /etc/apt/sources.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends "qemu-system-arm=$QEMU_PACKAGE_VERSION" "qemu-utils=$QEMU_PACKAGE_VERSION" "qemu-efi-aarch64=$FIRMWARE_PACKAGE_VERSION" "cloud-image-utils=$CLOUD_UTILS_PACKAGE_VERSION" "python3=$PYTHON_PACKAGE_VERSION" \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir /opt/sduoj-vm \
 && dpkg-query -W > /opt/sduoj-vm/packages.lock
COPY manager.py vmctl.py source.lock.json /opt/sduoj-vm/
USER 10001:10001
ENTRYPOINT ["python3", "/opt/sduoj-vm/manager.py"]
CMD ["plan"]
