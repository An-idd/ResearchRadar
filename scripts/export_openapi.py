"""Export the API contract for frontend types; does not connect to a database."""

import json
from pathlib import Path

from app.config import Settings
from app.main import create_app


def main() -> None:
    settings = Settings(_env_file=None, database_url="postgresql://unused:unused@localhost/unused")
    schema = create_app(settings).openapi()
    Path("frontend/openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
