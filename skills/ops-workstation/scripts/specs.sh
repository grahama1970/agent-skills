#!/usr/bin/env bash
# Display comprehensive workstation specifications and documentation.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Display comprehensive workstation hardware and software specifications.
Includes hardware upgrade procedures and file organization.

Options:
  --hardware         Show hardware specs only
  --software         Show installed software only
  --storage          Show storage layout and organization
  --procedures       Show hardware upgrade procedures
  --all              Show everything (default)
  --json             Output as JSON
  --help             Show this message

Examples:
  $(basename "$0")                  # Full workstation documentation
  $(basename "$0") --storage        # Just storage info
  $(basename "$0") --procedures     # How to upgrade hardware
USAGE
}

SECTION="all"
OUTPUT_FORMAT="markdown"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hardware) SECTION="hardware"; shift;;
    --software) SECTION="software"; shift;;
    --storage) SECTION="storage"; shift;;
    --procedures) SECTION="procedures"; shift;;
    --all) SECTION="all"; shift;;
    --json) OUTPUT_FORMAT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

# =============================================================================
# Hardware Specs
# =============================================================================
show_hardware() {
  echo "## Hardware Specifications"
  echo ""

  # CPU
  local cpu_model cpu_cores cpu_threads
  cpu_model=$(lscpu 2>/dev/null | grep "Model name" | cut -d: -f2 | xargs)
  cpu_cores=$(lscpu 2>/dev/null | grep "^Core(s) per socket" | cut -d: -f2 | xargs)
  cpu_threads=$(nproc 2>/dev/null)

  echo "### CPU"
  echo ""
  echo "| Spec | Value |"
  echo "|------|-------|"
  echo "| Model | $cpu_model |"
  echo "| Cores | $cpu_cores |"
  echo "| Threads | $cpu_threads |"
  echo "| Architecture | x86_64 |"
  echo ""

  # RAM
  local ram_total ram_speed
  ram_total=$(grep MemTotal /proc/meminfo | awk '{printf "%.0f GB", $2/1024/1024}')
  ram_speed=$(dmidecode -t memory 2>/dev/null | grep "Speed:" | grep -v Unknown | head -1 | cut -d: -f2 | xargs || echo "Unknown")

  echo "### Memory"
  echo ""
  echo "| Spec | Value |"
  echo "|------|-------|"
  echo "| Total RAM | $ram_total |"
  echo "| Speed | $ram_speed |"
  echo ""

  # GPU
  if command -v nvidia-smi &>/dev/null; then
    echo "### GPU"
    echo ""
    nvidia-smi --query-gpu=name,memory.total,driver_version,pcie.link.gen.current --format=csv,noheader 2>/dev/null | \
    while IFS=',' read -r name mem driver pcie; do
      echo "| Spec | Value |"
      echo "|------|-------|"
      echo "| Model | $(echo "$name" | xargs) |"
      echo "| VRAM | $(echo "$mem" | xargs) |"
      echo "| Driver | $(echo "$driver" | xargs) |"
      echo "| PCIe Gen | $(echo "$pcie" | xargs) |"
    done
    echo ""
  fi

  # Motherboard
  echo "### Motherboard"
  echo ""
  echo "| Spec | Value |"
  echo "|------|-------|"
  local mb_vendor mb_product
  mb_vendor=$(cat /sys/class/dmi/id/board_vendor 2>/dev/null || echo "Unknown")
  mb_product=$(cat /sys/class/dmi/id/board_name 2>/dev/null || echo "Unknown")
  echo "| Vendor | $mb_vendor |"
  echo "| Model | $mb_product |"
  echo "| Chipset | AMD TRX40 |"
  echo ""
}

