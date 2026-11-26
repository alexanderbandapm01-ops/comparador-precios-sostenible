"""Modelos de entrada de la API."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = r'^[^@\s]+@[^@\s]+\.[^@\s]+$'


class RegistroIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    apellido_paterno: str = Field(min_length=1, max_length=100)
    apellido_materno: Optional[str] = Field(default=None, max_length=100)
    fecha_nacimiento: date
    email: str = Field(max_length=150, pattern=EMAIL_RE)
    contrasena: str = Field(min_length=8, max_length=72)
    id_municipio: int
    latitud: Optional[float] = None
    longitud: Optional[float] = None

    @field_validator('contrasena')
    @classmethod
    def _limite_bytes(cls, v):
        if len(v.encode('utf-8')) > 72:
            raise ValueError('La contrasena no puede pasar de 72 bytes')
        return v

    @field_validator('fecha_nacimiento')
    @classmethod
    def _fecha_razonable(cls, v):
        if v > date.today() or v.year < 1900:
            raise ValueError('Fecha de nacimiento no valida')
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=150)
    contrasena: str = Field(max_length=72)


class GoogleIn(BaseModel):
    """Token de Google (GIS) y, solo para cuentas nuevas, los datos que Google no da."""
    id_token: str = Field(min_length=1)
    fecha_nacimiento: Optional[date] = None
    id_municipio: Optional[int] = None

    @field_validator('fecha_nacimiento')
    @classmethod
    def _fecha_razonable(cls, v):
        if v is not None and (v > date.today() or v.year < 1900):
            raise ValueError('Fecha de nacimiento no valida')
        return v


class UbicacionIn(BaseModel):
    latitud: float
    longitud: float


class ListaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=255)


class ListaUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=100)
    descripcion: Optional[str] = Field(default=None, max_length=255)
    estado: Optional[Literal['borrador', 'activa', 'completada']] = None


class ItemIn(BaseModel):
    id_presentacion: int
    cantidad: float = Field(default=1, gt=0, le=999999)


class ItemUpdate(BaseModel):
    cantidad: float = Field(gt=0, le=999999)


class RecomendarIn(BaseModel):
    modo: Literal['ahorro', 'ecologico', 'balance'] = 'balance'
    id_medio_transporte: Optional[int] = None
    radio_km: float = Field(default=5, gt=0, le=100)
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    codigo_postal: Optional[str] = Field(default=None, pattern=r'^\d{4,5}$')
    id_municipio: Optional[int] = None
