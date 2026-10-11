from fastapi import APIRouter

from app.api.v2 import builds, config, jobs, ota

router = APIRouter(prefix="/api/v2")
router.include_router(config.router)
router.include_router(builds.router)
router.include_router(jobs.router)
router.include_router(ota.router)
