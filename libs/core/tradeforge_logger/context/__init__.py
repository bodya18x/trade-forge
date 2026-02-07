# -*- coding: utf-8 -*-
"""Управление контекстом логирования."""

from __future__ import annotations

from .manager import (
    bind_context,
    clear_all_context,
    generate_request_id,
    get_correlation_id,
    get_current_context,
    get_custom_context,
    get_request_id,
    get_user_id,
    set_correlation_id,
    set_custom_context,
    set_request_id,
    set_user_id,
)

__all__ = [
    # Context Management
    "bind_context",
    "get_current_context",
    "clear_all_context",
    # Correlation ID
    "set_correlation_id",
    "get_correlation_id",
    # Request ID
    "set_request_id",
    "get_request_id",
    "generate_request_id",
    # User ID
    "set_user_id",
    "get_user_id",
    # Custom Context
    "set_custom_context",
    "get_custom_context",
]
