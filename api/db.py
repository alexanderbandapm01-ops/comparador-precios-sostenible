"""Conexion a MySQL: una conexion por peticion."""
import pymysql
import pymysql.cursors

from . import config


def conectar():
    parametros = dict(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
                      password=config.DB_PASSWORD, database=config.DB_NAME, charset='utf8mb4',
                      cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    if config.DB_SOCKET:
        parametros['unix_socket'] = config.DB_SOCKET
    return pymysql.connect(**parametros)


def obtener_db():
    """Dependencia de FastAPI: abre y cierra la conexion de cada peticion."""
    con = conectar()
    try:
        yield con
    finally:
        con.close()
