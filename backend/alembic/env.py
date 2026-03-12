"""Alembic async environment configuration for J.A.R.V.I.S."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.models.base import Base

# Import every model module so that Base.metadata is fully populated.
# Alembic autogenerate will only detect tables registered on Base.metadata,
# so every model must be imported here.
import app.models.user  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.knowledge  # noqa: F401
import app.models.smart_home  # noqa: F401
import app.models.reminder  # noqa: F401
import app.models.passkey  # noqa: F401
import app.models.contact  # noqa: F401
import app.models.health  # noqa: F401
import app.models.focus_session  # noqa: F401
import app.models.habit  # noqa: F401

# Alembic Config object — gives access to alembic.ini values
config = context.config

# Override sqlalchemy.url from the application settings so the connection
# string is always sourced from .env / environment variables.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up Python logging from the ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# MetaData target for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine. Calls to
    context.execute() emit the given string to the script output.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations against a live connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncpg."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
