def test_app_imports_cleanly(users_db_path):
    from src.app import app

    assert app is not None
    # Flask-Login manager attaché
    assert "login_manager" in app.server.extensions or hasattr(
        app.server, "login_manager"
    )
