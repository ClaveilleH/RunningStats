from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.accounts import AccessError
from app.api import admin, auth, garmin, health, jobs, me

app = FastAPI(title="RunningStats API", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.exception_handler(AccessError)
def access_error_handler(_: Request, exc: AccessError) -> JSONResponse:
    return JSONResponse({"detail": exc.message}, status_code=exc.status_code)


api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(me.router)
api.include_router(garmin.router)
api.include_router(garmin.sync_router)
api.include_router(jobs.router)
api.include_router(admin.router)
app.include_router(api)
