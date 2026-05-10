#!/usr/bin/env bash
set -euo pipefail

APP_NAME="senseibox-kpi"
SERVICE_NAME="senseibox-kpi"
SERVICE_USER="senseibox"
SERVICE_GROUP="senseibox"
INSTALL_ROOT="/opt/senseibox"
INSTALL_DIR="${INSTALL_ROOT}/${APP_NAME}"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo: sudo ./install.sh" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but was not found." >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required but was not found." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

echo "Installing ${APP_NAME} into ${INSTALL_DIR}"

if ! getent group "${SERVICE_GROUP}" >/dev/null; then
  groupadd --system "${SERVICE_GROUP}"
fi

if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  useradd --system --home "${INSTALL_ROOT}" --shell /usr/sbin/nologin --gid "${SERVICE_GROUP}" "${SERVICE_USER}"
fi

install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" "${INSTALL_ROOT}"
install -d -o "${SERVICE_USER}" -g "${SERVICE_GROUP}" "${INSTALL_DIR}"

systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true

rsync -a --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".pytest_cache" \
  --exclude ".DS_Store" \
  "${SCRIPT_DIR}/" "${INSTALL_DIR}/"

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_ROOT}"

sudo -u "${SERVICE_USER}" python3 -m venv "${INSTALL_DIR}/.venv"
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u "${SERVICE_USER}" "${INSTALL_DIR}/.venv/bin/python" -m pip install -e "${INSTALL_DIR}"

install -m 0644 "${INSTALL_DIR}/systemd/${SERVICE_NAME}.service" "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "${APP_NAME} is installed."
systemctl --no-pager --full status "${SERVICE_NAME}"
