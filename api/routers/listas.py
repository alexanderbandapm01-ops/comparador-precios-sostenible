"""Listas de compra (CRUD), sus productos y la recomendacion."""
import pymysql
from fastapi import APIRouter, Depends, HTTPException

from ..db import obtener_db
from ..esquemas import ItemIn, ItemUpdate, ListaIn, ListaUpdate, RecomendarIn
from ..seguridad import usuario_actual
from ..servicios.recomendador import leer_guardadas, recomendar

router = APIRouter(prefix='/listas', tags=['Listas de compra'])


def _lista_propia(db, usuario, id_lista):
    """La lista solo existe para su dueno: si es de otra persona, responde 404."""
    with db.cursor() as cur:
        cur.execute('SELECT id_lista, nombre, descripcion, fecha_creacion, estado FROM lista_compra '
                    'WHERE id_lista = %s AND id_usuario = %s', (id_lista, usuario['id_usuario']))
        lista = cur.fetchone()
    if not lista:
        raise HTTPException(404, 'Lista no encontrada')
    return lista


def _items(db, id_lista):
    with db.cursor() as cur:
        cur.execute(
            '''SELECT i.id_item, i.id_presentacion, i.cantidad, pr.nombre AS producto, m.nombre AS marca,
                      c.nombre AS categoria, pe.descripcion_original AS presentacion
                 FROM item_lista i
                 JOIN presentacion pe ON pe.id_presentacion = i.id_presentacion
                 JOIN producto pr ON pr.id_producto = pe.id_producto
                 JOIN marca m ON m.id_marca = pr.id_marca
                 JOIN categoria c ON c.id_categoria = pr.id_categoria
                WHERE i.id_lista = %s ORDER BY i.id_item''', (id_lista,))
        filas = cur.fetchall()
    for f in filas:
        f['cantidad'] = float(f['cantidad'])
    return filas


@router.post('', status_code=201)
def crear_lista(datos: ListaIn, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('INSERT INTO lista_compra (id_usuario, nombre, descripcion) VALUES (%s, %s, %s)',
                    (usuario['id_usuario'], datos.nombre, datos.descripcion))
        id_lista = cur.lastrowid
    db.commit()
    return _lista_propia(db, usuario, id_lista)


@router.get('')
def mis_listas(usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT l.id_lista, l.nombre, l.descripcion, l.fecha_creacion, l.estado, '
                    'COUNT(i.id_item) AS productos FROM lista_compra l '
                    'LEFT JOIN item_lista i ON i.id_lista = l.id_lista WHERE l.id_usuario = %s '
                    'GROUP BY l.id_lista ORDER BY l.fecha_creacion DESC, l.id_lista DESC', (usuario['id_usuario'],))
        return cur.fetchall()


@router.get('/{id_lista}')
def ver_lista(id_lista: int, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    lista = _lista_propia(db, usuario, id_lista)
    return {**lista, 'items': _items(db, id_lista)}


@router.put('/{id_lista}')
def editar_lista(id_lista: int, datos: ListaUpdate, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        raise HTTPException(422, 'No se envio ningun cambio')
    if 'nombre' in cambios and cambios['nombre'] is None:
        raise HTTPException(422, 'El nombre no puede quedar vacio')
    columnas = ', '.join(f'{c} = %s' for c in cambios)   # los nombres de columna vienen del modelo, no del usuario
    with db.cursor() as cur:
        cur.execute(f'UPDATE lista_compra SET {columnas} WHERE id_lista = %s', list(cambios.values()) + [id_lista])
    db.commit()
    return _lista_propia(db, usuario, id_lista)


@router.delete('/{id_lista}', status_code=204)
def borrar_lista(id_lista: int, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    with db.cursor() as cur:
        cur.execute('DELETE FROM lista_compra WHERE id_lista = %s', (id_lista,))
    db.commit()


@router.post('/{id_lista}/items', status_code=201)
def agregar_item(id_lista: int, datos: ItemIn, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    with db.cursor() as cur:
        cur.execute('SELECT 1 FROM presentacion WHERE id_presentacion = %s', (datos.id_presentacion,))
        if not cur.fetchone():
            raise HTTPException(404, 'Presentacion no encontrada')
        try:
            cur.execute('INSERT INTO item_lista (id_lista, id_presentacion, cantidad) VALUES (%s, %s, %s)',
                        (id_lista, datos.id_presentacion, datos.cantidad))
        except pymysql.err.IntegrityError as e:
            db.rollback()
            if e.args and e.args[0] == 1062:
                raise HTTPException(409, 'Ese producto ya esta en la lista. Cambia su cantidad con PUT.')
            raise
        id_item = cur.lastrowid
    db.commit()
    return {'id_item': id_item, 'id_presentacion': datos.id_presentacion, 'cantidad': datos.cantidad}


@router.put('/{id_lista}/items/{id_item}')
def cambiar_cantidad(id_lista: int, id_item: int, datos: ItemUpdate, usuario=Depends(usuario_actual),
                     db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    with db.cursor() as cur:
        cur.execute('UPDATE item_lista SET cantidad = %s WHERE id_item = %s AND id_lista = %s',
                    (datos.cantidad, id_item, id_lista))
        cur.execute('SELECT COUNT(*) AS n FROM item_lista WHERE id_item = %s AND id_lista = %s', (id_item, id_lista))
        existe = cur.fetchone()['n']
    db.commit()
    if not existe:
        raise HTTPException(404, 'Producto no encontrado en la lista')
    return {'id_item': id_item, 'cantidad': datos.cantidad}


@router.delete('/{id_lista}/items/{id_item}', status_code=204)
def quitar_item(id_lista: int, id_item: int, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    with db.cursor() as cur:
        cur.execute('DELETE FROM item_lista WHERE id_item = %s AND id_lista = %s', (id_item, id_lista))
        borrados = cur.rowcount
    db.commit()
    if not borrados:
        raise HTTPException(404, 'Producto no encontrado en la lista')


@router.post('/{id_lista}/recomendar')
def recomendar_lista(id_lista: int, datos: RecomendarIn, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    lista = _lista_propia(db, usuario, id_lista)
    resultado = recomendar(db, usuario, id_lista, datos)
    if lista['estado'] == 'borrador':
        with db.cursor() as cur:
            cur.execute("UPDATE lista_compra SET estado = 'activa' WHERE id_lista = %s", (id_lista,))
        db.commit()
    return resultado


@router.get('/{id_lista}/recomendaciones')
def recomendaciones_guardadas(id_lista: int, usuario=Depends(usuario_actual), db=Depends(obtener_db)):
    _lista_propia(db, usuario, id_lista)
    return leer_guardadas(db, id_lista)
