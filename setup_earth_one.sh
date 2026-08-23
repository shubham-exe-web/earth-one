#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CFG_DIR="$HOME/.config/earth_one"
ENV_FILE="$CFG_DIR/earth_one.env"

mkdir -p "$CFG_DIR"
chmod 700 "$CFG_DIR"

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --upgrade pip
"$ROOT/.venv/bin/pip" install -e "$ROOT"

if [ ! -f "$ENV_FILE" ]; then
  echo "Earth One one-time configuration"
  echo "Secrets are stored only in: $ENV_FILE"
  echo

  read -r -p "CDSE Client ID: " CDSE_ID
  read -r -s -p "CDSE Client Secret: " CDSE_SECRET
  echo
  read -r -p "SMTP Host (e.g. smtp.gmail.com): " SMTP_HOST
  read -r -p "SMTP Port [465]: " SMTP_PORT
  SMTP_PORT="${SMTP_PORT:-465}"
  read -r -p "Alert email username: " SMTP_USER
  read -r -s -p "Alert email password/app password: " SMTP_PASS
  echo
  read -r -p "From email: " MAIL_FROM
  read -r -p "To email: " MAIL_TO

  cat > "$ENV_FILE" <<EOF
CDSE_CLIENT_ID="$CDSE_ID"
CDSE_CLIENT_SECRET="$CDSE_SECRET"
EARTH_ONE_SMTP_HOST="$SMTP_HOST"
EARTH_ONE_SMTP_PORT="$SMTP_PORT"
EARTH_ONE_SMTP_USERNAME="$SMTP_USER"
EARTH_ONE_SMTP_PASSWORD="$SMTP_PASS"
EARTH_ONE_ALERT_FROM="$MAIL_FROM"
EARTH_ONE_ALERT_TO="$MAIL_TO"
EOF
  chmod 600 "$ENV_FILE"
fi

echo
echo "Environment:"
"$ROOT/.venv/bin/earth-one" config-status

echo
echo "Setup complete."
