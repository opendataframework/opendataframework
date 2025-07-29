import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

app.mount("/static", StaticFiles(directory="server/static"), name="static")

@app.get("/")
async def root():
    return FileResponse(os.path.join("server", "static", "index.html"))
