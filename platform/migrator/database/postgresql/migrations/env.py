from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Импортируем Base из библиотеки tradeforge_db
from tradeforge_db.models import Base

from config.settings import get_settings

settings = get_settings()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
section = config.config_ini_section
config.set_section_option(section, "POSTGRES_URL", settings.POSTGRES_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

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


def include_object(object, name, type_, reflected, compare_to):
    """
    Функция-фильтр для Alembic autogenerate.

    Исключает таблицу alembic_version из процесса сравнения.
    """
    if type_ == "table" and name == "alembic_version":
        return False
    else:
        return True


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # Получаем схему для таблицы версий из alembic.ini
        version_schema = config.get_main_option("version_table_schema")

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Явно включаем схемы в процесс сравнения
            include_schemas=True,
            # Указываем, где искать таблицу с версиями
            version_table_schema=version_schema,
            # Полезная опция для сравнения типов колонок (например, VARCHAR(50) vs VARCHAR(100))
            compare_type=True,
            # Передаем нашу функцию-фильтр в Alembic
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
