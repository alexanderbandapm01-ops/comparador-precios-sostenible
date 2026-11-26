"""Motor de recomendacion: ahorro, huella de carbono o un balance de ambos.

Regla (propuesta del equipo, ajustable):
  1. Candidatas: sucursales dentro del radio.
  2. Se quedan las que cubren mas productos de la lista (cobertura maxima).
  3. Costo = precio mas reciente x cantidad. Huella = productos + traslado (una sola vez por viaje).
  4. Modo ahorro: menor costo. Modo ecologico: menor huella. Modo balance: 50 % costo y 50 % huella,
     ambos escalados de 0 a 1 entre las candidatas.
  5. El traslado se reparte por partes iguales entre los productos que cubre la sucursal elegida.
"""
from fastapi import HTTPException

from .geo import resolver_ubicacion, sucursales_cercanas
from .huella import factores_producto, huella_traslado, peso_kg
from .precios import precios_recientes
from .util import a_float, marcas

PESO_COSTO = 0.5
PESO_HUELLA = 0.5


def _normalizar(valores):
    """Escala de 0 a 1 (0 = mejor). Si todos son iguales, todo queda en 0."""
    menor, mayor = min(valores), max(valores)
    if mayor == menor:
        return [0.0] * len(valores)
    return [(v - menor) / (mayor - menor) for v in valores]


def _items_de_la_lista(db, id_lista):
    with db.cursor() as cur:
        cur.execute(
            '''SELECT i.id_item, i.id_presentacion, i.cantidad, pr.id_producto, pr.nombre AS producto,
                      m.nombre AS marca, c.nombre AS categoria, pe.descripcion_original,
                      pe.cantidad AS cantidad_presentacion, u.abreviatura AS unidad
                 FROM item_lista i
                 JOIN presentacion pe ON pe.id_presentacion = i.id_presentacion
                 JOIN producto pr ON pr.id_producto = pe.id_producto
                 JOIN marca m ON m.id_marca = pr.id_marca
                 JOIN categoria c ON c.id_categoria = pr.id_categoria
                 JOIN unidad_medida u ON u.id_unidad = pe.id_unidad
                WHERE i.id_lista = %s ORDER BY i.id_item''', (id_lista,))
        items = cur.fetchall()
    for it in items:
        it['cantidad'] = float(it['cantidad'])
        it['cantidad_presentacion'] = a_float(it['cantidad_presentacion'])
    return items