# =============================================================================
# Storage Layout
# =============================================================================
show_storage() {
  echo "## Storage Layout"
  echo ""

  echo "### Physical Drives"
  echo ""
  echo "| Device | Size | Model | Mount | Purpose |"
  echo "|--------|------|-------|-------|---------|"

  lsblk -o NAME,SIZE,MODEL,MOUNTPOINT -d 2>/dev/null | grep -vE "^loop|^NAME" | while read -r name size model mount; do
    case "$name" in
      nvme0n1)
        echo "| /dev/$name | $size | $model | / | **Boot/OS Drive** (WD Black SN850X) |"
        ;;
      nvme1n1)
        echo "| /dev/$name | $size | $model | (Windows) | Secondary NVMe (Samsung 980 PRO) |"
        ;;
      sda)
        echo "| /dev/$name | $size | $model | /mnt/storage12tb | **Bulk Storage** (media, backups) |"
        ;;
      sdb)
        echo "| /dev/$name | $size | $model | /mnt/exnvme | External NVMe enclosure |"
        ;;
    esac
  done
  echo ""

  echo "### NVMe Slot Configuration"
  echo ""
  echo "| Slot | Current Drive | Speed | Notes |"
  echo "|------|---------------|-------|-------|"
  echo "| M.2 Slot 1 (CPU lanes) | WD Black SN850X 4TB | PCIe 4.0 x4 | Primary boot drive |"
  echo "| M.2 Slot 2 (Chipset) | Samsung 980 PRO 2TB | PCIe 4.0 x4 | Windows/dual boot |"
  echo ""

  echo "### SATA Ports"
  echo ""
  echo "| Port | Device | Purpose |"
  echo "|------|--------|---------|"
  echo "| SATA 0 | Seagate IronWolf 12TB | Bulk storage |"
  echo "| SATA 1-7 | Available | Future expansion |"
  echo ""

  echo "### Mount Points"
  echo ""
  df -h 2>/dev/null | grep -E "^/dev/(sd|nvme)" | awk '{print "| " $6 " | " $2 " | " $3 " | " $4 " | " $5 " |"}' | \
  (echo "| Mount | Size | Used | Free | Use% |"; echo "|-------|------|------|------|------|"; cat)
  echo ""
}

# =============================================================================
# Software Configuration
# =============================================================================
show_software() {
  echo "## Software Configuration"
  echo ""

  # OS
  echo "### Operating System"
  echo ""
  echo "| Component | Version |"
  echo "|-----------|---------|"
  echo "| OS | $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"') |"
  echo "| Kernel | $(uname -r) |"
  echo "| Desktop | KDE Plasma $(plasmashell --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+') |"
  echo ""

  # Key packages
  echo "### Key Installed Software"
  echo ""
  echo "| Category | Software |"
  echo "|----------|----------|"
  echo "| Python | $(python3 --version 2>/dev/null) |"
  echo "| Node.js | $(node --version 2>/dev/null || echo "Not installed") |"
  echo "| Docker | $(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ',') |"
  echo "| Git | $(git --version | cut -d' ' -f3) |"
  echo "| CUDA | $(nvidia-smi 2>/dev/null | grep "CUDA" | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "N/A") |"
  echo "| Ollama | $(ollama --version 2>/dev/null | head -1 || echo "Not installed") |"
  echo ""

  # IDEs
  echo "### Development Tools"
  echo ""
  echo "| Tool | Status |"
  echo "|------|--------|"
  pgrep -x code >/dev/null && echo "| VS Code | Running |" || echo "| VS Code | Installed |"
  pgrep -f antigravity >/dev/null && echo "| Antigravity IDE | Running |" || echo "| Antigravity IDE | Installed |"
  pgrep -f cloudcode_cli >/dev/null && echo "| Cloud Code CLI | Running |" || echo "| Cloud Code CLI | Installed |"
  echo ""
}

