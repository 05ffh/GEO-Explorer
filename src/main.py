from fastapi import FastAPI

app = FastAPI(title="GEO Explorer", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}
