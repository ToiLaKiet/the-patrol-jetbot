import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db.base import Base
import app.models  # Ensure all models are registered on Base.metadata
import app.db.session as app_session
from app.db.session import get_db
from app.main import app

# In-memory test database with StaticPool so all connections share the same memory instance
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Patch app's engine and SessionLocal so websocket endpoints also use test db
app_session.engine = test_engine
app_session.SessionLocal = TestingSessionLocal

@pytest.fixture(scope="function")
def db_session():
    """Creates a fresh in-memory database for each test function"""
    Base.metadata.create_all(bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)

@pytest.fixture(scope="function")
def client(db_session):
    """Overrides get_db dependency to point to the in-memory test database"""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
