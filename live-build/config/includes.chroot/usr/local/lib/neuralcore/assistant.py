#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest


HOST, PORT = os.getenv("NEURALCORE_ASSISTANT_BIND", "127.0.0.1:8811").rsplit(":", 1)
PORT = int(PORT)
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("NEURALCORE_ASSISTANT_MODEL", "llama3.1:8b")


def run_command(command: list[str]) -> dict[str, object]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout[-12000:],
        "stderr": completed.stderr[-12000:],
        "command": command,
    }


def ollama_intent(message: str) -> dict[str, object] | None:
    prompt = {
        "role": "system",
        "content": (
            "Return JSON only with keys action and arguments. "
            "Allowed actions are system_update, install_package, remove_package, list_files, disk_usage, system_info, show_services, restart_service, show_logs, unknown. "
            "For install_package and remove_package, arguments must contain packages as an array of package names. "
            "For list_files, arguments must contain path. For service actions, arguments must contain service."
        ),
    }
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [prompt, {"role": "user", "content": message}],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urlerror.URLError):
        return None

    try:
        content = result["message"]["content"]
        return json.loads(content)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def heuristic_intent(message: str) -> dict[str, object]:
    lowered = message.lower()

    if any(phrase in lowered for phrase in ["update the system", "system update", "upgrade packages", "full upgrade"]):
        return {"action": "system_update", "arguments": {}}

    if any(phrase in lowered for phrase in ["show disk", "disk usage", "filesystem usage"]):
        return {"action": "disk_usage", "arguments": {}}

    if any(phrase in lowered for phrase in ["show system info", "system info", "host info"]):
        return {"action": "system_info", "arguments": {}}

    service_match = re.search(r"(?:restart|show logs for|status of|show status of)\s+([a-z0-9_.@-]+)", lowered)
    if service_match:
        service_name = service_match.group(1)
        if lowered.startswith("restart"):
            return {"action": "restart_service", "arguments": {"service": service_name}}
        if "log" in lowered:
            return {"action": "show_logs", "arguments": {"service": service_name}}
        return {"action": "show_services", "arguments": {"service": service_name}}

    list_match = re.search(r"(?:list|show|open)\s+(?:files?\s+in\s+)?(?:the\s+)?(.+)$", message, re.IGNORECASE)
    if list_match:
        return {"action": "list_files", "arguments": {"path": list_match.group(1).strip()}}

    install_match = re.search(r"install\s+(.+)$", message, re.IGNORECASE)
    if install_match:
        packages = [name for name in re.split(r"[\s,]+", install_match.group(1).strip()) if re.match(r"^[A-Za-z0-9+._-]+$", name)]
        if packages:
            return {"action": "install_package", "arguments": {"packages": packages}}

    remove_match = re.search(r"remove\s+(.+)$", message, re.IGNORECASE)
    if remove_match:
        packages = [name for name in re.split(r"[\s,]+", remove_match.group(1).strip()) if re.match(r"^[A-Za-z0-9+._-]+$", name)]
        if packages:
            return {"action": "remove_package", "arguments": {"packages": packages}}

    return {"action": "unknown", "arguments": {"message": message}}


def execute_intent(intent: dict[str, object]) -> dict[str, object]:
    action = str(intent.get("action", "unknown"))
    arguments = intent.get("arguments") or {}

    if action == "system_update":
        return run_command(["/bin/sh", "-lc", "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get -y full-upgrade"])

    if action == "install_package":
        packages = arguments.get("packages", [])
        if not isinstance(packages, list) or not packages:
            return {"returncode": 1, "stderr": "No package names were supplied.", "stdout": ""}
        return run_command(["apt-get", "install", "-y", *[str(package) for package in packages]])

    if action == "remove_package":
        packages = arguments.get("packages", [])
        if not isinstance(packages, list) or not packages:
            return {"returncode": 1, "stderr": "No package names were supplied.", "stdout": ""}
        return run_command(["apt-get", "remove", "-y", *[str(package) for package in packages]])

    if action == "list_files":
        path = str(arguments.get("path", "."))
        return run_command(["/bin/sh", "-lc", f"find {shlex.quote(path)} -maxdepth 2 -type f | sort | head -n 200"])

    if action == "disk_usage":
        return run_command(["df", "-h"])

    if action == "system_info":
        return run_command(["/bin/sh", "-lc", "uname -a && (hostnamectl || true) && free -h && df -h"])

    if action == "show_services":
        service = str(arguments.get("service", ""))
        if not service:
            return {"returncode": 1, "stderr": "No service name was supplied.", "stdout": ""}
        return run_command(["systemctl", "status", service, "--no-pager"])

    if action == "restart_service":
        service = str(arguments.get("service", ""))
        if not service:
            return {"returncode": 1, "stderr": "No service name was supplied.", "stdout": ""}
        return run_command(["systemctl", "restart", service])

    if action == "show_logs":
        service = str(arguments.get("service", ""))
        if not service:
            return {"returncode": 1, "stderr": "No service name was supplied.", "stdout": ""}
        return run_command(["journalctl", "-u", service, "-n", "200", "--no-pager"])

    return {
        "returncode": 1,
        "stdout": "",
        "stderr": f"Unsupported request: {intent.get('action', 'unknown')}",
    }


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/command":
            self._write_json(404, {"error": "not found"})
            return

        # Secure against browser-based CSRF / CORS bypass attacks
        content_type = self.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            self._write_json(400, {"error": "Content-Type must be application/json"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        message = str(payload.get("message", "")).strip()
        if not message:
            self._write_json(400, {"error": "message is required"})
            return

        intent = ollama_intent(message) or heuristic_intent(message)
        result = execute_intent(intent)
        self._write_json(200, {"message": message, "intent": intent, **result})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()