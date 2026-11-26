# CDPS — Comparador de Precios Sostenible

Comparador de precios de **alimentos y bebidas** entre sucursales de México, que
recomienda **una sucursal por lista de compra** según el ahorro, la huella de carbono
estimada o un balance de ambos. Limitado a Querétaro en la presentación y en los
datos de ejemplo. Alineado con el **ODS 12** (producción y consumo responsables),
con apoyo en ODS 9, 11 y 15.

> **Datos:** PROFECO, *Quién es Quién en los Precios* (QQP): 3 CSV, 1,583,283 filas,
> 15 columnas, del 2 de enero al 13 de febrero de 2026. Tras la limpieza quedan
> 757,363 precios, 1,504 presentaciones, 1,421 sucursales y 3 fuentes.
> **Querétaro (datos de ejemplo):** 26 sucursales, todas en Santiago de Querétaro,
> 9,651 precios y 1,011 presentaciones.

## Cómo funciona

```
3 CSV ──> 01_limpiar.py ──> 02_cargar.py ──> MySQL 8 ──> API (FastAPI) ──> web/
              limpia          carga las        21 tablas    reglas de        (esta repo)
              y filtra        tablas                        negocio
```

El navegador nunca habla con MySQL: solo con la API. La API calcula precios
actuales, distancias, huella y la recomendación.

### La recomendación: una sucursal por lista

`POST /listas/{id}/recomendar` (modo `ahorro`, `ecologico` o `balance` 50/50):

1. Candidatas: sucursales dentro del radio.
2. Se queda con las que cubren **más productos de la lista**.
3. Costo = precio más reciente × cantidad. Huella = productos + traslado
   (ida y vuelta, una sola vez, repartido por partes iguales entre los productos).
4. Gana la de mejor puntaje. La respuesta trae esa sucursal, el detalle por
   producto, `otras_sucursales` (hasta 3, solo como comparación) y `avisos`.
5. Guarda una fila por producto en `recomendacion`, todas con la misma sucursal,
   y la lista pasa a `activa`.

La distancia es **en línea recta** (limitación que se declara en el informe).
La ubicación del usuario se resuelve en este orden: coordenadas del dispositivo,
ubicación guardada, centro de las sucursales de su código postal (si hay al menos 3),
centro de su municipio.

## Estructura

```
comparador-precios-sostenible/
├── api/            FastAPI: main, config, db, seguridad (bcrypt+JWT), esquemas
│   ├── routers/    auth, catalogo, listas
│   └── servicios/  geo, huella, precios, recomendador, util
├── etl/            01_limpiar.py, 02_cargar.py, 03_cargar_factores.py,
│                   mapeo_huella.csv, factores_transporte.csv, factores_producto.csv
├── tests/          test_api.py (10 pruebas contra la base real)
├── sql/            comparador_precios_sostenible.sql (21 tablas, MySQL 8.0)
├── web/            página: búsqueda, mapa, listas (CRUD) y recomendación
├── docs/           diagramaMER.pdf, logo-cdps.png
├── datos_ejemplo/  Querétaro: sucursales, precios y presentaciones (parquet + CSV)
├── datos/          <- los 3 CSV originales (NO se suben a Git)
└── salida/         <- la crea 01_limpiar.py (no se sube)
```

## Puesta en marcha

Requisitos: Python 3.12, **MySQL 8.0** (no MariaDB: el script usa `POINT` con
`SRID 4326`) y MySQL Workbench.

```bash
# 1. Base de datos (Workbench): ejecutar sql/comparador_precios_sostenible.sql
# 2. Limpieza y carga (desde etl/)
pip install -r etl/requirements.txt
python 01_limpiar.py            # revisa salida/reportes/ antes de cargar
python 02_cargar.py             # pide la contrasena; --reiniciar borra y recarga
python 03_cargar_factores.py    # cuando haya factores con fuente
# 3. API (desde la raíz del proyecto)
pip install -r api/requirements.txt
$env:DB_PASSWORD = "tu contrasena de MySQL"   # PowerShell
$env:JWT_SECRET  = "cadena larga y aleatoria" # python -c "import secrets; print(secrets.token_urlsafe(48))"
uvicorn api.main:app --reload   # docs en http://127.0.0.1:8000/docs
# 4. Pruebas (usan la base cargada; crean y borran usuarios ficticios)
python -m pytest -q tests
```

La carpeta `web/` se sirve sola desde la raíz cuando existe (`http://127.0.0.1:8000/`).
La ubicación del navegador necesita HTTPS en producción.

## Estado y pendientes honestos

- **Factores de CO₂: pendientes.** `kgco2e_por_kg` está vacío en las 42 categorías
  de `mapeo_huella.csv`, `factores_producto.csv` está vacío y en
  `factores_transporte.csv` solo Bicicleta y A pie tienen factor (0); Auto y
  Transporte público están vacíos. Mientras tanto la API devuelve la recomendación
  con huella parcial y lo avisa en `avisos` y `huella_completa`. **No se rellenan
  con números inventados.** Fuente sugerida: Poore y Nemecek (2018), vía Our World
  in Data, verificando cada valor en la tabla original.
- **Alcance:** solo alimentos y bebidas, por categoría en `mapeo_huella.csv`
  (`en_alcance`: `si` / `no` / `tal_vez`). Hoy 29 en `si` (incluye Productos de
  Temporada, 17 productos), 2 en `tal_vez` (Cerveza, Vinos y Licores), 11 en `no`.
- **Archivos recreados (2026-11-25):** `etl/01_limpiar.py`, `etl/02_cargar.py` y
  `web/` no estaban en los archivos entregados y se reconstruyeron a partir del
  LEEME, del notebook de análisis y de los parquet limpios de referencia. También
  se añadieron los `__init__.py` que faltaban y se reacomodaron los archivos de la
  API en `api/routers/` y `api/servicios/`, que es la estructura que sus imports
  esperan. El resto del código (API, `03_cargar_factores.py`, tests, SQL) es el
  entregado por el equipo, sin cambios salvo la organización en carpetas.
- **Seguridad pendiente para un sitio real:** limitar intentos de inicio de sesión
  y usar HTTPS en el VPS. Las cuentas son ficticias; la ubicación y la fecha de
  nacimiento son datos personales: no se suben datos reales de usuarios.
- No se sabe con certeza qué significan Q1 y Q2 en los nombres de los CSV: no se
  afirma en el informe sin confirmarlo.

## Identidad

**CDPS — Comparador de Precios Sostenible.** Logo: hoja verde con el texto CDPS y
“Datos · Mapas · Querétaro”. Colores: verde pastel y azul pastel.
