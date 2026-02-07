"""
Pipeline Context - контекст для передачи данных между этапами pipeline.

Инкапсулирует все данные необходимые для выполнения бэктеста,
передаваемые между этапами обработки.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from clickhouse_connect.driver.asyncclient import AsyncClient

from models import BacktestJobDetails, TickerInfo
from models.strategy import StrategyDefinition


@dataclass
class PipelineContext:
    """
    Контекст для передачи данных между этапами pipeline бэктеста.

    Содержит все необходимые данные для координации выполнения бэктеста.
    Каждый stage может читать и обновлять контекст.

    Attributes:
        job_id: UUID задачи на бэктест.
        client: Async ClickHouse client из pool.
        correlation_id: ID корреляции для трейсинга.
        job_details: Детали задачи (заполняется в LoadJobStage).
        ticker_info: Информация о тикере (заполняется в LoadJobStage).
        strategy_definition: Определение стратегии (заполняется в LoadJobStage).
        required_indicators: Список требуемых индикаторов (заполняется в AnalyzeStrategyStage).
        dataframe: DataFrame с данными для бэктеста (заполняется в LoadDataStage).
        trades: Список завершенных сделок (заполняется в ExecuteSimulationStage).
        simulation_params: Параметры симуляции из job_details.
        lot_size: Размер лота инструмента.
    """

    # Обязательные параметры
    job_id: uuid.UUID
    client: AsyncClient
    correlation_id: str | None = None

    # Данные, заполняемые на этапах pipeline
    job_details: BacktestJobDetails | None = None
    ticker_info: TickerInfo | None = None
    strategy_definition: StrategyDefinition | None = None
    required_indicators: list[tuple[str, str]] = field(default_factory=list)
    dataframe: pd.DataFrame | None = None
    trades: list[Any] = field(default_factory=list)
    simulation_params: dict[str, Any] = field(default_factory=dict)
    lot_size: int = 1

    # Флаги управления процессом
    skip_indicator_check: bool = False

    # Вспомогательные свойства для удобного доступа
    @property
    def ticker(self) -> str:
        """Возвращает тикер из job_details."""
        if not self.job_details:
            raise ValueError("job_details not loaded yet")
        return self.job_details.ticker

    @property
    def timeframe(self) -> str:
        """Возвращает таймфрейм из job_details."""
        if not self.job_details:
            raise ValueError("job_details not loaded yet")
        return self.job_details.timeframe

    @property
    def start_date(self) -> datetime:
        """Возвращает дату начала из job_details."""
        if not self.job_details:
            raise ValueError("job_details not loaded yet")
        return self.job_details.start_date

    @property
    def end_date(self) -> datetime:
        """Возвращает дату окончания из job_details."""
        if not self.job_details:
            raise ValueError("job_details not loaded yet")
        return self.job_details.end_date
