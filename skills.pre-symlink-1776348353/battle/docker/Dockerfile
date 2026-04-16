# Battle QEMU Twin - Containerized QEMU for Red vs Blue firmware battles
# Based on dogpile research: QEMU inside Docker for reproducible digital twins
#
# Supports multiple architectures:
# - ARM (Cortex-M, Cortex-A)
# - RISC-V
# - x86/x86_64
# - MIPS
#
# Usage:
#   docker build -t battle-qemu-twin .
#   docker run --rm -it -v /path/to/firmware:/firmware battle-qemu-twin

FROM ubuntu:24.04

LABEL maintainer="battle-skill"
LABEL description="QEMU digital twin for Red vs Blue firmware battles"

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install QEMU system emulators for multiple architectures
RUN apt-get update && apt-get install -y --no-install-recommends \
    # QEMU system emulators
    qemu-system-arm \
    qemu-system-aarch64 \
    qemu-system-x86 \
    qemu-system-riscv64 \
    qemu-system-mips \
    qemu-system-misc \
    # QEMU utilities
    qemu-utils \
    # User-mode emulation (for fast binary fuzzing)
    qemu-user-static \
    # GDB for debugging
    gdb \
    gdb-multiarch \
    # Networking tools
    iproute2 \
    iputils-ping \
    netcat-openbsd \
    # Python for battle orchestration
    python3 \
    python3-pip \
    # Utilities
    ca-certificates \
    curl \
    file \
    binutils \
    && rm -rf /var/lib/apt/lists/*

# Install AFL++ for fuzzing (Red Team fuzzing capabilities)
RUN apt-get update && apt-get install -y --no-install-recommends \
    afl++ \
    && rm -rf /var/lib/apt/lists/*

# Create directories for battle operations
RUN mkdir -p /battle/firmware /battle/snapshots /battle/corpus /battle/crashes

# Set working directory
WORKDIR /battle

# Create helper scripts
RUN cat > /usr/local/bin/battle-gdb << 'EOF'
#!/bin/bash
# Connect GDB to QEMU stub
# Usage: battle-gdb <port> [symbol-file]
PORT=${1:-1234}
SYMBOLS=${2:-}
if [ -n "$SYMBOLS" ]; then
    gdb-multiarch -ex "target remote localhost:$PORT" -ex "file $SYMBOLS"
else
    gdb-multiarch -ex "target remote localhost:$PORT"
fi
EOF
RUN chmod +x /usr/local/bin/battle-gdb

RUN cat > /usr/local/bin/battle-qemu << 'EOF'
#!/bin/bash
# Start QEMU with battle-friendly defaults
# Usage: battle-qemu <arch> <firmware> [extra-args...]
#
# Examples:
#   battle-qemu arm firmware.bin
#   battle-qemu riscv64 firmware.elf -m 256M
#   battle-qemu x86_64 bios.rom --gdb 1234

ARCH=$1
FIRMWARE=$2
shift 2

GDB_PORT=${GDB_PORT:-1234}
MEMORY=${MEMORY:-64M}
SNAPSHOT_DIR=${SNAPSHOT_DIR:-/battle/snapshots}

case "$ARCH" in
    arm|ARM)
        QEMU="qemu-system-arm"
        MACHINE="virt"
        CPU="cortex-a15"
        KERNEL_OPT="-kernel"
        ;;
    aarch64|arm64|ARM64)
        QEMU="qemu-system-aarch64"
        MACHINE="virt"
        CPU="cortex-a53"
        KERNEL_OPT="-kernel"
        ;;
    riscv64|RISCV64)
        QEMU="qemu-system-riscv64"
        MACHINE="virt"
        CPU="rv64"
        KERNEL_OPT="-kernel"
        ;;
    x86|i386|x86_64)
        QEMU="qemu-system-x86_64"
        MACHINE="q35"
        CPU="qemu64"
        KERNEL_OPT="-bios"
        ;;
    mips|MIPS)
        QEMU="qemu-system-mips"
        MACHINE="malta"
        CPU="24Kc"
        KERNEL_OPT="-kernel"
        ;;
    *)
        echo "Unknown architecture: $ARCH"
        echo "Supported: arm, aarch64, riscv64, x86_64, mips"
        exit 1
        ;;
esac

echo "Starting $QEMU for $ARCH..."
echo "  Machine: $MACHINE"
echo "  CPU: $CPU"
echo "  Memory: $MEMORY"
echo "  GDB port: $GDB_PORT"
echo "  Firmware: $FIRMWARE"

exec $QEMU \
    -M $MACHINE \
    -cpu $CPU \
    -m $MEMORY \
    -nographic \
    -S \
    -gdb tcp::$GDB_PORT \
    $KERNEL_OPT "$FIRMWARE" \
    "$@"
EOF
RUN chmod +x /usr/local/bin/battle-qemu

RUN cat > /usr/local/bin/battle-snapshot << 'EOF'
#!/bin/bash
# Manage QEMU snapshots via QMP
# Usage: battle-snapshot <save|load|list> <name> [qmp-socket]
#
# Examples:
#   battle-snapshot save golden /tmp/qmp.sock
#   battle-snapshot load golden /tmp/qmp.sock
#   battle-snapshot list /tmp/qmp.sock

ACTION=$1
NAME=$2
QMP_SOCKET=${3:-/tmp/qmp.sock}

case "$ACTION" in
    save)
        echo '{"execute": "human-monitor-command", "arguments": {"command-line": "savevm '"$NAME"'"}}' | \
            nc -U "$QMP_SOCKET"
        echo "Snapshot '$NAME' saved"
        ;;
    load)
        echo '{"execute": "human-monitor-command", "arguments": {"command-line": "loadvm '"$NAME"'"}}' | \
            nc -U "$QMP_SOCKET"
        echo "Snapshot '$NAME' loaded"
        ;;
    list)
        echo '{"execute": "human-monitor-command", "arguments": {"command-line": "info snapshots"}}' | \
            nc -U "$QMP_SOCKET"
        ;;
    *)
        echo "Usage: battle-snapshot <save|load|list> <name> [qmp-socket]"
        exit 1
        ;;
esac
EOF
RUN chmod +x /usr/local/bin/battle-snapshot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD qemu-system-arm --version || exit 1

# Default command shows help
CMD ["bash", "-c", "echo 'Battle QEMU Twin Ready'; echo ''; echo 'Commands:'; echo '  battle-qemu <arch> <firmware>  - Start QEMU emulation'; echo '  battle-gdb <port> [symbols]    - Connect GDB'; echo '  battle-snapshot <action> <name> - Manage snapshots'; echo ''; echo 'Supported architectures: arm, aarch64, riscv64, x86_64, mips'; bash"]
