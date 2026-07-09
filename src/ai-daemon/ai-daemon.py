#!/usr/bin/env python3
import os
import sys
import subprocess
import psutil
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastmcp import FastMCP

# Create FastAPI app
app = FastAPI(
    title="ctx0an Daemon",
    description="REST API and Model Context Protocol (MCP) server for custom Linux Live OS",
    version="1.0.0"
)

# Enable CORS for convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create FastMCP server instance
mcp = FastMCP("ctx0an Daemon MCP Server")

# --- Define MCP Tools ---

@mcp.tool()
def execute_command(command: str) -> str:
    """Execute a system bash command on the host live OS and return stdout + stderr."""
    try:
        res = subprocess.run(
            ["/bin/bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=60
        )
        return f"Exit Code: {res.returncode}\n\nStdout:\n{res.stdout}\n\nStderr:\n{res.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out after 60 seconds."
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
def read_file(path: str) -> str:
    """Read the contents of a file at the specified absolute path."""
    if not os.path.isabs(path):
        return "Error: File path must be absolute."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {e}"

@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write text content to a file at the specified absolute path, creating directories if needed."""
    if not os.path.isabs(path):
        return "Error: File path must be absolute."
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {path}"
    except Exception as e:
        return f"Error writing file: {e}"

@mcp.tool()
def list_directory(path: str) -> str:
    """List details of files and directories at the specified absolute path."""
    if not os.path.isabs(path):
        return "Error: Directory path must be absolute."
    try:
        entries = os.listdir(path)
        result = []
        for entry in entries:
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                result.append(f"[DIR]  {entry}")
            else:
                size = os.path.getsize(full_path)
                result.append(f"[FILE] {entry} ({size} bytes)")
        return "\n".join(result) if result else "Directory is empty."
    except Exception as e:
        return f"Error listing directory: {e}"

@mcp.tool()
def get_system_stats() -> str:
    """Return hardware usage statistics: CPU, RAM, Disk, and System Load."""
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        
        stats = (
            f"CPU Usage: {cpu_pct}%\n"
            f"RAM Usage: {mem.percent}% (Used: {mem.used // (1024*1024)}MB, Total: {mem.total // (1024*1024)}MB)\n"
            f"Disk Usage: {disk.percent}% (Used: {disk.used // (1024*1024)}MB, Total: {disk.total // (1024*1024)}MB)\n"
            f"System Load: {load}"
        )
        return stats
    except Exception as e:
        return f"Error gathering system stats: {e}"

# --- Define FastAPI Pydantic Models ---

class CommandRequest(BaseModel):
    command: str

class FileReadRequest(BaseModel):
    path: str

class FileWriteRequest(BaseModel):
    path: str
    content: str

class ListDirRequest(BaseModel):
    path: str

# --- Define FastAPI REST Endpoints ---

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "ctx0an Daemon",
        "version": "1.0.0",
        "endpoints": {
            "REST": {
                "GET /": "Service metadata",
                "GET /stats": "System resources usage status",
                "POST /execute": "Run shell command",
                "POST /files/read": "Retrieve file contents",
                "POST /files/write": "Write/create text files",
                "POST /files/list": "List contents of directory"
            },
            "MCP": {
                "Mount Path": "/mcp",
                "SSE Endpoint": "/mcp/sse",
                "Messages Endpoint": "/mcp/messages"
            }
        }
    }

@app.get("/stats")
def stats_endpoint():
    try:
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        return {
            "cpu_percent": cpu_pct,
            "memory": {
                "percent": mem.percent,
                "used_mb": mem.used // (1024 * 1024),
                "total_mb": mem.total // (1024 * 1024)
            },
            "disk": {
                "percent": disk.percent,
                "used_mb": disk.used // (1024 * 1024),
                "total_mb": disk.total // (1024 * 1024)
            },
            "load_average": load
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/execute")
def execute_endpoint(req: CommandRequest):
    try:
        res = subprocess.run(
            ["/bin/bash", "-c", req.command],
            capture_output=True,
            text=True,
            timeout=60
        )
        return {
            "exit_code": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 60 seconds."}
    except Exception as e:
        return {"error": str(e)}

@app.post("/files/read")
def read_file_endpoint(req: FileReadRequest):
    if not os.path.isabs(req.path):
        return {"error": "Path must be absolute."}
    try:
        with open(req.path, "r", encoding="utf-8", errors="replace") as f:
            return {"content": f.read()}
    except Exception as e:
        return {"error": str(e)}

@app.post("/files/write")
def write_file_endpoint(req: FileWriteRequest):
    if not os.path.isabs(req.path):
        return {"error": "Path must be absolute."}
    try:
        os.makedirs(os.path.dirname(req.path), exist_ok=True)
        with open(req.path, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"status": "success", "path": req.path}
    except Exception as e:
        return {"error": str(e)}

@app.post("/files/list")
def list_dir_endpoint(req: ListDirRequest):
    if not os.path.isabs(req.path):
        return {"error": "Path must be absolute."}
    try:
        entries = os.listdir(req.path)
        items = []
        for entry in entries:
            full_path = os.path.join(req.path, entry)
            is_dir = os.path.isdir(full_path)
            size = 0 if is_dir else os.path.getsize(full_path)
            items.append({
                "name": entry,
                "type": "directory" if is_dir else "file",
                "size_bytes": size
            })
        return {"path": req.path, "items": items}
    except Exception as e:
        return {"error": str(e)}

# --- Mount FastMCP SSE App ---
app.mount("/mcp", mcp.sse_app())

if __name__ == "__main__":
    import uvicorn
    # Expose the API on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)
