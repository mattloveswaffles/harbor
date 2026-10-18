"""Bank layer: the Capital One Nessie client."""

from fastapi import Request

from harbor.bank.base import (
    Bank,
    BankWrite,
    NessieConfigError,
    NessieError,
    NessieNotFound,
    NessieRejected,
    NessieUnavailable,
    from_dollars,
    tag_for,
    to_dollars,
)
from harbor.bank.nessie import NessieClient

__all__ = [
    "Bank",
    "BankWrite",
    "NessieClient",
    "NessieConfigError",
    "NessieError",
    "NessieNotFound",
    "NessieRejected",
    "NessieUnavailable",
    "from_dollars",
    "get_bank",
    "make_bank",
    "tag_for",
    "to_dollars",
]


def make_bank(settings) -> Bank:
    return NessieClient(settings.nessie_base_url, settings.nessie_api_key.get_secret_value())


def get_bank(request: Request) -> Bank:
    return request.app.state.bank
