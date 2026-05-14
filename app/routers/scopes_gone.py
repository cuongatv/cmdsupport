"""Tombstone shim for the legacy scope router removed in the unit-agile upgrade."""

from fastapi import APIRouter, Response

router = APIRouter(prefix="/scopes")


@router.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def scope_router_removed(full_path: str) -> Response:
    return Response(
        status_code=410,
        content="Endpoint removed; use /api/departments/{id}/members",
        media_type="text/plain",
    )
