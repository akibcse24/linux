#!/bin/sh

set -eu

export DEBIAN_FRONTEND=noninteractive
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

AI_USER="ai"
AI_GROUP="ai"
AI_HOME="/home/${AI_USER}"
NEURALCORE_HOME="/opt/neuralcore"
PYTHON_VENV="${NEURALCORE_HOME}/venvs/ai-stack"

if ! getent group "${AI_GROUP}" >/dev/null 2>&1; then
  groupadd --system "${AI_GROUP}"
fi

if ! id "${AI_USER}" >/dev/null 2>&1; then
  useradd --create-home --home-dir "${AI_HOME}" --shell /bin/bash --gid "${AI_GROUP}" "${AI_USER}"
fi

usermod -aG sudo "${AI_USER}" || true

install -d -m 0755 "${NEURALCORE_HOME}" "${NEURALCORE_HOME}/models" "${NEURALCORE_HOME}/venvs"
install -d -m 0755 "${AI_HOME}/.config/Code/User" "${AI_HOME}/.config/openbox" "${AI_HOME}/.local/share/applications"
chown -R "${AI_USER}:${AI_GROUP}" "${AI_HOME}"

apt-get update
apt-get install -y --no-install-recommends python3-venv python3-pip python3-dev python3-full build-essential curl wget jq gnupg gpg ca-certificates libc-bin

if [ ! -d "${PYTHON_VENV}" ]; then
  python3 -m venv "${PYTHON_VENV}"
fi

"${PYTHON_VENV}/bin/pip" install --upgrade pip setuptools wheel
"${PYTHON_VENV}/bin/pip" install --no-cache-dir jupyterlab ipykernel numpy pandas scikit-learn lmstudio
"${PYTHON_VENV}/bin/pip" install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
"${PYTHON_VENV}/bin/pip" install --no-cache-dir tensorflow-cpu

if ! command -v ldconfig >/dev/null 2>&1; then
  apt-get install -y --no-install-recommends libc-bin
fi

# Ollama's installer may return non-zero in chroot/CI when systemd is unavailable.
# Keep the build green if the binary was installed successfully.
if ! curl -fsSL https://ollama.com/install.sh | sh; then
  if command -v ollama >/dev/null 2>&1; then
    echo "WARNING: Ollama installer returned non-zero, but ollama is installed. Continuing."
  else
    echo "ERROR: Ollama installation failed and binary is missing."
    exit 1
  fi
fi

su - "${AI_USER}" -c 'curl -fsSL https://lmstudio.ai/install.sh | bash'

install -d -m 0755 /etc/apt/keyrings /etc/apt/sources.list.d
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor >/etc/apt/keyrings/microsoft.gpg
chmod 0644 /etc/apt/keyrings/microsoft.gpg
printf '%s\n' 'deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/repos/code stable main' >/etc/apt/sources.list.d/vscode.list

apt-get update
apt-get install -y code

su - "${AI_USER}" -c 'code --install-extension ms-python.python --force' || true
su - "${AI_USER}" -c 'code --install-extension ms-python.vscode-pylance --force' || true
su - "${AI_USER}" -c 'code --install-extension ms-toolsai.jupyter --force' || true
su - "${AI_USER}" -c 'code --install-extension Continue.continue --force' || true
su - "${AI_USER}" -c 'code --install-extension github.copilot --force' || true
su - "${AI_USER}" -c 'code --install-extension github.copilot-chat --force' || true


cat >/etc/profile.d/neuralcore.sh <<'EOF'
export NEURALCORE_HOME=/opt/neuralcore
export PATH="/opt/neuralcore/venvs/ai-stack/bin:$PATH"
export OLLAMA_HOST=http://127.0.0.1:11434
EOF

cat >"${AI_HOME}/.config/Code/User/settings.json" <<EOF
{
  "python.defaultInterpreterPath": "${PYTHON_VENV}/bin/python",
  "python.terminal.activateEnvironment": true,
  "jupyter.jupyterServerType": "local",
  "terminal.integrated.defaultProfile.linux": "bash"
}
EOF

install -d -m 0755 /etc/sudoers.d
cat >/etc/sudoers.d/010-ai-nopasswd <<EOF
${AI_USER} ALL=(ALL) NOPASSWD:ALL
EOF
chmod 0440 /etc/sudoers.d/010-ai-nopasswd

if command -v systemctl >/dev/null 2>&1; then
  for service_name in ai-assistant.service ollama.service; do
    if [ -f "/etc/systemd/system/${service_name}" ] || [ -f "/lib/systemd/system/${service_name}" ] || [ -f "/usr/lib/systemd/system/${service_name}" ]; then
      systemctl --root=/ enable "${service_name}" >/dev/null 2>&1 || true
    fi
  done
fi

chown -R "${AI_USER}:${AI_GROUP}" "${AI_HOME}"