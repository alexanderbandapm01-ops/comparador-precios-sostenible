"""Consultas de precios: el precio mas reciente de cada presentacion en cada sucursal."""
from .util import marcas


def precios_recientes(db, ids_presentacion, ids_sucursal=None):
    """Devuelve {(id_presentacion, id_sucursal): (precio, fecha)} con el ultimo precio de cada par."""
    if not ids_presentacion:
        return {}
    ids_presentacion = list(ids_presentacion)
    filtro_suc, params_suc = '', []
    if ids_sucursal is not None:
        ids_sucursal = list(ids_sucursal)
        if not ids_sucursal:
            return {}
        filtro_suc, params_suc = f' AND id_sucursal IN ({marcas(len(ids_sucursal))})', ids_sucursal
    filtro_ext = filtro_suc.replace('id_sucursal', 'r.id_sucursal')
    sql = f'''SELECT r.id_presentacion, r.id_sucursal, r.precio, r.fecha_registro
                FROM registro_precio r
                JOIN (SELECT id_presentacion, id_sucursal, MAX(fecha_registro) AS f
                        FROM registro_precio
                       WHERE id_presentacion IN ({marcas(len(ids_presentacion))}){filtro_suc}
                       GROUP BY id_presentacion, id_sucursal) u
                  ON u.id_presentacion = r.id_presentacion AND u.id_sucursal = r.id_sucursal
                 AND u.f = r.fecha_registro
               WHERE r.id_presentacion IN ({marcas(len(ids_presentacion))}){filtro_ext}'''
    params = ids_presentacion + params_suc + ids_presentacion + params_suc
    with db.cursor() as cur:
        cur.execute(sql, params)
        return {(f['id_presentacion'], f['id_sucursal']): (float(f['precio']), f['fecha_registro'])
                for f in cur.fetchall()}
