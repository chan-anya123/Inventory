#!/usr/bin/env python3
"""
Class-based Manual Service and Documentation Server
Serves the styled HTML User Manual and Markdown API on port 8081.
"""

import os
import socket
import threading
from typing import Optional
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles


def get_default_base_dir() -> str:
    """Resolve project base directory (parent of scripts directory)."""
    curr = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(curr) == "scripts":
        return os.path.dirname(curr)
    return curr


class ManualService:
    """Class-based Manual Service managing documentation, HTML reader, and dedicated server."""

    def __init__(self, base_dir: str = None, host: str = "0.0.0.0", port: int = 8081):
        self.base_dir = base_dir or get_default_base_dir()
        self.readme_path = os.path.join(self.base_dir, "MANUAL.md")
        self.templates_dir = os.path.join(self.base_dir, "templates")
        self.html_path = os.path.join(self.templates_dir, "manual.html")
        if not os.path.exists(self.html_path):
            fallback = os.path.join(self.base_dir, "manual.html")
            if os.path.exists(fallback):
                self.html_path = fallback

        self.static_dir = os.path.join(self.base_dir, "static")
        self.host = host
        self.port = port
        self.app = FastAPI(title="NEXT Feature - User Manual")
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes for Manual Reader."""
        if os.path.exists(self.static_dir):
            self.app.mount("/static", StaticFiles(directory=self.static_dir), name="static")

        @self.app.get("/", response_class=HTMLResponse)
        def show_manual_page():
            return self.get_manual_html()

        @self.app.get("/api/readme", response_class=PlainTextResponse)
        def get_readme_file():
            return self.get_readme_markdown()

    def get_manual_html(self) -> str:
        """Read and return manual.html content."""
        if os.path.exists(self.html_path):
            with open(self.html_path, "r", encoding="utf-8") as f:
                return f.read()
        raise HTTPException(status_code=404, detail="manual.html not found in templates")

    def get_readme_markdown(self) -> str:
        """Read and return MANUAL.md markdown content."""
        if os.path.exists(self.readme_path):
            with open(self.readme_path, "r", encoding="utf-8") as f:
                return f.read()
        root_readme = os.path.join(os.path.dirname(self.base_dir), "README.md")
        if os.path.exists(root_readme):
            with open(root_readme, "r", encoding="utf-8") as f:
                return f.read()
        return "# Error\n❌ ไม่พบไฟล์ `MANUAL.md` หรือ `README.md`"

    def run_server_in_thread(self) -> Optional[threading.Thread]:
        """Start the manual reader server on a background daemon thread if port is free."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((self.host, self.port))
            s.close()
        except OSError:
            return None

        def _serve():
            try:
                uvicorn.run(self.app, host=self.host, port=self.port, log_level="warning")
            except Exception as e:
                print(f"Manual server error: {e}")

        t = threading.Thread(target=_serve, daemon=True)
        t.start()
        return t


# Instantiate default service and expose aliases for easy imports
Manual = ManualService
ManualReader = ManualService
manual_service = ManualService()
app = manual_service.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)
