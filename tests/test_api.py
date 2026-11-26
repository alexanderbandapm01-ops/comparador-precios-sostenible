"""
Pruebas de la API contra la base de datos real (la que cargaste con 02_cargar.py).

Antes de correrlas, define las variables de entorno de la base (DB_HOST, DB_USER, DB_PASSWORD, ...).
JWT_SECRET se define solo con un valor de prueba.

    pytest -q tests
"""
import os
import uuid

import pytest

os.environ.setdefault('JWT_SECRET', 'secreto-solo-para-pruebas')

from fastapi.testclient import TestClient  # noqa: E402

from api.db import conectar  # noqa: E402
from api.main import app  # noqa: E402
from api.servicios.precios import precios_recientes  # noqa: E402

cliente = TestClient(app)


@pytest.fixture(scope='module')
def base():
    """Una presentacion con precios en varias sucursales y una sucursal donde se vende."""
    con = conectar()
    with con.cursor() as cur:
        cur.execute('SELECT id_presentacion, COUNT(DISTINCT id_sucursal) AS n FROM registro_precio '
                    'GROUP BY id_presentacion ORDER BY n DESC, id_presentacion LIMIT 1')
        fila = cur.fetchone()
        assert fila, 'La base no tiene precios: carga los datos con 02_cargar.py'
        cur.execute('SELECT r.id_sucursal, s.id_municipio, s.codigo_postal, ST_Latitude(s.ubicacion) AS lat, '
                    'ST_Longitude(s.ubicacion) AS lon FROM registro_precio r JOIN sucursal s '
                    'ON s.id_sucursal = r.id_sucursal WHERE r.id_presentacion = %s LIMIT 1', (fila['id_presentacion'],))
        suc = cur.fetchone()
    con.close()
    return {'id_presentacion': fila['id_presentacion'], **suc, 'lat': float(suc['lat']), 'lon': float(suc['lon'])}


def _registrar(base, nombre='Prueba'):
    correo = f'{uuid.uuid4().hex[:12]}@prueba.test'
    r = cliente.post('/auth/registro', json={
        'nombre': nombre, 'apellido_paterno': 'Ficticio', 'fecha_nacimiento': '2000-06-15', 'email': correo,
        'contrasena': 'clave-de-prueba-1', 'id_municipio': base['id_municipio']})
    assert r.status_code == 201, r.text
    return correo, r.json()['token'], r.json()['id_usuario']


@pytest.fixture()
def usuario(base):
    correo, token, id_usuario = _registrar(base)
    yield {'correo': correo, 'id': id_usuario, 'cabecera': {'Authorization': f'Bearer {token}'}}
    con = conectar()
    with con.cursor() as cur:
        cur.execute('DELETE FROM usuario WHERE id_usuario = %s', (id_usuario,))
    con.commit()
    con.close()


def test_salud():
    r = cliente.get('/salud')
    assert r.status_code == 200 and r.json()['precios_cargados'] > 0


def test_catalogos(base):
    assert len(cliente.get('/estados').json()) > 0
    municipios = cliente.get('/municipios').json()
    assert any(m['id_municipio'] == base['id_municipio'] for m in municipios)
    assert cliente.get('/categorias').status_code == 200
    assert cliente.get('/catalogos').status_code == 200
    assert cliente.get('/medios-transporte').status_code == 200


def test_registro_login_y_yo(base, usuario):
    r = cliente.get('/auth/yo', headers=usuario['cabecera'])
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo['email'] == usuario['correo'] and cuerpo['edad'] >= 18
    assert 'contrasena_hash' not in cuerpo
    ok = cliente.post('/auth/login', json={'email': usuario['correo'], 'contrasena': 'clave-de-prueba-1'})
    assert ok.status_code == 200 and ok.json()['token']
    mal = cliente.post('/auth/login', json={'email': usuario['correo'], 'contrasena': 'otra-clave-123'})
    assert mal.status_code == 401
    inexistente = cliente.post('/auth/login', json={'email': 'nadie@prueba.test', 'contrasena': 'otra-clave-123'})
    assert inexistente.status_code == 401 and inexistente.json() == mal.json()
    duplicado = cliente.post('/auth/registro', json={
        'nombre': 'X', 'apellido_paterno': 'Y', 'fecha_nacimiento': '2000-01-01', 'email': usuario['correo'].upper(),
        'contrasena': 'clave-de-prueba-1', 'id_municipio': base['id_municipio']})
    assert duplicado.status_code == 409


