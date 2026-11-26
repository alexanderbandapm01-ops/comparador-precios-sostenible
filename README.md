# CDPS — Comparador de Precios Sostenible

Compara precios de alimentos y bebidas entre sucursales y recomienda **una sucursal
por lista de compra**, por ahorro, huella de carbono o balance. Datos de PROFECO
(QQP, ene–feb 2026). ODS 12.

## Uso

```bash
# 1. En Workbench: ejecutar sql/comparador_precios_sostenible.sql (MySQL 8.0)
# 2. Desde etl/:
pip install -r etl/requirements.txt
python 01_limpiar.py   # revisa salida/reportes/
python 02_cargar.py    # pide la contraseña; --reiniciar borra y recarga
# 3. Desde la raíz:
pip install -r api/requirements.txt
$env:DB_PASSWORD = "tu contraseña"    # PowerShell
$env:JWT_SECRET  = "cadena aleatoria"
uvicorn api.main:app --reload         # docs en http://127.0.0.1:8000/docs
python -m pytest -q tests
```

La carpeta `web/` se sirve sola en la raíz. Los CSV originales van en `datos/`
y no se suben a Git.

## Estructura

- `api/` — FastAPI (`routers/`, `servicios/`): auth, catálogo, listas y recomendación
- `etl/` — limpieza, carga y factores de CO₂
- `sql/` — base de datos, 21 tablas
- `web/` — búsqueda, mapa, listas y recomendación
- `tests/` — 10 pruebas · `docs/` — MER y logo · `datos_ejemplo/` — Querétaro

## Pendiente

Los factores de CO₂ aún no existen (`mapeo_huella.csv` vacío, solo bici y a pie
en 0). La API avisa cuando la huella es parcial; no se inventan números.
La distancia es en línea recta.
