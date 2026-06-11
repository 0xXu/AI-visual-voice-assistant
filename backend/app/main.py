import logging

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

app = FastAPI(title="SightLine API", version="1.0.0")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "sightline-backend"}
