"""Catalogos, busqueda de productos, precios, historico, alternativas y sucursales cercanas."""
from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import obtener_db
from ..seguridad import usuario_opcional
from ..servicios.geo import resolver_ubicacion, sucursales_cercanas
from ..servicios.precios import precios_recientes
from ..servicios.util import like_seguro

router = APIRouter(tags=['Catalogo y precios'])

# Factor para pasar cada unidad a su unidad base (kg, L o pieza)
A_BASE = {'Gr': 0.001, 'Kg': 1.0, 'Ml': 0.001, 'Lt': 1.0, 'Pza': 1.0}
NOMBRE_BASE = {'masa': 'kg', 'volumen': 'L', 'pieza': 'pieza'}

_FROM_PRESENTACION = '''FROM presentacion p
    JOIN producto pr ON pr.id_producto = p.id_producto
    JOIN marca m ON m.id_marca = pr.id_marca
    JOIN categoria c ON c.id_categoria = pr.id_categoria
    JOIN unidad_medida u ON u.id_unidad = p.id_unidad'''
_COLUMNAS_PRESENTACION = '''p.id_presentacion, pr.id_producto, pr.nombre AS producto, m.nombre AS marca,
    c.nombre AS categoria, p.descripcion_original, p.cantidad, p.envase, p.variante,
    u.abreviatura AS unidad, u.tipo AS tipo_unidad'''


def _presentacion_o_404(db, id_presentacion):
    with db.cursor() as cur:
        cur.execute(f'SELECT {_COLUMNAS_PRESENTACION} {_FROM_PRESENTACION} WHERE p.id_presentacion = %s',
                    (id_presentacion,))
        fila = cur.fetchone()
    if not fila:
        raise HTTPException(404, 'Presentacion no encontrada')
    if fila['cantidad'] is not None:
        fila['cantidad'] = float(fila['cantidad'])
    return fila


