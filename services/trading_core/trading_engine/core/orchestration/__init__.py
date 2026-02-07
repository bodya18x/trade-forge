"""
Модуль оркестрации процесса бэктестинга.

Содержит координатор полного цикла обработки бэктеста:
- BacktestOrchestrator: Управляет всеми этапами от получения задачи до сохранения результатов
- BacktestPipeline: Pipeline для последовательного выполнения этапов
- PipelineContext: Контекст для передачи данных между этапами
- Stages: Отдельные этапы обработки бэктеста
"""

from __future__ import annotations

from .context import PipelineContext
from .orchestrator import BacktestOrchestrator
from .pipeline import BacktestPipeline
from .stages.analyze_strategy_stage import AnalyzeStrategyStage
from .stages.base import PipelineStage, StageError
from .stages.ensure_data_stage import EnsureDataStage
from .stages.execute_simulation_stage import ExecuteSimulationStage
from .stages.load_data_stage import LoadDataStage
from .stages.load_job_stage import LoadJobStage
from .stages.save_results_stage import SaveResultsStage

__all__ = [
    "BacktestOrchestrator",
    "BacktestPipeline",
    "PipelineContext",
    "PipelineStage",
    "StageError",
    "LoadJobStage",
    "AnalyzeStrategyStage",
    "EnsureDataStage",
    "LoadDataStage",
    "ExecuteSimulationStage",
    "SaveResultsStage",
]
