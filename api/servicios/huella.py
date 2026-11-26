"""Huella de carbono estimada: producto (kg de CO2e por kg) y traslado (kg de CO2e por km).

Todo es una estimacion: los factores salen de las tablas factor_emision_producto y
medio_transporte, y las conversiones a kilos usan los supuestos de mapeo_huella.csv.
"""
import csv

from .. import config
from .util import marcas, norm

DENSIDAD_POR_DEFECTO = 1.0   # kg por litro; supuesto para liquidos si la categoria no trae otra
_conversiones = None


def _cargar_conversiones():
    """Lee kg_por_pieza y densidad_kg_por_l por categoria desde mapeo_huella.csv."""
    global _conversiones
    if _conversiones is None:
        _conversiones = {}
        if config.MAPEO_HUELLA.exists():
            with open(config.MAPEO_HUELLA, encoding='utf-8-sig', newline='') as f:
                for fila in csv.DictReader(f):
                    def numero(clave):
                        try:
                            return float((fila.get(clave) or '').replace(',', '.'))
                        except ValueError:
                            return None
                    _conversiones[norm(fila.get('categoria', ''))] = {
                        'kg_por_pieza': numero('kg_por_pieza'), 'densidad': numero('densidad_kg_por_l')}
    return _conversiones


def peso_kg(cantidad, unidad, categoria):
    """Peso en kg de una presentacion. Devuelve (kg o None, supuesto o None)."""
    if cantidad is None:
        return None, None
    c = float(cantidad)
    if unidad == 'Kg':
        return c, None
    if unidad == 'Gr':
        return c / 1000.0, None
    conv = _cargar_conversiones().get(norm(categoria), {})
    if unidad in ('Lt', 'Ml'):
        litros = c if unidad == 'Lt' else c / 1000.0
        densidad = conv.get('densidad')
        if densidad:
            return litros * densidad, None
        return litros * DENSIDAD_POR_DEFECTO, f'densidad de {DENSIDAD_POR_DEFECTO} kg/L'
    if unidad == 'Pza':
        kg_pieza = conv.get('kg_por_pieza')
        return (c * kg_pieza, None) if kg_pieza else (None, None)
    return None, None


def factores_producto(db, ids_producto):
    """{id_producto: kg de CO2e por kg}. Si hay varios factores, se promedian."""
    ids_producto = list(ids_producto)
    if not ids_producto:
        return {}
    with db.cursor() as cur:
        cur.execute(f'SELECT id_producto, AVG(kgco2_por_unidad) AS f FROM factor_emision_producto '
                    f'WHERE id_producto IN ({marcas(len(ids_producto))}) GROUP BY id_producto', ids_producto)
        return {r['id_producto']: float(r['f']) for r in cur.fetchall()}


def huella_traslado(km, factor_kgco2_km, ida_y_vuelta=True):
    if factor_kgco2_km is None:
        return None
    return km * factor_kgco2_km * (2 if ida_y_vuelta else 1)
