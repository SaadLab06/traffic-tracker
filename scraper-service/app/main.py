from fastapi import FastAPI

from app.routes import activity
from app.routes import marketplaces
from app.routes import traffic

app = FastAPI(title="Acquisition Scraper Service")
app.include_router(activity.router)
app.include_router(marketplaces.router)
app.include_router(traffic.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
