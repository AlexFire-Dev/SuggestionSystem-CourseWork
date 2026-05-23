from fastapi import APIRouter

from app.services.dwh_service import list_migrations

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/migrations")
def migrations() -> list[dict]:
    return list_migrations()