# =============================================================================
# Hardware Upgrade Procedures
# =============================================================================
show_procedures() {
  echo "## Hardware Upgrade Procedures"
  echo ""

  echo "### Adding/Replacing NVMe SSD"
  echo ""
  echo "**Prerequisites:**"
  echo "- Backup important data"
  echo "- PCIe 4.0 NVMe drive (for full speed) or PCIe 3.0 (compatible)"
  echo "- Phillips screwdriver"
  echo ""
  echo "**Steps:**"
  echo ""
  echo "1. **Power off** and unplug the workstation"
  echo "2. **Ground yourself** (touch case metal)"
  echo "3. **Remove side panel** (thumb screws on back)"
  echo "4. **Locate M.2 slots** on motherboard (TRX40):"
  echo "   - Slot 1: Near CPU (best performance, CPU lanes)"
  echo "   - Slot 2: Below GPU area (chipset lanes)"
  echo "5. **Remove heatsink** (if present) by unscrewing"
  echo "6. **Insert NVMe at 30° angle**, press down, secure with screw"
  echo "7. **Replace heatsink**, close case, boot"
  echo "8. **Partition and mount:**"
  echo "   \`\`\`bash"
  echo "   sudo fdisk /dev/nvmeXn1  # Create partition"
  echo "   sudo mkfs.ext4 /dev/nvmeXn1p1  # Format"
  echo "   sudo mkdir /mnt/newdrive"
  echo "   sudo mount /dev/nvmeXn1p1 /mnt/newdrive"
  echo "   # Add to /etc/fstab for persistence"
  echo "   \`\`\`"
  echo ""

  echo "### Adding SATA Hard Drive"
  echo ""
  echo "**Steps:**"
  echo ""
  echo "1. **Power off** and unplug"
  echo "2. **Mount drive** in available bay (tool-less or screw mount)"
  echo "3. **Connect SATA data cable** to motherboard (ports 0-7)"
  echo "4. **Connect SATA power** from PSU"
  echo "5. **Boot and partition:**"
  echo "   \`\`\`bash"
  echo "   sudo fdisk /dev/sdX  # Create partition"
  echo "   sudo mkfs.ext4 /dev/sdX1  # Format"
  echo "   sudo mount /dev/sdX1 /mnt/storage"
  echo "   \`\`\`"
  echo ""

  echo "### Adding RAM"
  echo ""
  echo "**Current:** ~256GB DDR4 (check slots)"
  echo "**Max supported:** Depends on motherboard (typically 256GB for TRX40)"
  echo ""
  echo "**Steps:**"
  echo ""
  echo "1. **Check current slots:** \`sudo dmidecode -t memory | grep Size\`"
  echo "2. **Buy matching RAM** (DDR4, same speed preferred)"
  echo "3. **Power off**, open case"
  echo "4. **Release clips** on RAM slots, insert at angle, press until click"
  echo "5. **Boot** - system should auto-detect"
  echo ""

  echo "### GPU Upgrade"
  echo ""
  echo "**Current:** NVIDIA RTX A5000 (24GB)"
  echo "**PCIe slot:** x16 Gen 4"
  echo ""
  echo "**Steps:**"
  echo ""
  echo "1. **Uninstall old drivers:** \`sudo apt remove --purge nvidia-*\`"
  echo "2. **Power off**, remove power cables"
  echo "3. **Release PCIe latch**, remove old GPU"
  echo "4. **Insert new GPU**, connect power cables"
  echo "5. **Install drivers:**"
  echo "   \`\`\`bash"
  echo "   sudo ubuntu-drivers autoinstall"
  echo "   # Or specific version:"
  echo "   sudo apt install nvidia-driver-550"
  echo "   \`\`\`"
  echo ""
}

# =============================================================================
# File Organization
# =============================================================================
show_file_organization() {
  echo "## File Organization"
  echo ""

  echo "### Home Directory (/home/graham)"
  echo ""
  echo "| Directory | Purpose |"
  echo "|-----------|---------|"
  echo "| workspace/ | All code projects |"
  echo "| .claude/ | Claude Code configuration |"
  echo "| .pi/ | Pi agent skills and config |"
  echo "| .cache/ | Application caches |"
  echo "| .local/ | User applications and data |"
  echo ""

  echo "### Workspace Structure (/home/graham/workspace)"
  echo ""
  echo "| Directory | Purpose |"
  echo "|-----------|---------|"
  echo "| experiments/ | Research and experimental projects |"
  echo "| experiments/pi-mono | Main monorepo with AI skills |"
  echo "| experiments/devops | DevOps scripts and infrastructure |"
  echo "| streamdeck | Stream Deck automation |"
  echo ""

  echo "### Bulk Storage (/mnt/storage12tb)"
  echo ""
  echo "| Directory | Purpose |"
  echo "|-----------|---------|"
  echo "| media/ | Movies, TV shows, audiobooks |"
  echo "| backups/ | System and project backups |"
  echo "| datasets/ | ML training datasets |"
  echo "| models/ | Downloaded ML models |"
  echo ""

  echo "### Key Configuration Locations"
  echo ""
  echo "| Path | Purpose |"
  echo "|------|---------|"
  echo "| ~/.claude/ | Claude Code projects and settings |"
  echo "| ~/.pi/ | Pi agent configuration |"
  echo "| ~/.config/Code/ | VS Code settings |"
  echo "| ~/.local/share/antigravity/ | Antigravity IDE data |"
  echo "| /etc/systemd/system/ | System services |"
  echo "| ~/.config/systemd/user/ | User services |"
  echo ""
}

# =============================================================================
# Main Output
# =============================================================================
output_markdown() {
  echo "# Workstation Documentation"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo "**Hostname:** $(hostname)"
  echo ""

  case "$SECTION" in
    hardware)
      show_hardware
      ;;
    software)
      show_software
      ;;
    storage)
      show_storage
      ;;
    procedures)
      show_procedures
      ;;
    all)
      show_hardware
      show_storage
      show_software
      show_file_organization
      show_procedures
      ;;
  esac
}

# Main
if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  echo "JSON output not yet implemented for specs"
  exit 1
else
  output_markdown
fi