def test_autenticacion_requerida():
    assert cliente.get('/auth/yo').status_code == 401
    assert cliente.get('/listas').status_code == 401
    assert cliente.get('/auth/yo', headers={'Authorization': 'Bearer token-falso'}).status_code == 401


def test_validaciones_de_registro(base):
    corto = cliente.post('/auth/registro', json={
        'nombre': 'X', 'apellido_paterno': 'Y', 'fecha_nacimiento': '2000-01-01', 'email': 'a@b.co',
        'contrasena': 'corta', 'id_municipio': base['id_municipio']})
    assert corto.status_code == 422
    futuro = cliente.post('/auth/registro', json={
        'nombre': 'X', 'apellido_paterno': 'Y', 'fecha_nacimiento': '2999-01-01', 'email': 'a@b.co',
        'contrasena': 'clave-de-prueba-1', 'id_municipio': base['id_municipio']})
    assert futuro.status_code == 422
    sin_municipio = cliente.post('/auth/registro', json={
        'nombre': 'X', 'apellido_paterno': 'Y', 'fecha_nacimiento': '2000-01-01', 'email': 'a@b.co',
        'contrasena': 'clave-de-prueba-1', 'id_municipio': 99999999})
    assert sin_municipio.status_code == 422


def test_ubicacion_del_usuario(usuario):
    h = usuario['cabecera']
    fuera = cliente.put('/auth/ubicacion', headers=h, json={'latitud': -19.44, 'longitud': -99.10})
    assert fuera.status_code == 422                      # latitud con el signo invertido
    ok = cliente.put('/auth/ubicacion', headers=h, json={'latitud': 21.85, 'longitud': -102.29})
    assert ok.status_code == 200
    yo = cliente.get('/auth/yo', headers=h).json()
    assert abs(yo['latitud'] - 21.85) < 1e-6 and abs(yo['longitud'] + 102.29) < 1e-6
    assert cliente.delete('/auth/ubicacion', headers=h).status_code == 204
    assert cliente.get('/auth/yo', headers=h).json()['latitud'] is None


def test_busqueda_y_precios(base):
    r = cliente.get('/presentaciones', params={'por_pagina': 5})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo['total'] > 0 and len(cuerpo['resultados']) <= 5
    primero = cuerpo['resultados'][0]
    assert {'producto', 'marca', 'precio_minimo', 'precio_promedio'} <= set(primero)
    # el texto del usuario no rompe la consulta
    assert cliente.get('/presentaciones', params={'q': "'; DROP TABLE usuario; --"}).json()['total'] == 0
    assert cliente.get('/presentaciones', params={'q': '%'}).json()['total'] == 0
    detalle = cliente.get(f"/presentaciones/{base['id_presentacion']}").json()
    assert detalle['id_presentacion'] == base['id_presentacion'] and 'catalogos' in detalle
    precios = cliente.get(f"/presentaciones/{base['id_presentacion']}/precios").json()
    assert len(precios) >= 1
    valores = [p['precio'] for p in precios]
    assert valores == sorted(valores)
    hist = cliente.get(f"/presentaciones/{base['id_presentacion']}/historico").json()
    assert len(hist) >= 1 and all(h['minimo'] <= h['promedio'] <= h['maximo'] for h in hist)
    assert cliente.get('/presentaciones/99999999').status_code == 404
    alt = cliente.get(f"/presentaciones/{base['id_presentacion']}/alternativas")
    assert alt.status_code in (200, 422)
    if alt.status_code == 200:
        por_unidad = [a['precio_por_unidad'] for a in alt.json()]
        assert por_unidad == sorted(por_unidad)


