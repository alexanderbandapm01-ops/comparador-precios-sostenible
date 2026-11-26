"""Ubicacion del usuario y sucursales cercanas."""
import math

from fastapi import HTTPException

# Caja aproximada de Mexico: sirve para detectar signos invertidos en las coordenadas
LAT_MEX = (14.0, 33.0)
LON_MEX = (-119.0, -86.0)
KM_POR_GRADO = 111.0
MIN_SUCURSALES_CP = 3   # con menos sucursales, el "centro" del codigo postal no sirve


def validar_coordenadas(lat, lon):
    if not (LAT_MEX[0] <= lat <= LAT_MEX[1] and LON_MEX[0] <= lon <= LON_MEX[1]):
        raise HTTPException(422, 'Las coordenadas estan fuera de Mexico. Revisa el signo de la latitud y la longitud.')


def wkt_punto(lat, lon):
    """Texto de un punto. Siempre se usa con 'axis-order=long-lat': primero longitud."""
    return f'POINT({lon:.7f} {lat:.7f})'


def wkt_caja(lat, lon, radio_km):
    """Recuadro alrededor del punto (usa el indice espacial antes de medir la distancia exacta)."""
    dlat = radio_km / KM_POR_GRADO
    dlon = radio_km / (KM_POR_GRADO * max(math.cos(math.radians(lat)), 0.05))
    lat1, lat2 = max(lat - dlat, -89.9), min(lat + dlat, 89.9)
    lon1, lon2 = max(lon - dlon, -179.9), min(lon + dlon, 179.9)
    return (f'POLYGON(({lon1:.6f} {lat1:.6f}, {lon2:.6f} {lat1:.6f}, {lon2:.6f} {lat2:.6f}, '
            f'{lon1:.6f} {lat2:.6f}, {lon1:.6f} {lat1:.6f}))')


def _centro(db, columna, valor):
    # 'columna' es siempre un nombre fijo del codigo, nunca texto del usuario
    with db.cursor() as cur:
        cur.execute(f'SELECT AVG(ST_Latitude(ubicacion)) AS lat, AVG(ST_Longitude(ubicacion)) AS lon, '
                    f'COUNT(*) AS n FROM sucursal WHERE {columna} = %s', (valor,))
        return cur.fetchone()


def resolver_ubicacion(db, latitud=None, longitud=None, usuario=None, codigo_postal=None, id_municipio=None):
    """Orden: coordenadas enviadas, ubicacion guardada, centro del codigo postal, centro del municipio."""
    if (latitud is None) != (longitud is None):
        raise HTTPException(422, 'Envia la latitud y la longitud juntas')
    if latitud is not None:
        validar_coordenadas(latitud, longitud)
        return {'lat': latitud, 'lon': longitud, 'origen': 'dispositivo', 'aviso': None}
    if usuario and usuario.get('latitud') is not None:
        return {'lat': float(usuario['latitud']), 'lon': float(usuario['longitud']),
                'origen': 'ubicacion_guardada', 'aviso': None}
    if codigo_postal:
        c = _centro(db, 'codigo_postal', codigo_postal.zfill(5))
        if c['n'] >= MIN_SUCURSALES_CP:
            return {'lat': float(c['lat']), 'lon': float(c['lon']), 'origen': 'codigo_postal',
                    'aviso': f'Ubicacion aproximada: centro de {c["n"]} sucursales con ese codigo postal.'}
    municipio = id_municipio or (usuario or {}).get('id_municipio')
    if municipio:
        c = _centro(db, 'id_municipio', municipio)
        if c['n'] > 0:
            return {'lat': float(c['lat']), 'lon': float(c['lon']), 'origen': 'municipio',
                    'aviso': f'Ubicacion aproximada: centro de las {c["n"]} sucursales del municipio.'}
    raise HTTPException(422, 'No se pudo determinar la ubicacion. Envia latitud y longitud, un codigo postal o un municipio.')


def sucursales_cercanas(db, lat, lon, radio_km, limite=300):
    punto = wkt_punto(lat, lon)
    with db.cursor() as cur:
        cur.execute(
            '''SELECT s.id_sucursal, s.nombre_comercial, ca.nombre AS cadena, g.nombre AS giro,
                      mu.nombre AS municipio, s.calle, s.colonia, s.codigo_postal,
                      ST_Latitude(s.ubicacion) AS latitud, ST_Longitude(s.ubicacion) AS longitud,
                      ROUND(ST_Distance_Sphere(s.ubicacion, ST_GeomFromText(%s, 4326, 'axis-order=long-lat')) / 1000, 3) AS km
                 FROM sucursal s
                 JOIN cadena_comercial ca ON ca.id_cadena = s.id_cadena
                 JOIN giro g ON g.id_giro = s.id_giro
                 JOIN municipio mu ON mu.id_municipio = s.id_municipio
                WHERE MBRContains(ST_GeomFromText(%s, 4326, 'axis-order=long-lat'), s.ubicacion)
               HAVING km <= %s
                ORDER BY km LIMIT %s''',
            (punto, wkt_caja(lat, lon, radio_km), radio_km, limite))
        filas = cur.fetchall()
    for f in filas:
        f['km'] = float(f['km'])
    return filas
