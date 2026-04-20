from fastapi import FastAPI

from app.routes import activity

app = FastAPI(title="Acquisition Scraper Service")
app.include_router(activity.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
