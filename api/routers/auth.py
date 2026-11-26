"""Registro, inicio de sesion y ubicacion del usuario."""
import secrets
from datetime import date

import pymysql
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import config
from ..db import obtener_db
from ..esquemas import GoogleIn, LoginIn, RegistroIn, UbicacionIn
from ..seguridad import crear_token, hashear, usuario_actual, verificar
from ..servicios.geo import validar_coordenadas, wkt_punto
from ..servicios.limitador import LIMITE_CORREO, LIMITE_IP, ip_cliente, limpiar, registrar_fallo, revisar

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
def login(datos: LoginIn, peticion: Request, db=Depends(obtener_db)):
    correo = datos.email.lower()
    ip = ip_cliente(peticion)
    revisar(f'correo:{correo}', LIMITE_CORREO)
    revisar(f'ip:{ip}', LIMITE_IP)
    with db.cursor() as cur:
        cur.execute('SELECT id_usuario, contrasena_hash FROM usuario WHERE email = %s', (correo,))
        fila = cur.fetchone()
    correcto = verificar(datos.contrasena, fila['contrasena_hash'] if fila else _HASH_FALSO)
    if not fila or not correcto:
        registrar_fallo(f'correo:{correo}', LIMITE_CORREO)
        registrar_fallo(f'ip:{ip}', LIMITE_IP)
        raise HTTPException(401, 'Correo o contrasena incorrectos')
    limpiar(f'correo:{correo}')
    limpiar(f'ip:{ip}')
    return {'id_usuario': fila['id_usuario'], 'token': crear_token(fila['id_usuario'])}


@router.get('/google-config')
def google_config():
    """Client ID publico para el boton de Google (nulo si no esta configurado)."""
    return {'client_id': config.GOOGLE_CLIENT_ID or None}


@router.post('/google')
def login_google(datos: GoogleIn, respuesta: Response, db=Depends(obtener_db)):
    """Entrar con Google: verifica el token y crea o enlaza la cuenta por correo.

    Google da nombre y correo verificado, pero el proyecto tambien pide fecha de
    nacimiento y municipio: si la cuenta es nueva y faltan esos datos, se responde
    registro_incompleto para que el usuario los complete una sola vez.
    """
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(503, 'El inicio con Google no esta configurado en el servidor')
    try:
        from google.auth import exceptions as google_exceptions
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        raise HTTPException(503, 'Falta instalar google-auth en el servidor')
    try:
        info = google_id_token.verify_oauth2_token(
            datos.id_token, google_requests.Request(), config.GOOGLE_CLIENT_ID)
    except (ValueError, google_exceptions.GoogleAuthError):
        raise HTTPException(401, 'El token de Google no es valido')
    email = (info.get('email') or '').lower()
    if not email or not info.get('email_verified'):
        raise HTTPException(401, 'Google no confirmo el correo')
    nombre = (info.get('given_name') or info.get('name') or 'Usuario')[:100]
    apellido = (info.get('family_name') or '')[:100]
    with db.cursor() as cur:
        cur.execute('SELECT id_usuario FROM usuario WHERE email = %s', (email,))
        fila = cur.fetchone()
    if fila:
        return {'id_usuario': fila['id_usuario'], 'token': crear_token(fila['id_usuario'])}
    if not datos.fecha_nacimiento or not datos.id_municipio:
        return {'registro_incompleto': True, 'nombre': nombre, 'apellido_paterno': apellido, 'email': email}
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM municipio WHERE id_municipio = %s', (datos.id_municipio,))
        if not cur.fetchone():
            raise HTTPException(422, 'El municipio no existe')
        # Contrasena inutilizable: esta cuenta solo entra con Google
        cur.execute(
            'INSERT INTO usuario (nombre, apellido_paterno, fecha_nacimiento, email, contrasena_hash, id_municipio) '
            'VALUES (%s, %s, %s, %s, %s, %s)',
            (nombre, apellido or 'Sin apellido', datos.fecha_nacimiento, email,
             hashear(secrets.token_hex(32)), datos.id_municipio))
        id_usuario = cur.lastrowid
    db.commit()
    respuesta.status_code = 201
    return {'id_usuario': id_usuario, 'token': crear_token(id_usuario)}


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
