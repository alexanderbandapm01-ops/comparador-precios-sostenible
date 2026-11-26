"""Contrasenas (bcrypt) y tokens (JWT)."""
import time

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config
from .db import obtener_db

esquema = HTTPBearer(auto_error=False)


def hashear(contrasena):
    return bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('ascii')


def verificar(contrasena, hash_guardado):
    try:
        return bcrypt.checkpw(contrasena.encode('utf-8'), hash_guardado.encode('ascii'))
    except ValueError:
        return False


def _secreto():
    if not config.JWT_SECRET:
        raise HTTPException(500, 'Falta configurar JWT_SECRET en el servidor')
    return config.JWT_SECRET


def crear_token(id_usuario):
    ahora = int(time.time())
    carga = {'sub': str(id_usuario), 'iat': ahora, 'exp': ahora + config.JWT_MINUTOS * 60}
    return jwt.encode(carga, _secreto(), algorithm='HS256')


def _cargar_usuario(db, credenciales):
    try:
        datos = jwt.decode(credenciales.credentials, _secreto(), algorithms=['HS256'])
        id_usuario = int(datos['sub'])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(401, 'Sesion invalida o vencida')
    with db.cursor() as cur:
        cur.execute('SELECT id_usuario, nombre, apellido_paterno, apellido_materno, fecha_nacimiento, email, '
                    'id_municipio, ST_Latitude(ubicacion) AS latitud, ST_Longitude(ubicacion) AS longitud '
                    'FROM usuario WHERE id_usuario = %s', (id_usuario,))
        usuario = cur.fetchone()
    if not usuario:
        raise HTTPException(401, 'El usuario ya no existe')
    return usuario


def usuario_actual(credenciales: HTTPAuthorizationCredentials = Depends(esquema), db=Depends(obtener_db)):
    """Devuelve el usuario del token o responde 401."""
    if credenciales is None:
        raise HTTPException(401, 'Falta iniciar sesion')
    return _cargar_usuario(db, credenciales)


def usuario_opcional(credenciales: HTTPAuthorizationCredentials = Depends(esquema), db=Depends(obtener_db)):
    """Usuario del token si lo hay; None si no se envio token."""
    if credenciales is None:
        return None
    return _cargar_usuario(db, credenciales)
