"""v1 路由聚合。"""
from fastapi import APIRouter

from app.api.v1 import assets, health, prompts, recipes

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(prompts.router)
api_v1_router.include_router(assets.router)
api_v1_router.include_router(recipes.router)
