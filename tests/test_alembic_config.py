from configparser import ConfigParser

from rag_platform.application.db.alembic_config import escape_config_value


def test_escape_config_value_preserves_percent_encoded_database_url() -> None:
    database_url = "postgresql+asyncpg://user:p%3Fss%21word@database:5432/ragplatform"
    parser = ConfigParser()
    parser.add_section("alembic")

    parser.set("alembic", "sqlalchemy.url", escape_config_value(database_url))

    assert parser.get("alembic", "sqlalchemy.url") == database_url
