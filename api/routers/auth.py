"""Registro, inicio de sesion y ubicacion del usuario."""
from datetime import date

import pymysql
from fastapi import APIRouter, Depends, HTTPException

from ..db import obtener_db
from ..esquemas import LoginIn, RegistroIn, UbicacionIn
from ..seguridad import crear_token, hashear, usuario_actual, verificar
from ..servicios.geo import validar_coordenadas, wkt_punto

router = APIRouter(prefix='/auth', tags=['Autenticacion'])

# Para tardar lo mismo cuando el correo no existe (evita adivinar quien tiene cuenta)
_HASH_FALSO = hashear('contrasena-de-relleno')
_UBICACION = "ST_GeomFromText(%s, 4326, 'axis-order=long-lat')"


@router.post('/registro', status_code=201)
def registro(datos: RegistroIn, db=Depends(obtener_db)):
    if (datos.latitud is None) != (datos.longitud is None):
        raise HTTPException(422, 'Envia la latitud y la longitud juntas')
    if datos.latitud is not None:
        validar_coordenadas(datos.latitud, datos.longitud)
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM municipio WHERE id_municipio = %s', (datos.id_municipio,))
        if not cur.fetchone():
            raise HTTPException(422, 'El municipio no existe')
        columnas = ('nombre, apellido_paterno, apellido_materno, fecha_nacimiento, email, contrasena_hash, '
                    'id_municipio')
        valores = [datos.nombre, datos.apellido_paterno, datos.apellido_materno, datos.fecha_nacimiento,
                   datos.email.lower(), hashear(datos.contrasena), datos.id_municipio]
        marcas = '%s, %s, %s, %s, %s, %s, %s'
        if datos.latitud is not None:
            columnas += ', ubicacion'
            marcas += ', ' + _UBICACION
            valores.append(wkt_punto(datos.latitud, datos.longitud))
        try:
            cur.execute(f'INSERT INTO usuario ({columnas}) VALUES ({marcas})', valores)
        except pymysql.err.IntegrityError as e:
            db.rollback()
            if e.args and e.args[0] == 1062:
                raise HTTPException(409, 'Ya existe una cuenta con ese correo')
            raise
        id_usuario = cur.lastrowid
    db.commit()
    return {'id_usuario': id_usuario, 'token': crear_token(id_usuario)}


@router.post('/login')
def login(datos: LoginIn, db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT id_usuario, contrasena_hash FROM usuario WHERE email = %s', (datos.email.lower(),))
        fila = cur.fetchone()
    correcto = verificar(datos.contrasena, fila['contrasena_hash'] if fila else _HASH_FALSO)
    if not fila or not correcto:
        raise HTTPException(401, 'Correo o contrasena incorrectos')
    return {'id_usuario': fila['id_usuario'], 'token': crear_token(fila['id_usuario'])}


@router.get('/yo')
def yo(usuario=Depends(usuario_actual)):
    nac, hoy = usuario['fecha_nacimiento'], date.today()
    edad = hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))
    return {**usuario, 'edad': edad}


@router.put('/ubicacion')
def guardar_ubicacion(datos: UbicacionIn, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    validar_coordenadas(datos.latitud, datos.longitud)
    with db.cursor() as cur:
        cur.execute(f'UPDATE usuario SET ubicacion = {_UBICACION} WHERE id_usuario = %s',
                    (wkt_punto(datos.latitud, datos.longitud), usuario['id_usuario']))
    db.commit()
    return {'latitud': datos.latitud, 'longitud': datos.longitud}


@router.delete('/ubicacion', status_code=204)
def borrar_ubicacion(usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('UPDATE usuario SET ubicacion = NULL WHERE id_usuario = %s', (usuario['id_usuario'],))
    db.commit()
