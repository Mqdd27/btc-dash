import pytest


@pytest.mark.django_db
def test_dashboard_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Engine" in response.content


@pytest.mark.django_db
def test_database_is_reachable():
    from core.health import check_database

    assert check_database() is True


def test_health_endpoint(client):
    response = client.get("/health/")
    assert response.status_code == 200
