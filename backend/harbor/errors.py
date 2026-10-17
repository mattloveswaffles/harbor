"""HarborError(status, code, message) becomes {"error": {"code", "message", "fields"}}."""


class HarborError(Exception):
    def __init__(self, status: int, code: str, message: str, fields: dict | list | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.fields = fields


def error_body(code: str, message: str, fields=None) -> dict:
    return {"error": {"code": code, "message": message, "fields": fields}}
