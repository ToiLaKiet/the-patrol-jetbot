import uvicorn
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings

def main():
    print("=" * 60)
    print(f"  {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}")
    print(f"  Swagger API Docs: http://localhost:{settings.PORT}/docs")
    print(f"  Web Dashboard:   http://localhost:{settings.PORT}/")
    print(f"  WebSocket:       ws://localhost:{settings.PORT}/ws/web")
    print("=" * 60)
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )

if __name__ == "__main__":
    main()
