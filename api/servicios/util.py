"""Utilidades pequenas."""
import re
import unicodedata


def norm(texto):
    """Compara textos como MySQL: sin mayusculas, acentos ni espacios repetidos."""
    t = unicodedata.normalize('NFKD', str(texto))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', t).strip().casefold()


def like_seguro(texto):
    """Escapa % y _ para usar el texto del usuario en un LIKE."""
    return '%' + texto.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def marcas(n):
    """'%s, %s, ...' para listas IN con parametros."""
    return ','.join(['%s'] * n)


def a_float(valor):
    return None if valor is None else float(valor)
