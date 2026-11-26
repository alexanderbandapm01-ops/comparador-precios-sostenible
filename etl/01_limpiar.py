"""
01_limpiar.py - Limpieza de los CSV de PROFECO (Quien es Quien en los Precios, QQP).

RECREADO el 2026-11-25: el script original del equipo no estaba en los archivos
entregados. Esta version se reconstruyo a partir de:
  - etl/LEEME.txt (reglas de limpieza y alcance),
  - pryoc.ipynb (analisis de los 3 CSV: 1,583,283 filas, 15 columnas),
  - los parquet limpios ya generados (limpio_*.parquet), que fijan el esquema
    de salida exacto: columnas y claves por orden de primera aparicion.

Uso (desde etl/):
    python 01_limpiar.py
    python 01_limpiar.py --incluir-tal-vez
    python 01_limpiar.py --datos RUTA --salida RUTA

Entrada: datos/01-2026_Q1.csv, datos/01-2026_Q2.csv, datos/02-2026_Q1.csv
         (NO se suben a Git; ver .gitignore)
Salida:  salida/limpio_precios.parquet, limpio_presentaciones.parquet,
         limpio_sucursales.parquet, limpio_catalogos.parquet, limpio_fuentes.parquet
         salida/reportes/*.txt y *.csv (que revisar antes de cargar)
"""
import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

AQUI = Path(__file__).resolve().parent
ARCHIVOS = ["01-2026_Q1.csv", "01-2026_Q2.csv", "02-2026_Q1.csv"]
# Caja aproximada de Mexico, igual que en api/servicios/geo.py
LAT_MEX, LON_MEX = (14.0, 33.0), (-119.0, -86.0)

UNIDADES = {  # texto en la presentacion -> (abreviatura, tipo)
    "kg": ("Kg", "masa"), "kilo": ("Kg", "masa"), "kilos": ("Kg", "masa"),
    "gr": ("Gr", "masa"), "g": ("Gr", "masa"), "gramos": ("Gr", "masa"),
    "lt": ("Lt", "volumen"), "l": ("Lt", "volumen"), "litro": ("Lt", "volumen"),
    "litros": ("Lt", "volumen"),
    "ml": ("Ml", "volumen"), "mililitros": ("Ml", "volumen"),
    "pza": ("Pza", "pieza"), "pieza": ("Pza", "pieza"), "piezas": ("Pza", "pieza"),
    "paquete": ("Pza", "pieza"), "caja": ("Pza", "pieza"),
}
# "Paquete C/18 Blanco" -> 18 piezas; "Caja con 25 Sobres" -> 25 piezas
RE_CANTIDAD_PAQUETE = re.compile(r"(?:c/|con)\s*(\d+(?:[.,]\d+)?)", re.I)
RE_CANTIDAD_UNIDAD = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|kilos?|gr|gramos?|lt|litros?|ml|pza|piezas?)\b", re.I)
RE_CP = re.compile(r"\b[Cc][Pp]\.?\s*(\d{4,5})\b")
RE_COLONIA = re.compile(r"\b[Cc]ol\.?\s*(.+?)(?:\s*[Cc][Pp]\.?\s*\d{4,5}\s*)?$")


def norm(texto):
    t = unicodedata.normalize("NFKD", str(texto))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().casefold()


def leer_csv_robusto(ruta):
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        for sep in (",", ";", "\t", "|"):
            try:
                df = pd.read_csv(ruta, encoding=enc, sep=sep, nrows=5)
                if df.shape[1] > 1:
                    return pd.read_csv(ruta, encoding=enc, sep=sep)
            except Exception:
                continue
    return pd.read_csv(ruta, encoding="latin-1")


def cargar_mapeo(ruta, incluir_tal_vez):
    mapeo = pd.read_csv(ruta, encoding="utf-8-sig", dtype=str).fillna("")
    alcance = {}
    for r in mapeo.itertuples(index=False):
        alcance[norm(r.categoria)] = r.en_alcance.strip().lower()
    en_si = {c for c, v in alcance.items() if v == "si"}
    tal_vez = {c for c, v in alcance.items() if v == "tal_vez"}
    permitidas = en_si | (tal_vez if incluir_tal_vez else set())
    return permitidas, tal_vez