def test_sucursales_cercanas(base, usuario):
    r = cliente.get('/sucursales/cercanas', params={'latitud': base['lat'], 'longitud': base['lon'], 'radio_km': 2})
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo['ubicacion']['origen'] == 'dispositivo'
    assert any(s['id_sucursal'] == base['id_sucursal'] for s in cuerpo['sucursales'])
    km = [s['km'] for s in cuerpo['sucursales']]
    assert km == sorted(km) and all(k <= 2 for k in km)
    assert cliente.get('/sucursales/cercanas', params={'latitud': base['lat']}).status_code == 422
    assert cliente.get('/sucursales/cercanas', params={'latitud': -base['lat'], 'longitud': base['lon']}).status_code == 422
    sin_datos = cliente.get('/sucursales/cercanas')
    assert sin_datos.status_code == 422
    por_municipio = cliente.get('/sucursales/cercanas', params={'id_municipio': base['id_municipio'], 'radio_km': 30})
    assert por_municipio.status_code == 200 and por_municipio.json()['ubicacion']['origen'] == 'municipio'
    # con sesion usa el municipio del usuario
    con_sesion = cliente.get('/sucursales/cercanas', headers=usuario['cabecera'], params={'radio_km': 30})
    assert con_sesion.status_code == 200
    cliente.put('/auth/ubicacion', headers=usuario['cabecera'], json={'latitud': base['lat'], 'longitud': base['lon']})
    guardada = cliente.get('/sucursales/cercanas', headers=usuario['cabecera'], params={'radio_km': 1})
    assert guardada.json()['ubicacion']['origen'] == 'ubicacion_guardada'


def test_listas_crud_y_aislamiento(base, usuario):
    h = usuario['cabecera']
    lista = cliente.post('/listas', headers=h, json={'nombre': 'Despensa', 'descripcion': 'Prueba'})
    assert lista.status_code == 201 and lista.json()['estado'] == 'borrador'
    id_lista = lista.json()['id_lista']
    assert cliente.get('/listas', headers=h).json()[0]['productos'] == 0
    nuevo = cliente.post(f'/listas/{id_lista}/items', headers=h,
                         json={'id_presentacion': base['id_presentacion'], 'cantidad': 2})
    assert nuevo.status_code == 201
    id_item = nuevo.json()['id_item']
    repetido = cliente.post(f'/listas/{id_lista}/items', headers=h, json={'id_presentacion': base['id_presentacion']})
    assert repetido.status_code == 409
    assert cliente.post(f'/listas/{id_lista}/items', headers=h, json={'id_presentacion': 99999999}).status_code == 404
    assert cliente.post(f'/listas/{id_lista}/items', headers=h,
                        json={'id_presentacion': base['id_presentacion'], 'cantidad': 0}).status_code == 422
    assert cliente.put(f'/listas/{id_lista}/items/{id_item}', headers=h, json={'cantidad': 5}).status_code == 200
    detalle = cliente.get(f'/listas/{id_lista}', headers=h).json()
    assert detalle['items'][0]['cantidad'] == 5
    editada = cliente.put(f'/listas/{id_lista}', headers=h, json={'nombre': 'Semana', 'estado': 'activa'})
    assert editada.json()['nombre'] == 'Semana' and editada.json()['estado'] == 'activa'
    assert cliente.put(f'/listas/{id_lista}', headers=h, json={}).status_code == 422
    assert cliente.put(f'/listas/{id_lista}', headers=h, json={'estado': 'otra'}).status_code == 422
    # otra persona no puede ver ni tocar la lista
    _, token2, id2 = _registrar(base, 'Otra')
    h2 = {'Authorization': f'Bearer {token2}'}
    try:
        assert cliente.get(f'/listas/{id_lista}', headers=h2).status_code == 404
        assert cliente.delete(f'/listas/{id_lista}', headers=h2).status_code == 404
        assert cliente.post(f'/listas/{id_lista}/items', headers=h2,
                            json={'id_presentacion': base['id_presentacion']}).status_code == 404
        assert cliente.get('/listas', headers=h2).json() == []
    finally:
        con = conectar()
        with con.cursor() as cur:
            cur.execute('DELETE FROM usuario WHERE id_usuario = %s', (id2,))
        con.commit()
        con.close()
    assert cliente.delete(f'/listas/{id_lista}/items/{id_item}', headers=h).status_code == 204
    assert cliente.delete(f'/listas/{id_lista}/items/{id_item}', headers=h).status_code == 404
    assert cliente.delete(f'/listas/{id_lista}', headers=h).status_code == 204
    assert cliente.get(f'/listas/{id_lista}', headers=h).status_code == 404


