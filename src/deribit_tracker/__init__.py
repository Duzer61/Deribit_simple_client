"""Deribit index price tracker.

Сервис периодически получает index price ``btc_usd``/``eth_usd`` с публичного API Deribit,
сохраняет наблюдения в PostgreSQL и отдаёт их через read-only HTTP API.
"""
