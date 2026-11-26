"""Limite de intentos fallidos de inicio de sesion.

En memoria: el servicio corre con un solo proceso, asi que el conteo es
consistente; al reiniciar el servicio los contadores se limpian (para un
bloqueo persistente habria que guardar los intentos en la base de datos).

Regla: 5 intentos fallidos por correo en 15 minutos -> bloqueo de 15 minutos.
Ademas, 20 intentos fallidos por IP en 15 minutos -> bloqueo de 15 minutos
(frena que desde una misma IP se prueben muchos correos distintos).
El mensaje de bloqueo no dice si fue por correo o por IP.
"""
import threading
import time

from fastapi import HTTPException

LIMITE_CORREO = 5
LIMITE_IP = 20
VENTANA_SEG = 15 * 60
BLOQUEO_SEG = 15 * 60

_bloqueos = {}
_candado = threading.Lock()


def _registro(clave):
    return _bloqueos.setdefault(clave, {'intentos': [], 'bloqueado_hasta': 0.0})


def limpiar_todo():
    """Solo para pruebas: vacia todos los contadores."""
    with _candado:
        _bloqueos.clear()


def revisar(clave, limite):
    """Lanza 429 si la clave esta bloqueada; si no, limpia intentos viejos."""
    ahora = time.time()
    with _candado:
        reg = _registro(clave)
        if reg['bloqueado_hasta'] > ahora:
            espera = int(reg['bloqueado_hasta'] - ahora)
            minutos = max(1, (espera + 59) // 60)
            raise HTTPException(
                429,
                f'Demasiados intentos fallidos. Intentalo de nuevo en {minutos} minutos.',
                headers={'Retry-After': str(espera)})
        reg['intentos'] = [t for t in reg['intentos'] if ahora - t < VENTANA_SEG]


def registrar_fallo(clave, limite):
    """Anota un intento fallido; al llegar al limite, bloquea la clave."""
    ahora = time.time()
    with _candado:
        reg = _registro(clave)
        reg['intentos'] = [t for t in reg['intentos'] if ahora - t < VENTANA_SEG]
        reg['intentos'].append(ahora)
        if len(reg['intentos']) >= limite:
            reg['bloqueado_hasta'] = ahora + BLOQUEO_SEG
            reg['intentos'] = []


def limpiar(clave):
    """Olvida los intentos de una clave (al iniciar sesion bien)."""
    with _candado:
        _bloqueos.pop(clave, None)


def ip_cliente(peticion):
    """IP real del cliente: detras de nginx llega en X-Real-IP."""
    real = peticion.headers.get('x-real-ip')
    if real:
        return real.strip().split(',')[0]
    reenviada = peticion.headers.get('x-forwarded-for')
    if reenviada:
        return reenviada.strip().split(',')[0]
    return peticion.client.host if peticion.client else 'desconocida'