def recomendar(db, usuario, id_lista, p, guardar=True):
    items = _items_de_la_lista(db, id_lista)
    if not items:
        raise HTTPException(422, 'La lista no tiene productos')
    avisos = []

    ubic = resolver_ubicacion(db, p.latitud, p.longitud, usuario, p.codigo_postal, p.id_municipio)
    if ubic['aviso']:
        avisos.append(ubic['aviso'])
    candidatas = sucursales_cercanas(db, ubic['lat'], ubic['lon'], p.radio_km)
    if not candidatas:
        raise HTTPException(404, f'No hay sucursales a menos de {p.radio_km} km')

    factor_medio, nombre_medio = None, None
    if p.id_medio_transporte is not None:
        with db.cursor() as cur:
            cur.execute('SELECT nombre, factor_emision_kgco2_km FROM medio_transporte WHERE id_transporte = %s',
                        (p.id_medio_transporte,))
            medio = cur.fetchone()
        if not medio:
            raise HTTPException(404, 'Medio de transporte no encontrado')
        factor_medio, nombre_medio = float(medio['factor_emision_kgco2_km']), medio['nombre']
    else:
        avisos.append('No se eligio medio de transporte: la huella del traslado no se calculo.')

    precios = precios_recientes(db, [it['id_presentacion'] for it in items],
                                [s['id_sucursal'] for s in candidatas])
    factores = factores_producto(db, {it['id_producto'] for it in items})

    # Huella de cada producto de la lista (no depende de la sucursal)
    supuestos = set()
    for it in items:
        kg, supuesto = peso_kg(it['cantidad_presentacion'], it['unidad'], it['categoria'])
        f = factores.get(it['id_producto'])
        if kg is None or f is None:
            it['huella'] = None
        else:
            it['huella'] = kg * f * it['cantidad']
            if supuesto:
                supuestos.add(supuesto)

    # Costo y huella por sucursal candidata
    resultados = []
    for s in candidatas:
        disp = [(it, precios[(it['id_presentacion'], s['id_sucursal'])]) for it in items
                if (it['id_presentacion'], s['id_sucursal']) in precios]
        if not disp:
            continue
        resultados.append({
            'sucursal': s, 'disp': disp,
            'costo': sum(reg[0] * it['cantidad'] for it, reg in disp),
            'h_prod': sum(it['huella'] for it, _ in disp if it['huella'] is not None),
            'sin_huella': [it for it, _ in disp if it['huella'] is None],
            'traslado': huella_traslado(s['km'], factor_medio),
        })
    if not resultados:
        raise HTTPException(404, 'Ninguna sucursal cercana tiene precio de los productos de la lista')

    maxima = max(len(r['disp']) for r in resultados)
    cands = [r for r in resultados if len(r['disp']) == maxima]
    if maxima < len(items):
        avisos.append(f'Ninguna sucursal cercana tiene los {len(items)} productos; la mejor cubre {maxima}.')
    if len({frozenset(it['id_item'] for it, _ in r['disp']) for r in cands}) > 1:
        avisos.append('Las sucursales comparadas no tienen exactamente los mismos productos.')
    for r in cands:
        r['huella_total'] = r['h_prod'] + (r['traslado'] or 0.0)

    # Puntaje de cada candidata (menor es mejor)
    costos = [r['costo'] for r in cands]
    traslado_conocido = all(r['traslado'] is not None for r in cands)
    modo = p.modo
    if modo == 'ahorro':
        puntajes = _normalizar(costos)
    elif not traslado_conocido:
        if modo == 'ecologico':
            avisos.append('Sin medio de transporte no hay huella comparable: se ordeno por cercania.')
            puntajes = _normalizar([r['sucursal']['km'] for r in cands])
        else:
            avisos.append('Sin medio de transporte no hay huella comparable: el balance se calculo solo con el costo.')
            puntajes = _normalizar(costos)
    elif modo == 'ecologico':
        puntajes = _normalizar([r['huella_total'] for r in cands])
    else:
        puntos_c = _normalizar(costos)
        puntos_h = _normalizar([r['huella_total'] for r in cands])
        puntajes = [PESO_COSTO * c + PESO_HUELLA * h for c, h in zip(puntos_c, puntos_h)]
    for r, puntaje in zip(cands, puntajes):
        r['puntaje'] = puntaje
    cands.sort(key=lambda r: (r['puntaje'], r['costo'], r['sucursal']['km']))
    elegida = cands[0]

    promedio = sum(costos) / len(costos)
    ahorro = promedio - elegida['costo']
    if len(cands) == 1:
        avisos.append('Solo una sucursal es comparable: el ahorro estimado es cero.')
    if elegida['sin_huella']:
        avisos.append(f'{len(elegida["sin_huella"])} de {len(elegida["disp"])} productos no tienen factor de emision '
                      'o peso: la huella de los productos es parcial.')
    for supuesto in supuestos:
        avisos.append(f'Supuesto en la huella de liquidos: {supuesto}.')

    s = elegida['sucursal']
    n_cubiertos = len(elegida['disp'])
    traslado_item = None if elegida['traslado'] is None else elegida['traslado'] / n_cubiertos
    filas, detalle = [], []
    for it, (precio, fecha) in elegida['disp']:
        precios_item = [precios[(it['id_presentacion'], r['sucursal']['id_sucursal'])][0] for r in cands
                        if (it['id_presentacion'], r['sucursal']['id_sucursal']) in precios]
        subtotal = precio * it['cantidad']
        ahorro_item = (sum(precios_item) / len(precios_item) - precio) * it['cantidad']
        huella_item = (it['huella'] + traslado_item) if (it['huella'] is not None and traslado_item is not None) else None
        filas.append((it['id_item'], s['id_sucursal'], round(subtotal, 2), round(ahorro_item, 2),
                      None if huella_item is None else round(huella_item, 4)))
        detalle.append({'id_item': it['id_item'], 'id_presentacion': it['id_presentacion'],
                        'producto': it['producto'], 'marca': it['marca'],
                        'presentacion': it['descripcion_original'], 'cantidad': it['cantidad'],
                        'precio_unitario': precio, 'fecha_precio': fecha, 'subtotal': round(subtotal, 2),
                        'ahorro_estimado': round(ahorro_item, 2),
                        'huella_producto_kgco2e': None if it['huella'] is None else round(it['huella'], 4),
                        'huella_con_traslado_kgco2e': None if huella_item is None else round(huella_item, 4)})
    cubiertos = {d['id_item'] for d in detalle}
    no_disponibles = [{'id_item': it['id_item'], 'producto': it['producto'], 'marca': it['marca'],
                       'presentacion': it['descripcion_original']} for it in items if it['id_item'] not in cubiertos]

    if guardar:
        with db.cursor() as cur:
            ids = [it['id_item'] for it in items]
            cur.execute(f'DELETE FROM recomendacion WHERE id_item IN ({marcas(len(ids))})', ids)
            cur.executemany('INSERT INTO recomendacion (id_item, id_sucursal, precio_estimado, ahorro_estimado, '
                            'huella_estimada_kgco2) VALUES (%s, %s, %s, %s, %s)', filas)
        db.commit()

    h_total_conocida = elegida['traslado'] is not None and not elegida['sin_huella']
    return {
        'modo': modo, 'medio_transporte': nombre_medio,
        'ubicacion': {'latitud': ubic['lat'], 'longitud': ubic['lon'], 'origen': ubic['origen']},
        'sucursal_recomendada': {k: s[k] for k in ('id_sucursal', 'nombre_comercial', 'cadena', 'giro', 'municipio',
                                                   'calle', 'colonia', 'codigo_postal', 'latitud', 'longitud')}
                                | {'distancia_km': s['km']},
        'resumen': {
            'costo_total': round(elegida['costo'], 2), 'ahorro_estimado': round(ahorro, 2),
            'huella_productos_kgco2e': round(elegida['h_prod'], 4),
            'huella_traslado_kgco2e': None if elegida['traslado'] is None else round(elegida['traslado'], 4),
            'huella_total_kgco2e': round(elegida['huella_total'], 4), 'huella_completa': h_total_conocida,
            'productos_cubiertos': n_cubiertos, 'productos_en_la_lista': len(items),
            'sucursales_comparadas': len(cands)},
        'items': detalle, 'items_no_disponibles': no_disponibles,
        'otras_sucursales': [{'id_sucursal': r['sucursal']['id_sucursal'],
                              'nombre_comercial': r['sucursal']['nombre_comercial'],
                              'distancia_km': r['sucursal']['km'], 'costo_total': round(r['costo'], 2),
                              'huella_total_kgco2e': round(r['huella_total'], 4)} for r in cands[1:4]],
        'avisos': avisos,
    }


def leer_guardadas(db, id_lista):
    with db.cursor() as cur:
        cur.execute(
            '''SELECT r.id_recomendacion, r.id_item, r.id_sucursal, s.nombre_comercial, r.precio_estimado,
                      r.ahorro_estimado, r.huella_estimada_kgco2, r.fecha_generacion
                 FROM recomendacion r
                 JOIN item_lista i ON i.id_item = r.id_item
                 JOIN sucursal s ON s.id_sucursal = r.id_sucursal
                WHERE i.id_lista = %s ORDER BY r.id_item''', (id_lista,))
        return cur.fetchall()
