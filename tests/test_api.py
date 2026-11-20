from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.routes import exports


async def register_and_login(client: AsyncClient, email: str = "reader@example.com") -> dict[str, str]:
    password = "correct-horse-battery-staple"
    registered = await client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert registered.status_code == 201
    logged_in = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


@pytest.mark.asyncio
async def test_health_and_validation(client: AsyncClient) -> None:
    assert (await client.get("/health")).json() == {"status": "ok"}
    headers = await register_and_login(client)
    invalid = await client.post("/api/v1/tasks", json={"title": ""}, headers=headers)
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_task_crud_cache_and_pagination(client: AsyncClient) -> None:
    headers = await register_and_login(client)
    first = await client.post(
        "/api/v1/tasks", json={"title": "Write FastAPI post", "status": "todo"}, headers=headers
    )
    second = await client.post(
        "/api/v1/tasks", json={"title": "Ship Docker image", "status": "done"}, headers=headers
    )
    assert first.status_code == 201 and second.status_code == 201
    task_id = first.json()["id"]

    listing = await client.get("/api/v1/tasks?status=done&limit=1", headers=headers)
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["title"] == "Ship Docker image"

    initial = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    repeated = await client.get(f"/api/v1/tasks/{task_id}", headers=headers)
    assert initial.json() == repeated.json()
    assert len(client.fake_redis.values) == 1  # type: ignore[attr-defined]

    updated = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=headers)
    assert updated.status_code == 200
    assert client.fake_redis.deleted  # type: ignore[attr-defined]
    assert (await client.delete(f"/api/v1/tasks/{task_id}", headers=headers)).status_code == 204
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_task_owner_isolation_and_export_ownership(client: AsyncClient, monkeypatch) -> None:
    first_headers = await register_and_login(client, "first@example.com")
    second_headers = await register_and_login(client, "second@example.com")
    created = await client.post("/api/v1/tasks", json={"title": "Private task"}, headers=first_headers)
    task_id = created.json()["id"]
    assert (await client.get(f"/api/v1/tasks/{task_id}", headers=second_headers)).status_code == 404

    monkeypatch.setattr(exports.export_user_tasks, "delay", lambda _user_id: SimpleNamespace(id="export-123"))
    queued = await client.post("/api/v1/exports/tasks", headers=first_headers)
    assert queued.status_code == 202
    assert queued.json()["task_id"] == "export-123"
    forbidden = await client.get("/api/v1/exports/tasks/export-123", headers=second_headers)
    assert forbidden.status_code == 404
