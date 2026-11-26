"""Comparador de precios sostenible - API.

Arranque (desde la carpeta del proyecto):
    uvicorn api.main:app --reload
Documentacion interactiva: http://127.0.0.1:8000/docs
"""
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .db import obtener_db
from .routers import auth, catalogo, listas

app = FastAPI(
    title='Comparador de precios sostenible',
    version='0.1.0',
    description='Compara precios de alimentos y bebidas entre sucursales (datos de PROFECO, QQP) y '
                'recomienda donde comprar segun el ahorro y la huella de carbono estimada.')

if config.CORS_ORIGENES:
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGENES, allow_methods=['*'],
                       allow_headers=['*'])

app.include_router(auth.router)
app.include_router(catalogo.router)
app.include_router(listas.router)


@app.get('/salud', tags=['Estado'])
def salud(db=Depends(obtener_db)):
    with db.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS precios FROM registro_precio')
        return {'estado': 'ok', 'precios_cargados': cur.fetchone()['precios']}


# Si existe la carpeta web/ (la pagina), se sirve desde la raiz
_web = config.RAIZ / 'web'
if _web.is_dir():
    app.mount('/', StaticFiles(directory=_web, html=True), name='web')
