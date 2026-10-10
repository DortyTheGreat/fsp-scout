from fastapi import HTTPException


class ServiceError(HTTPException):
    """Ошибка бизнес-логики с машиночитаемым кодом: {"detail": {"code": ..., "message": ..., ...}}."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(status_code=status, detail={"code": code, "message": message, **extra})


def not_found(what: str = "Объект") -> ServiceError:
    return ServiceError(404, "not_found", f"{what} не найден")


def forbidden(message: str = "Недостаточно прав") -> ServiceError:
    return ServiceError(403, "forbidden", message)
