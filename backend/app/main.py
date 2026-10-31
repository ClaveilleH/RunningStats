from fastapi import APIRouter, FastAPI

from app.api import health

app = FastAPI(title="RunningStats API", docs_url="/api/docs", openapi_url="/api/openapi.json")

api = APIRouter(prefix="/api")
api.include_router(health.router)
app.include_router(api)