def corregir_coordenadas(lat, lon):
    """Si una coordenada tiene el signo invertido y al invertirlo cae en Mexico,
    se corrige. Devuelve (lat, lon, corregida)."""
    if pd.isna(lat) or pd.isna(lon):
        return lat, lon, False
    if -LAT_MEX[1] <= lat <= -LAT_MEX[0] and LON_MEX[0] <= lon <= LON_MEX[1]:
        return -lat, lon, True
    if LAT_MEX[0] <= lat <= LAT_MEX[1] and -LON_MEX[1] <= lon <= -LON_MEX[0]:
        return lat, -lon, True
    if -LAT_MEX[1] <= lat <= -LAT_MEX[0] and -LON_MEX[1] <= lon <= -LON_MEX[0]:
        return -lat, -lon, True
    return lat, lon, False


def separar_direccion(direccion):
    """'Blvd. ... Col. Prados de Villasuncion. Cp. 20280' -> (calle, colonia, cp).
    Si no se puede, colonia 'Sin dato' y cp '00000' (regla del LEEME)."""
    texto = str(direccion or "").strip()
    m_cp = RE_CP.search(texto)
    cp = m_cp.group(1).zfill(5) if m_cp else "00000"
    sin_cp = RE_CP.sub("", texto).strip(" .")
    m_col = re.search(r"\b[Cc]ol\.?\s*(.+)$", sin_cp)
    if m_col:
        colonia = m_col.group(1).strip(" .") or "Sin dato"
        calle = sin_cp[: m_col.start()].strip(" .") or "Sin dato"
    else:
        calle, colonia = (sin_cp or "Sin dato"), "Sin dato"
    return calle, colonia, cp


def interpretar_presentacion(texto):
    """'Botella 850 Ml. Vegetal' -> (envase, cantidad, unidad, variante).
    Un texto que es solo una unidad ('Kilo') es 1 de esa unidad.
    Lo que no se entiende queda con unidad 'N/A' y cantidad vacia."""
    t = str(texto or "").strip()
    partes = [p.strip() for p in t.split(".") if p.strip()]
    if not partes:
        return "", None, "N/A", ""
    # Cantidad + unidad: buscar en todo el texto ("850 Ml", "1 Kg", "Paquete C/18")
    m = RE_CANTIDAD_UNIDAD.search(t)
    cantidad, unidad = None, "N/A"
    if m:
        cantidad = float(m.group(1).replace(",", "."))
        unidad = UNIDADES[norm(m.group(2))][0]
    else:
        m2 = RE_CANTIDAD_PAQUETE.search(t)
        if m2 and norm(partes[0]) in ("paquete", "caja"):
            cantidad, unidad = float(m2.group(1)), "Pza"
        elif norm(t) in UNIDADES:
            cantidad, unidad = 1.0, UNIDADES[norm(t)][0]
        elif norm(partes[0]) in ("manojo",):
            cantidad, unidad = 1.0, "Pza"
    # Envase: primera palabra del primer segmento si no es cantidad/unidad
    primero = partes[0]
    envase = re.sub(r"\d+(?:[.,]\d+)?\s*(?:kg|gr|lt|ml|pza)\b", "", primero, flags=re.I).strip()
    envase = re.sub(r"^(c/|con)\s*\d+.*$", "", envase, flags=re.I).strip()
    # Variante: lo que queda despues de envase+cantidad+unidad
    resto = " ".join(partes[1:]).strip()
    variante = resto
    if not envase and variante:
        # "1 Kg. Granel. Entero": el envase es la primera palabra del resto
        palabras = variante.split(" ", 1)
        envase, variante = palabras[0], (palabras[1] if len(palabras) > 1 else "")
    if unidad == "N/A":
        return envase, None, "N/A", variante
    return envase, cantidad, unidad, variante


