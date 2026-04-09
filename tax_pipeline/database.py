from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(slots=True, frozen=True)
class PostgresConnectionConfig:
    host: str
    port: int
    username: str
    password: str
    database: str

    @classmethod
    def from_spring_environment(
        cls,
        database: str | None = None,
    ) -> "PostgresConnectionConfig":
        jdbc_url = os.getenv("SPRING_DATASOURCE_URL")
        username = os.getenv("SPRING_DATASOURCE_USERNAME")
        password = os.getenv("SPRING_DATASOURCE_PASSWORD", "")

        if not jdbc_url or not username:
            raise RuntimeError(
                "SPRING_DATASOURCE_URL and SPRING_DATASOURCE_USERNAME are required for Postgres access."
            )

        normalized_url = jdbc_url.removeprefix("jdbc:")
        parsed = urlparse(normalized_url)
        if parsed.scheme != "postgresql" or not parsed.hostname:
            raise RuntimeError(f"Unsupported Spring datasource URL: {jdbc_url}")

        database_name = database or parsed.path.lstrip("/") or username
        return cls(
            host=parsed.hostname,
            port=parsed.port or 5432,
            username=username,
            password=password,
            database=database_name,
        )

    def with_database(self, database: str) -> "PostgresConnectionConfig":
        return PostgresConnectionConfig(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=database,
        )

    def connect_kwargs(self, database: str | None = None) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "user": self.username,
            "password": self.password,
            "dbname": database or self.database,
        }
