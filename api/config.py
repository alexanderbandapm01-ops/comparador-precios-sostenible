"""Configuracion de la API (variables de entorno)."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

DB_HOST = os.getenv('DB_HOST', '127.0.0.1')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'comparador_precios_sostenible')
DB_SOCKET = os.getenv('DB_SOCKET')

# Obligatoria para iniciar sesion (cadena larga y aleatoria, nunca en el codigo)
JWT_SECRET = os.getenv('JWT_SECRET')
JWT_MINUTOS = int(os.getenv('JWT_MINUTOS', '120'))

# Client ID publico de Google para "Entrar con Google" (no es un secreto:
# tambien va en la pagina). Vacio = el boton no se muestra.
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID', '')

# Origenes permitidos si la pagina se sirve desde otro dominio, separados por coma
CORS_ORIGENES = [o.strip() for o in os.getenv('CORS_ORIGENES', '').split(',') if o.strip()]

# Archivo con los parametros de conversion a kilos (kg_por_pieza, densidad_kg_por_l)
MAPEO_HUELLA = Path(os.getenv('MAPEO_HUELLA', RAIZ / 'etl' / 'mapeo_huella.csv'))