def main():
    p = argparse.ArgumentParser(description="Limpia los CSV de PROFECO (QQP).")
    p.add_argument("--incluir-tal-vez", action="store_true",
                   help="incluye las categorias marcadas como tal_vez")
    p.add_argument("--datos", default=str(AQUI.parent / "datos"))
    p.add_argument("--salida", default=str(AQUI.parent / "salida"))
    a = p.parse_args()
    datos, salida = Path(a.datos), Path(a.salida)
    reportes = salida / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)

    permitidas, tal_vez = cargar_mapeo(AQUI / "mapeo_huella.csv", a.incluir_tal_vez)
    frames, fuentes, descartadas = [], [], {"vacias_o_precio": 0, "fuera_de_alcance": 0,
                                            "fecha_invalida": 0, "coordenadas_invalidas": 0}
    corregidas, incompletas = [], []
    for nombre in ARCHIVOS:
        ruta = datos / nombre
        if not ruta.exists():
            print(f"AVISO: no encontrado {ruta} (se omite)")
            continue
        df = leer_csv_robusto(ruta)
        n0 = len(df)
        df = df.dropna(subset=["precio"])
        descartadas["vacias_o_precio"] += n0 - len(df)
        df["fecha_registro"] = pd.to_datetime(df["fecha_registro"], format="%Y/%m/%d", errors="coerce")
        descartadas["fecha_invalida"] += int(df["fecha_registro"].isna().sum())
        df = df.dropna(subset=["fecha_registro"])
        df["_cat_norm"] = df["categoria"].map(norm)
        fuera = ~df["_cat_norm"].isin(permitidas)
        descartadas["fuera_de_alcance"] += int(fuera.sum())
        df = df[~fuera].copy()
        df["archivo"] = nombre
        # Coordenadas: corregir signo invertido, descartar las que siguen fuera
        lat_ok, lon_ok, corr = [], [], []
        for lat, lon in zip(df["latitud"], df["longitud"]):
            la, lo, c = corregir_coordenadas(lat, lon)
            lat_ok.append(la)
            lon_ok.append(lo)
            corr.append(c)
        df["latitud"], df["longitud"] = lat_ok, lon_ok
        for _, r in df[pd.Series(corr, index=df.index)].iterrows():
            corregidas.append({"archivo": nombre, "nombre_comercial": r["nombre_comercial"],
                               "latitud": r["latitud"], "longitud": r["longitud"]})
        validas = df["latitud"].between(*LAT_MEX) & df["longitud"].between(*LON_MEX)
        descartadas["coordenadas_invalidas"] += int((~validas).sum())
        df = df[validas]
        df["fecha_registro"] = df["fecha_registro"].dt.strftime("%Y-%m-%d")
        fuentes.append({"archivo": nombre,
                        "periodo": f"{df['fecha_registro'].min()}/{df['fecha_registro'].max()}",
                        "fecha_min": df["fecha_registro"].min(),
                        "fecha_max": df["fecha_registro"].max(),
                        "registros": len(df)})
        frames.append(df)
    if not frames:
        raise SystemExit("No se leyo ningun CSV: revisa --datos")
    df = pd.concat(frames, ignore_index=True)
    print(f"Filas tras filtrar por alcance y validar: {len(df):,}")

    # Direccion -> calle / colonia / codigo postal
    partes_dir = df["direccion"].map(separar_direccion)
    df["calle"] = [x[0] for x in partes_dir]
    df["colonia"] = [x[1] for x in partes_dir]
    df["codigo_postal"] = [x[2] for x in partes_dir]
    incompletas = df[df["colonia"].eq("Sin dato") | df["codigo_postal"].eq("00000")][
        ["producto", "nombre_comercial", "direccion", "colonia", "codigo_postal"]].drop_duplicates()
    # Presentacion -> envase / cantidad / unidad / variante
    partes_pre = df["presentacion"].map(interpretar_presentacion)
    df["envase"] = [x[0] for x in partes_pre]
    df["cantidad"] = [x[1] for x in partes_pre]
    df["unidad"] = [x[2] for x in partes_pre]
    df["variante"] = [x[3] for x in partes_pre]
    sin_interpretar = df[df["unidad"].eq("N/A")][
        ["producto", "presentacion", "envase", "cantidad", "unidad", "variante"]].drop_duplicates()

    # Claves estables por orden de primera aparicion (igual que en los parquet de referencia)
    pres_clave = {}
    for _, r in df.iterrows():
        k = (r["categoria"], r["marca"], r["producto"], r["presentacion"])
        if k not in pres_clave:
            pres_clave[k] = len(pres_clave) + 1
    suc_clave = {}
    for _, r in df.iterrows():
        k = (r["cadena_comercial"], r["nombre_comercial"], r["direccion"])
        if k not in suc_clave:
            suc_clave[k] = len(suc_clave) + 1
    df["clave_presentacion"] = [pres_clave[(r.categoria, r.marca, r.producto, r.presentacion)]
                                for r in df.itertuples(index=False)]
    df["clave_sucursal"] = [suc_clave[(r.cadena_comercial, r.nombre_comercial, r.direccion)]
                            for r in df.itertuples(index=False)]

    presentaciones = (df[["clave_presentacion", "categoria", "marca", "producto", "presentacion",
                          "envase", "cantidad", "unidad", "variante"]]
                      .rename(columns={"presentacion": "descripcion_original"})
                      .drop_duplicates("clave_presentacion").sort_values("clave_presentacion"))
    sucursales = (df[["clave_sucursal", "cadena_comercial", "nombre_comercial", "calle", "colonia",
                      "codigo_postal", "giro", "estado", "municipio", "latitud", "longitud"]]
                  .drop_duplicates("clave_sucursal").sort_values("clave_sucursal"))
    catalogos = (df[["clave_presentacion", "catalogo"]]
                 .drop_duplicates().sort_values(["clave_presentacion", "catalogo"]))
    # Precios repetidos (misma presentacion, sucursal, archivo y fecha) se promedian
    g = df.groupby(["clave_presentacion", "clave_sucursal", "archivo", "fecha_registro"])["precio"]
    repetidos = g.nunique()
    precios = (g.mean().reset_index()
               .rename(columns={"precio": "precio"})
               .sort_values(["clave_presentacion", "clave_sucursal", "fecha_registro"]))
    n_rep_distinto = int(((df.groupby(["clave_presentacion", "clave_sucursal", "archivo", "fecha_registro"])
                           ["precio"].nunique() > 1)).sum())

    # Conflictos de sucursal: mismo nombre comercial en la misma cadena con >1 direccion
    conflictos = (df.groupby(["cadena_comercial", "nombre_comercial"])["direccion"].nunique()
                  .loc[lambda s: s > 1].reset_index().rename(columns={"direccion": "direcciones_distintas"}))
    # Sucursales con mas de un giro (el giro es de la sucursal, no de la cadena)
    giro_conflicto = (df.groupby(["cadena_comercial", "nombre_comercial", "direccion"])["giro"].nunique()
                      .loc[lambda s: s > 1])
    if len(giro_conflicto):
        print(f"AVISO: {len(giro_conflicto)} sucursales con mas de un giro (se queda el primero visto)")

    salida.mkdir(parents=True, exist_ok=True)
    precios.to_parquet(salida / "limpio_precios.parquet", index=False)
    presentaciones.to_parquet(salida / "limpio_presentaciones.parquet", index=False)
    sucursales.to_parquet(salida / "limpio_sucursales.parquet", index=False)
    catalogos.to_parquet(salida / "limpio_catalogos.parquet", index=False)
    pd.DataFrame(fuentes).to_parquet(salida / "limpio_fuentes.parquet", index=False)

    # Reportes
    (reportes / "resumen_limpieza.txt").write_text(
        "Resumen de limpieza\n" + "\n".join(f"- {k}: {v:,}" for k, v in descartadas.items()) +
        f"\n- filas limpias: {len(df):,}\n- presentaciones: {len(presentaciones):,}\n"
        f"- sucursales: {len(sucursales):,}\n- precios (tras promediar repetidos): {len(precios):,}\n"
        f"- precios repetidos con precio distinto (promediados): {n_rep_distinto:,}\n"
        f"- coordenadas corregidas: {len(corregidas):,}\n"
        f"- direcciones incompletas: {len(incompletas):,}\n"
        f"- presentaciones sin interpretar: {len(sin_interpretar):,}\n", encoding="utf-8")
    incompletas.to_csv(reportes / "direcciones_incompletas.csv", index=False)
    sin_interpretar.to_csv(reportes / "presentaciones_sin_interpretar.csv", index=False)
    presentaciones["unidad"].value_counts().rename_axis("unidad").reset_index(name="n").to_csv(
        reportes / "unidades_encontradas.csv", index=False)
    conflictos.to_csv(reportes / "conflictos_sucursal.csv", index=False)
    (df[df.duplicated(subset=["clave_presentacion", "clave_sucursal", "archivo", "fecha_registro"],
                      keep=False)].sort_values(["clave_presentacion", "clave_sucursal", "fecha_registro"])
     .to_csv(reportes / "precios_repetidos_con_precio_distinto.csv", index=False))
    pd.DataFrame(corregidas).to_csv(reportes / "coordenadas_corregidas.csv", index=False)
    df[df["_cat_norm"].isin(tal_vez)][["catalogo", "categoria"]].drop_duplicates().to_csv(
        reportes / "categorias_tal_vez.csv", index=False)
    print(f"Listo: {len(precios):,} precios, {len(presentaciones):,} presentaciones, "
          f"{len(sucursales):,} sucursales en {salida}")


if __name__ == "__main__":
    main()
