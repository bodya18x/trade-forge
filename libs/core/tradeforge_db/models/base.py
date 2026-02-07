import sqlalchemy
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase):
    def to_dict(self):
        return {
            c.key: getattr(self, c.key)
            for c in sqlalchemy.inspect(self).mapper.column_attrs
        }


class TimestampTemplate(Base):
    """Абстрактный класс таблицы содержащий время сохранения и обновления."""

    __abstract__ = True
    created_at = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        server_default=sqlalchemy.sql.func.now(),
        doc="(datetime) - время сохранения записи",
        comment="(datetime) - время сохранения записи",
        index=True,
    )
    updated_at = mapped_column(
        sqlalchemy.DateTime(timezone=True),
        server_default=sqlalchemy.sql.func.now(),
        server_onupdate=sqlalchemy.sql.func.now(),
        doc="(datetime) - время обновления записи",
        comment="(datetime) - время обновления записи",
    )