def test_recomendacion(base, usuario):
    h = usuario['cabecera']
    id_lista = cliente.post('/listas', headers=h, json={'nombre': 'Recomendar'}).json()['id_lista']
    vacia = cliente.post(f'/listas/{id_lista}/recomendar', headers=h, json={'latitud': base['lat'], 'longitud': base['lon']})
    assert vacia.status_code == 422
    cliente.post(f'/listas/{id_lista}/items', headers=h, json={'id_presentacion': base['id_presentacion'], 'cantidad': 2})
    cuerpo_base = {'latitud': base['lat'], 'longitud': base['lon'], 'radio_km': 100}
    # un medio de transporte de prueba (se borra al final)
    con = conectar()
    with con.cursor() as cur:
        cur.execute("INSERT INTO medio_transporte (nombre, factor_emision_kgco2_km) VALUES ('PRUEBA-auto', 0.2)")
        id_medio = cur.lastrowid
    con.commit()
    try:
        for modo in ('ahorro', 'ecologico', 'balance'):
            r = cliente.post(f'/listas/{id_lista}/recomendar', headers=h,
                             json={**cuerpo_base, 'modo': modo, 'id_medio_transporte': id_medio})
            assert r.status_code == 200, r.text
            c = r.json()
            assert c['modo'] == modo and c['sucursal_recomendada']['id_sucursal']
            assert c['resumen']['productos_cubiertos'] == 1 and c['resumen']['costo_total'] > 0
            assert c['resumen']['huella_traslado_kgco2e'] is not None
        # sin medio de transporte: avisa y no inventa la huella del traslado
        sin_medio = cliente.post(f'/listas/{id_lista}/recomendar', headers=h, json={**cuerpo_base, 'modo': 'ecologico'}).json()
        assert sin_medio['resumen']['huella_traslado_kgco2e'] is None and sin_medio['avisos']
        assert cliente.post(f'/listas/{id_lista}/recomendar', headers=h,
                            json={**cuerpo_base, 'id_medio_transporte': 99999999}).status_code == 404
        # modo "ahorro": la sucursal elegida es la de menor costo entre las candidatas
        cerca = cliente.get('/sucursales/cercanas', params={'latitud': base['lat'], 'longitud': base['lon'],
                                                            'radio_km': 100}).json()['sucursales']
        con = conectar()
        precios = precios_recientes(con, [base['id_presentacion']], [s['id_sucursal'] for s in cerca])
        con.close()
        barato = min(precio for precio, _ in precios.values())
        ahorro = cliente.post(f'/listas/{id_lista}/recomendar', headers=h,
                              json={**cuerpo_base, 'modo': 'ahorro', 'id_medio_transporte': id_medio}).json()
        assert abs(ahorro['items'][0]['precio_unitario'] - barato) < 0.005
        # quedo guardada y la lista paso a "activa"
        guardadas = cliente.get(f'/listas/{id_lista}/recomendaciones', headers=h).json()
        assert len(guardadas) == 1 and guardadas[0]['id_sucursal'] == ahorro['sucursal_recomendada']['id_sucursal']
        assert cliente.get(f'/listas/{id_lista}', headers=h).json()['estado'] == 'activa'
        # lejos de cualquier sucursal
        lejos = cliente.post(f'/listas/{id_lista}/recomendar', headers=h,
                             json={'latitud': 20.0, 'longitud': -117.5, 'radio_km': 1})
        assert lejos.status_code == 404
    finally:
        con = conectar()
        with con.cursor() as cur:
            cur.execute('DELETE FROM medio_transporte WHERE id_transporte = %s', (id_medio,))
        con.commit()
        con.close()


def test_limite_de_intentos_de_login(base):
    """5 intentos fallidos -> el 6o responde 429; con la clave correcta tampoco entra hasta limpiar."""
    from api.servicios.limitador import limpiar_todo
    limpiar_todo()
    correo, _token, _uid = _registrar(base)
    for _ in range(5):
        r = cliente.post('/auth/login', json={'email': correo, 'contrasena': 'clave-incorrecta'})
        assert r.status_code == 401, r.text
    r = cliente.post('/auth/login', json={'email': correo, 'contrasena': 'clave-incorrecta'})
    assert r.status_code == 429, r.text
    assert 'Retry-After' in r.headers
    assert 'minutos' in r.json()['detail']
    bien = cliente.post('/auth/login', json={'email': correo, 'contrasena': 'clave-de-prueba-1'})
    assert bien.status_code == 429, bien.text
    limpiar_todo()
    ok = cliente.post('/auth/login', json={'email': correo, 'contrasena': 'clave-de-prueba-1'})
    assert ok.status_code == 200 and ok.json()['token']
