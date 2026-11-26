"""
02_cargar.py - Carga los parquet limpios (salida/ de 01_limpiar.py) a MySQL 8.0.

RECREADO el 2026-11-25: el script original del equipo no estaba en los archivos
entregados. Se reconstruyo a partir de etl/LEEME.txt, del esquema
sql/comparador_precios_sostenible.sql (21 tablas) y de los parquet de referencia.

Uso (desde etl/):
    python 02_cargar.py              # pide la contrasena de MySQL
    python 02_cargar.py --reiniciar  # pide escribir SI; borra productos,
                                     # sucursales y precios, NO usuarios ni listas
Variables de entorno: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SOCKET.

Si la base ya tiene precios, se niega a cargar (para no duplicar).
Al final verifica: conteos por tabla y que toda sucursal tenga ubicacion POINT.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

import pandas as pd
import pymysql

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI.parent / "salida"

# unidad en el parquet -> (abreviatura, tipo) en unidad_medida
TIPO_UNIDAD = {"Kg": "masa", "Gr": "masa", "Lt": "volumen", "Ml": "volumen",
               "Pza": "pieza", "N/A": "otro"}
NOMBRE_UNIDAD = {"Kg": "Kilogramo", "Gr": "Gramo", "Lt": "Litro",
                 "Ml": "Mililitro", "Pza": "Pieza", "N/A": "Sin unidad"}


def conectar():
    datos = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
                 user=os.getenv("DB_USER", "root"), database=os.getenv("DB_NAME", "comparador_precios_sostenible"),
                 charset="utf8mb4", autocommit=False)
    if os.getenv("DB_SOCKET"):
        datos["unix_socket"] = os.getenv("DB_SOCKET")
    clave = os.getenv("DB_PASSWORD")
    if clave is None:
        clave = getpass.getpass(f"Contrasena de MySQL para {datos['user']}: ")
    datos["password"] = clave
    return pymysql.connect(**datos)


def reiniciar(con):
    print("Esto borra productos, presentaciones, sucursales, precios y fuentes.")
    print("NO borra usuarios, listas ni recomendaciones guardadas de otros datos.")
    if input("Escribe SI para continuar: ").strip() != "SI":
        print("Cancelado.")
        sys.exit(0)
    with con.cursor() as cur:
        # Orden inverso a las dependencias; TRUNCATE no sirve con FK, se usa DELETE.
        for tabla in ("registro_precio", "presentacion_catalogo", "presentacion",
                      "producto", "sucursal", "fuente_datos", "categoria", "marca",
                      "catalogo", "cadena_comercial", "giro", "municipio", "estado",
                      "unidad_medida"):
            cur.execute(f"DELETE FROM {tabla}")
        # La unidad 'Sin unidad' (N/A) la vuelve a crear el script SQL; se repone aqui
        cur.execute("INSERT INTO unidad_medida (nombre, abreviatura, tipo) "
                    "VALUES ('Sin unidad', 'N/A', 'otro')")
    con.commit()
    print("Base reiniciada.")


def main():
    p = argparse.ArgumentParser(description="Carga los datos limpios a MySQL.")
    p.add_argument("--reiniciar", action="store_true")
    p.add_argument("--salida", default=str(SALIDA))
    a = p.parse_args()
    salida = Path(a.salida)
    for nombre in ("limpio_precios", "limpio_presentaciones", "limpio_sucursales",
                   "limpio_catalogos", "limpio_fuentes"):
        if not (salida / f"{nombre}.parquet").exists():
            raise SystemExit(f"Falta {salida / nombre}.parquet: corre primero 01_limpiar.py")
    con = conectar()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM registro_precio")
    if cur.fetchone()["n"]:
        if not a.reiniciar:
            print("La base ya tiene precios. Usa --reiniciar para borrar y volver a cargar.")
            sys.exit(1)
        reiniciar(con)

    precios = pd.read_parquet(salida / "limpio_precios.parquet")
    presentaciones = pd.read_parquet(salida / "limpio_presentaciones.parquet")
    sucursales = pd.read_parquet(salida / "limpio_sucursales.parquet")
    catalogos = pd.read_parquet(salida / "limpio_catalogos.parquet")
    fuentes = pd.read_parquet(salida / "limpio_fuentes.parquet")

    def insertar_id(sql, valores):
        cur.execute(sql, valores)
        return cur.lastrowid

    # --- catalogos geograficos y de producto (sin dependencias entre si) ---
    estado_id = {}
    for nombre in sorted(sucursales["estado"].unique()):
        estado_id[nombre] = insertar_id(
            "INSERT INTO estado (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_estado=LAST_INSERT_ID(id_estado)",
            (nombre,))
    municipio_id = {}
    for _, r in sucursales[["estado", "municipio"]].drop_duplicates().iterrows():
        municipio_id[(r["estado"], r["municipio"])] = insertar_id(
            "INSERT INTO municipio (id_estado, nombre) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE id_municipio=LAST_INSERT_ID(id_municipio)",
            (estado_id[r["estado"]], r["municipio"]))
    catalogo_id = {}
    for nombre in sorted(catalogos["catalogo"].unique()):
        catalogo_id[nombre] = insertar_id(
            "INSERT INTO catalogo (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_catalogo=LAST_INSERT_ID(id_catalogo)",
            (nombre,))
    categoria_id = {}
    for nombre in sorted(presentaciones["categoria"].unique()):
        categoria_id[nombre] = insertar_id(
            "INSERT INTO categoria (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_categoria=LAST_INSERT_ID(id_categoria)",
            (nombre,))
    marca_id = {}
    for nombre in sorted(presentaciones["marca"].unique()):
        marca_id[nombre] = insertar_id(
            "INSERT INTO marca (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_marca=LAST_INSERT_ID(id_marca)",
            (nombre,))
    unidad_id = {}
    for abrev in sorted(presentaciones["unidad"].unique()):
        unidad_id[abrev] = insertar_id(
            "INSERT INTO unidad_medida (nombre, abreviatura, tipo) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE id_unidad=LAST_INSERT_ID(id_unidad)",
            (NOMBRE_UNIDAD.get(abrev, abrev), abrev, TIPO_UNIDAD.get(abrev, "otro")))
    giro_id = {}
    for nombre in sorted(sucursales["giro"].unique()):
        giro_id[nombre] = insertar_id(
            "INSERT INTO giro (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_giro=LAST_INSERT_ID(id_giro)",
            (nombre,))
    cadena_id = {}
    for nombre in sorted(sucursales["cadena_comercial"].unique()):
        cadena_id[nombre] = insertar_id(
            "INSERT INTO cadena_comercial (nombre) VALUES (%s) ON DUPLICATE KEY UPDATE id_cadena=LAST_INSERT_ID(id_cadena)",
            (nombre,))

    # --- producto y presentacion ---
    producto_id = {}
    for (cat, mar, prod), _ in presentaciones.groupby(["categoria", "marca", "producto"]):
        producto_id[(cat, mar, prod)] = insertar_id(
            "INSERT INTO producto (id_categoria, id_marca, nombre) VALUES (%s, %s, %s)",
            (categoria_id[cat], marca_id[mar], prod))
    presentacion_id = {}
    for r in presentaciones.itertuples(index=False):
        presentacion_id[r.clave_presentacion] = insertar_id(
            "INSERT INTO presentacion (id_producto, id_unidad, cantidad, envase, variante, descripcion_original) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (producto_id[(r.categoria, r.marca, r.producto)], unidad_id[r.unidad],
             None if pd.isna(r.cantidad) else float(r.cantidad),
             r.envase or None, r.variante or None, r.descripcion_original))
    cur.executemany(
        "INSERT INTO presentacion_catalogo (id_presentacion, id_catalogo) VALUES (%s, %s)",
        [(presentacion_id[r.clave_presentacion], catalogo_id[r.catalogo])
         for r in catalogos.itertuples(index=False)])

    # --- sucursales (ubicacion POINT, SRID 4326, eje long-lat) ---
    sucursal_id = {}
    for r in sucursales.itertuples(index=False):
        sucursal_id[r.clave_sucursal] = insertar_id(
            "INSERT INTO sucursal (id_cadena, id_municipio, id_giro, nombre_comercial, calle, colonia, "
            "codigo_postal, ubicacion) VALUES (%s, %s, %s, %s, %s, %s, %s, "
            "ST_GeomFromText(%s, 4326, 'axis-order=long-lat'))",
            (cadena_id[r.cadena_comercial], municipio_id[(r.estado, r.municipio)], giro_id[r.giro],
             r.nombre_comercial, r.calle, r.colonia, str(r.codigo_postal).zfill(5),
             f"POINT({float(r.longitud):.7f} {float(r.latitud):.7f})"))

    # --- fuentes y precios ---
    fuente_id = {}
    for r in fuentes.itertuples(index=False):
        fuente_id[r.archivo] = insertar_id(
            "INSERT INTO fuente_datos (nombre_archivo, periodo) VALUES (%s, %s)",
            (r.archivo, r.periodo))
    cur.executemany(
        "INSERT INTO registro_precio (id_presentacion, id_sucursal, id_fuente, fecha_registro, precio) "
        "VALUES (%s, %s, %s, %s, %s)",
        [(presentacion_id[r.clave_presentacion], sucursal_id[r.clave_sucursal],
          fuente_id[r.archivo], str(r.fecha_registro)[:10], float(r.precio))
         for r in precios.itertuples(index=False)])
    con.commit()

    # --- verificacion ---
    print("Verificacion:")
    for tabla in ("estado", "municipio", "categoria", "marca", "producto", "presentacion",
                  "sucursal", "fuente_datos", "registro_precio"):
        cur.execute(f"SELECT COUNT(*) AS n FROM {tabla}")
        print(f"  {tabla}: {cur.fetchone()['n']:,}")
    cur.execute("SELECT COUNT(*) AS n FROM sucursal WHERE ubicacion IS NULL")
    assert cur.fetchone()["n"] == 0, "Hay sucursales sin ubicacion"
    cur.execute("SELECT MIN(fecha_registro) AS d1, MAX(fecha_registro) AS d2, "
                "MIN(precio) AS p1, MAX(precio) AS p2 FROM registro_precio")
    print("  rango de fechas y precios:", cur.fetchone())
    con.close()
    print("Carga completa.")


if __name__ == "__main__":
    main()
