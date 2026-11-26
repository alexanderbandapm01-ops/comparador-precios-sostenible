"""
03_cargar_factores.py - Carga los factores de emision (CO2e) a MySQL.

Lee:
  factores_transporte.csv  -> tabla medio_transporte (nombre, factor_kgco2_km, fuente)
  mapeo_huella.csv         -> factor por categoria (columnas kgco2e_por_kg y fuente_del_factor)
  factores_producto.csv    -> (opcional) factor por producto, tiene prioridad sobre el de la categoria

Solo se cargan las filas que tienen un factor numerico. Las filas vacias se omiten y se avisan.
Cada vez que se ejecuta REEMPLAZA todo el contenido de factor_emision_producto.

Uso:
    python 03_cargar_factores.py
    python 03_cargar_factores.py --carpeta .

Conexion: mismas variables de entorno que 02_cargar.py (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SOCKET).
"""
import argparse
import getpass
import os
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd
import pymysql

AQUI = Path(__file__).resolve().parent


def norm(texto):
    t = unicodedata.normalize('NFKD', str(texto))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip().casefold()


def conectar():
    datos = dict(host=os.getenv('DB_HOST', '127.0.0.1'), port=int(os.getenv('DB_PORT', '3306')),
                 user=os.getenv('DB_USER', 'root'), database=os.getenv('DB_NAME', 'comparador_precios_sostenible'),
                 charset='utf8mb4', autocommit=False)
    if os.getenv('DB_SOCKET'):
        datos['unix_socket'] = os.getenv('DB_SOCKET')
    clave = os.getenv('DB_PASSWORD')
    if clave is None:
        clave = getpass.getpass(f'Contrasena de MySQL para {datos["user"]}: ')
    datos['password'] = clave
    return pymysql.connect(**datos)


def numero(texto):
    """Convierte '2.5' o '2,5' en float; devuelve None si esta vacio o no es un numero."""
    try:
        return float(str(texto).strip().replace(',', '.'))
    except ValueError:
        return None


def leer(ruta):
    return pd.read_csv(ruta, encoding='utf-8-sig', dtype=str, keep_default_na=False)


def main():
    p = argparse.ArgumentParser(description='Carga los factores de emision a MySQL.')
    p.add_argument('--carpeta', default=str(AQUI), help='carpeta con los CSV de factores')
    a = p.parse_args()
    carpeta = Path(a.carpeta)
    con = conectar()
    cur = con.cursor()

    # ---- medios de transporte
    ruta = carpeta / 'factores_transporte.csv'
    if ruta.exists():
        cargados, omitidos = 0, []
        for r in leer(ruta).itertuples(index=False):
            f = numero(r.factor_kgco2_km)
            if f is None or f < 0:
                omitidos.append(r.nombre)
                continue
            cur.execute('INSERT INTO medio_transporte (nombre, factor_emision_kgco2_km) VALUES (%s, %s) '
                        'ON DUPLICATE KEY UPDATE factor_emision_kgco2_km = VALUES(factor_emision_kgco2_km)',
                        (r.nombre.strip(), f))
            cargados += 1
        con.commit()
        print(f'Medios de transporte cargados: {cargados}')
        if omitidos:
            print('  SIN FACTOR (se omitieron, hay que llenarlos con una fuente): ' + ', '.join(omitidos))
    else:
        print(f'No se encontro {ruta.name}: se omiten los medios de transporte.')

    # ---- factores por categoria y por producto
    mapeo = leer(carpeta / 'mapeo_huella.csv')
    por_categoria = {}
    for r in mapeo.itertuples(index=False):
        f = numero(r.kgco2e_por_kg)
        if f is not None and f >= 0:
            por_categoria[norm(r.categoria)] = (f, r.fuente_del_factor.strip() or None)
    por_producto = {}
    ruta = carpeta / 'factores_producto.csv'
    if ruta.exists():
        for r in leer(ruta).itertuples(index=False):
            f = numero(r.kgco2e_por_kg)
            if f is not None and f >= 0:
                por_producto[(norm(r.categoria), norm(r.producto))] = (f, r.fuente_del_factor.strip() or None)

    cur.execute('SELECT p.id_producto, p.nombre AS producto, c.nombre AS categoria FROM producto p '
                'JOIN categoria c ON c.id_categoria = p.id_categoria')
    productos = cur.fetchall()
    filas, sin_factor, usados = [], {}, set()
    for id_producto, producto, categoria in productos:
        clave_cat = norm(categoria)
        clave_prod = (clave_cat, norm(producto))
        if clave_prod in por_producto:
            f, fuente = por_producto[clave_prod]
            usados.add(clave_prod)
        elif clave_cat in por_categoria:
            f, fuente = por_categoria[clave_cat]
        else:
            sin_factor[categoria] = sin_factor.get(categoria, 0) + 1
            continue
        filas.append((id_producto, f, fuente))
    cur.execute('DELETE FROM factor_emision_producto')
    if filas:
        cur.executemany('INSERT INTO factor_emision_producto (id_producto, kgco2_por_unidad, fuente) '
                        'VALUES (%s, %s, %s)', filas)
    con.commit()
    print(f'Factores de producto cargados: {len(filas):,} de {len(productos):,} productos')
    if sin_factor:
        print('  Categorias sin factor (productos afectados):')
        for c, n in sorted(sin_factor.items(), key=lambda x: -x[1]):
            print(f'    {c}: {n}')
    no_encontrados = set(por_producto) - usados
    if no_encontrados:
        print('  AVISO: filas de factores_producto.csv que no coinciden con ningun producto: '
              + ', '.join(f'{c} / {p}' for c, p in sorted(no_encontrados)))
    con.close()


if __name__ == '__main__':
    main()
