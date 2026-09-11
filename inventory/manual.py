import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles  # 👈 1. Import StaticFiles to serve assets

app = FastAPI(title="Manual Reader")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
README_PATH = os.path.join(BASE_DIR, "MANUAL.md")
HTML_PATH = os.path.join(BASE_DIR, "manual.html")

# 👇 2. Mount static folder to serve manual illustrations and screenshots
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/", response_class=HTMLResponse)
def show_manual_page():
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    raise HTTPException(status_code=404, detail="manual.html not found")

@app.get("/api/readme")
def get_readme_file():
    if os.path.exists(README_PATH):
        with open(README_PATH, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    return PlainTextResponse("# Error\n❌ ไม่พบไฟล์ `MANUAL.md` ในโฟลเดอร์เดียวกับสคริปต์นี้")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8081)