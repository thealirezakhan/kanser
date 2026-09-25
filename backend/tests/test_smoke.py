from app.main import app


def test_app_loads():
    assert app.title == "Kanser API"
