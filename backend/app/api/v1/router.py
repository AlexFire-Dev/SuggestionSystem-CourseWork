from fastapi import APIRouter

from app.api.v1 import exports, health, instruments, market, meta, news, orderbook

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(meta.router)
api_router.include_router(news.router)
api_router.include_router(instruments.router)
api_router.include_router(market.router)
api_router.include_router(orderbook.router)
api_router.include_router(exports.router)