@router.get('/estados')
def estados(db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT id_estado, nombre FROM estado ORDER BY nombre')
        return cur.fetchall()


@router.get('/municipios')
def municipios(id_estado: int | None = None, db=Depends(obtener_db)):
    sql, params = 'SELECT id_municipio, id_estado, nombre FROM municipio', []
    if id_estado is not None:
        sql, params = sql + ' WHERE id_estado = %s', [id_estado]
    with db.cursor() as cur:
        cur.execute(sql + ' ORDER BY nombre', params)
        return cur.fetchall()


@router.get('/categorias')
def categorias(db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT id_categoria, nombre FROM categoria ORDER BY nombre')
        return cur.fetchall()


@router.get('/catalogos')
def catalogos(db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT id_catalogo, nombre FROM catalogo ORDER BY nombre')
        return cur.fetchall()


@router.get('/medios-transporte')
def medios_transporte(db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT id_transporte, nombre, factor_emision_kgco2_km FROM medio_transporte ORDER BY nombre')
        filas = cur.fetchall()
    for f in filas:
        f['factor_emision_kgco2_km'] = float(f['factor_emision_kgco2_km'])
    return filas


@router.get('/presentaciones')
def buscar_presentaciones(q: str | None = Query(default=None, max_length=100),
                          categoria: str | None = Query(default=None, max_length=150),
                          catalogo: str | None = Query(default=None, max_length=80),
                          pagina: int = Query(default=1, ge=1),
                          por_pagina: int = Query(default=20, ge=1, le=50),
                          db=Depends(obtener_db)):
    """Busca por texto (producto, marca o descripcion), categoria o catalogo, con el resumen de precios actuales."""
    condiciones, params = [], []
    if q:
        condiciones.append('(pr.nombre LIKE %s OR m.nombre LIKE %s OR p.descripcion_original LIKE %s)')
        params += [like_seguro(q)] * 3
    if categoria:
        condiciones.append('c.nombre = %s')
        params.append(categoria)
    if catalogo:
        condiciones.append('EXISTS (SELECT 1 FROM presentacion_catalogo pc JOIN catalogo ca '
                           'ON ca.id_catalogo = pc.id_catalogo WHERE pc.id_presentacion = p.id_presentacion '
                           'AND ca.nombre = %s)')
        params.append(catalogo)
    donde = (' WHERE ' + ' AND '.join(condiciones)) if condiciones else ''
    with db.cursor() as cur:
        cur.execute(f'SELECT COUNT(*) AS total {_FROM_PRESENTACION}{donde}', params)
        total = cur.fetchone()['total']
        cur.execute(f'SELECT {_COLUMNAS_PRESENTACION} {_FROM_PRESENTACION}{donde} '
                    f'ORDER BY pr.nombre, m.nombre, p.cantidad LIMIT %s OFFSET %s',
                    params + [por_pagina, (pagina - 1) * por_pagina])
        filas = cur.fetchall()
    precios = precios_recientes(db, [f['id_presentacion'] for f in filas])
    for f in filas:
        f['cantidad'] = None if f['cantidad'] is None else float(f['cantidad'])
        valores = [v[0] for (idp, _), v in precios.items() if idp == f['id_presentacion']]
        f['sucursales_con_precio'] = len(valores)
        f['precio_minimo'] = min(valores) if valores else None
        f['precio_promedio'] = round(sum(valores) / len(valores), 2) if valores else None
        f['precio_maximo'] = max(valores) if valores else None
    return {'total': total, 'pagina': pagina, 'por_pagina': por_pagina, 'resultados': filas}


@router.get('/presentaciones/{id_presentacion}')
def detalle_presentacion(id_presentacion: int, db=Depends(obtener_db)):
    fila = _presentacion_o_404(db, id_presentacion)
    with db.cursor() as cur:
        cur.execute('SELECT ca.nombre FROM presentacion_catalogo pc JOIN catalogo ca ON ca.id_catalogo = pc.id_catalogo '
                    'WHERE pc.id_presentacion = %s ORDER BY ca.nombre', (id_presentacion,))
        fila['catalogos'] = [r['nombre'] for r in cur.fetchall()]
    return fila


@router.get('/presentaciones/{id_presentacion}/precios')
def precios_por_sucursal(id_presentacion: int, id_municipio: int | None = None, id_cadena: int | None = None,
                         limite: int = Query(default=100, ge=1, le=500), db=Depends(obtener_db)):
    """Precio mas reciente de la presentacion en cada sucursal, del mas barato al mas caro."""
    _presentacion_o_404(db, id_presentacion)
    filtros, params = '', [id_presentacion, id_presentacion]
    if id_municipio is not None:
        filtros += ' AND s.id_municipio = %s'
        params.append(id_municipio)
    if id_cadena is not None:
        filtros += ' AND s.id_cadena = %s'
        params.append(id_cadena)
    with db.cursor() as cur:
        cur.execute(
            f'''SELECT s.id_sucursal, s.nombre_comercial, ca.nombre AS cadena, g.nombre AS giro,
                       mu.nombre AS municipio, es.nombre AS estado, s.calle, s.colonia, s.codigo_postal,
                       ST_Latitude(s.ubicacion) AS latitud, ST_Longitude(s.ubicacion) AS longitud,
                       r.precio, r.fecha_registro
                  FROM registro_precio r
                  JOIN (SELECT id_sucursal, MAX(fecha_registro) AS f FROM registro_precio
                         WHERE id_presentacion = %s GROUP BY id_sucursal) u
                    ON u.id_sucursal = r.id_sucursal AND u.f = r.fecha_registro
                  JOIN sucursal s ON s.id_sucursal = r.id_sucursal
                  JOIN cadena_comercial ca ON ca.id_cadena = s.id_cadena
                  JOIN giro g ON g.id_giro = s.id_giro
                  JOIN municipio mu ON mu.id_municipio = s.id_municipio
                  JOIN estado es ON es.id_estado = mu.id_estado
                 WHERE r.id_presentacion = %s{filtros}
                 ORDER BY r.precio, s.nombre_comercial LIMIT %s''', params + [limite])
        filas = cur.fetchall()
    for f in filas:
        f['precio'] = float(f['precio'])
    return filas


@router.get('/presentaciones/{id_presentacion}/historico')
def historico(id_presentacion: int, id_sucursal: int | None = None, db=Depends(obtener_db)):
    """Evolucion del precio por fecha (minimo, promedio y maximo entre sucursales)."""
    _presentacion_o_404(db, id_presentacion)
    filtro, params = '', [id_presentacion]
    if id_sucursal is not None:
        filtro = ' AND id_sucursal = %s'
        params.append(id_sucursal)
    with db.cursor() as cur:
        cur.execute(f'SELECT fecha_registro, MIN(precio) AS minimo, ROUND(AVG(precio), 2) AS promedio, '
                    f'MAX(precio) AS maximo, COUNT(*) AS sucursales FROM registro_precio '
                    f'WHERE id_presentacion = %s{filtro} GROUP BY fecha_registro ORDER BY fecha_registro', params)
        filas = cur.fetchall()
    for f in filas:
        for k in ('minimo', 'promedio', 'maximo'):
            f[k] = float(f[k])
    return filas


@router.get('/presentaciones/{id_presentacion}/alternativas')
def alternativas(id_presentacion: int, limite: int = Query(default=10, ge=1, le=50), db=Depends(obtener_db)):
    """Presentaciones de la misma categoria y tipo de unidad, ordenadas por precio por kg, L o pieza."""
    base = _presentacion_o_404(db, id_presentacion)
    if base['tipo_unidad'] not in NOMBRE_BASE or not base['cantidad']:
        raise HTTPException(422, 'Esta presentacion no tiene una unidad comparable')
    with db.cursor() as cur:
        cur.execute(f'SELECT {_COLUMNAS_PRESENTACION} {_FROM_PRESENTACION} '
                    'WHERE c.nombre = %s AND u.tipo = %s AND p.cantidad IS NOT NULL AND p.cantidad > 0',
                    (base['categoria'], base['tipo_unidad']))
        candidatas = cur.fetchall()
    precios = precios_recientes(db, [c['id_presentacion'] for c in candidatas])
    por_presentacion = {}
    for (idp, _), (precio, _) in precios.items():
        por_presentacion.setdefault(idp, []).append(precio)
    resultado = []
    for c in candidatas:
        valores = por_presentacion.get(c['id_presentacion'])
        if not valores:
            continue
        cantidad_base = float(c['cantidad']) * A_BASE[c['unidad']]
        promedio = sum(valores) / len(valores)
        resultado.append({'id_presentacion': c['id_presentacion'], 'producto': c['producto'], 'marca': c['marca'],
                          'descripcion': c['descripcion_original'], 'precio_promedio': round(promedio, 2),
                          'sucursales_con_precio': len(valores),
                          'precio_por_unidad': round(promedio / cantidad_base, 2),
                          'unidad_de_comparacion': NOMBRE_BASE[c['tipo_unidad']],
                          'es_la_consultada': c['id_presentacion'] == id_presentacion})
    resultado.sort(key=lambda r: r['precio_por_unidad'])
    return resultado[:limite]


@router.get('/sucursales/cercanas')
def cercanas(latitud: float | None = None, longitud: float | None = None, codigo_postal: str | None = Query(
             default=None, pattern=r'^\d{4,5}$'), id_municipio: int | None = None,
             radio_km: float = Query(default=5, gt=0, le=100), usuario=Depends(usuario_opcional),
             db=Depends(obtener_db)):
    """Sucursales dentro del radio. La ubicacion se toma de: coordenadas, la guardada del usuario, el
    codigo postal o el municipio."""
    ubic = resolver_ubicacion(db, latitud, longitud, usuario, codigo_postal, id_municipio)
    return {'ubicacion': {'latitud': ubic['lat'], 'longitud': ubic['lon'], 'origen': ubic['origen']},
            'aviso': ubic['aviso'], 'radio_km': radio_km,
            'sucursales': sucursales_cercanas(db, ubic['lat'], ubic['lon'], radio_km)}
