# NeuralCore OS

NeuralCore OS is a Debian-based live Linux distribution built with `live-build` and `debootstrap` so it can be compiled reliably inside GitHub Actions containers.

The current repository is wired for a lightweight Openbox desktop with local AI tooling baked into the ISO:

- Ollama for local LLM inference
- LM Studio via its official Linux installer
- Python 3.12+ userland from Debian trixie
- PyTorch, TensorFlow, JupyterLab, and the LM Studio Python SDK in a dedicated virtual environment
- VS Code with AI-oriented extensions
- A local AI assistant daemon that exposes a safe, allowlisted command API

## Repository layout

- `.github/workflows/build-iso.yml` - Builds the ISO in GitHub Actions and publishes it to a release on tagged builds
- `live-build/auto/config` - Live-build configuration entrypoint
- `live-build/config/package-lists/ai-os.list.chroot` - Base package list for the ISO
- `live-build/config/hooks/normal/0100-ai-rootfs.hook.chroot` - Runs the AI rootfs bootstrap during the build
- `scripts/ai-rootfs.sh` - Installs and configures the AI stack inside the chroot

## Build flow

1. GitHub Actions restores package caches.
2. The workflow copies `scripts/ai-rootfs.sh` into the live-build chroot.
3. `live-build` creates a Debian trixie live ISO.
4. Tagged builds publish the final `.iso` as a GitHub Release asset.

## Notes

- Debian is the default base here because it fits the GitHub Actions container model better than an Arch `archiso` build.
- The AI assistant daemon is intentionally allowlisted; it can update packages, inspect files, and manage services, but it does not execute arbitrary shell input.
- For full publishing, push a version tag such as `v0.1.0`.