/* CDPS web — habla solo con la API, nunca con MySQL directamente. */
const API = ""; // mismo origen cuando FastAPI sirve web/; si no, pon "http://127.0.0.1:8000"
const $ = (id) => document.getElementById(id);
let token = localStorage.getItem("cdps_token") || "";
let ubic = { lat: null, lon: null, cp: "" };
let mapa, capaMarcadores;

const headers = (json = true) => {
  const h = {};
  if (json) h["Content-Type"] = "application/json";
  if (token) h["Authorization"] = "Bearer " + token;
  return h;
};
async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    const texto = (await r.text()).slice(0, 300);
    let mensaje = texto;
    try { mensaje = JSON.parse(texto).detail || texto; } catch { /* el mensaje ya es texto */ }
    throw new Error(mensaje);
  }
  return r.status === 204 ? null : r.json();
}
const dinero = (n) => (n == null ? "—" : "$" + Number(n).toFixed(2));

async function cargarYo() {
  if (!token) return;
  try {
    const yo = await api("/auth/yo", { headers: headers(false) });
    $("auth-estado").textContent = `Sesión: ${yo.nombre} ${yo.apellido_paterno || ""}`.trim();
  } catch { $("auth-estado").textContent = "Sesión iniciada"; }
}

function refrescarAuth() {
  $("auth-estado").textContent = token ? "Sesión iniciada" : "Sin sesión";
  $("btn-salir").hidden = !token;
  if (token) cargarYo();
}

// Listas de estado y municipio para el registro (la API ya las expone)
let estadosCargados = false;
async function cargarEstados() {
  if (estadosCargados) return;
  try {
    const estados = await api("/estados");
    $("select-estado").innerHTML = `<option value="">Elige tu estado</option>` + estados.map((e) =>
      `<option value="${e.id_estado}">${e.nombre}</option>`).join("");
    estadosCargados = true;
    const qro = estados.find((e) => /quer.taro/i.test(e.nombre));
    if (qro) { $("select-estado").value = qro.id_estado; await cargarMunicipios(); }
  } catch { $("select-estado").innerHTML = `<option value="">No se pudieron cargar</option>`; }
}
async function cargarMunicipios() {
  const idEstado = $("select-estado").value;
  $("select-municipio").innerHTML = `<option value="">Cargando municipios…</option>`;
  if (!idEstado) { $("select-municipio").innerHTML = `<option value="">Elige un estado primero</option>`; return; }
  try {
    const municipios = await api(`/municipios?id_estado=${idEstado}`);
    $("select-municipio").innerHTML = `<option value="">Elige tu municipio</option>` + municipios.map((m) =>
      `<option value="${m.id_municipio}">${m.nombre}</option>`).join("");
    const qro = municipios.find((m) => /quer.taro/i.test(m.nombre));
    if (qro) $("select-municipio").value = qro.id_municipio;
  } catch { $("select-municipio").innerHTML = `<option value="">No se pudieron cargar</option>`; }
}
$("select-estado").onchange = cargarMunicipios;

// Entrar con Google (solo si el servidor tiene Client ID configurado)
let googleToken = "";
let googleListo = false;
async function cargarGoogle() {
  if (googleListo) return;
  try {
    const cfg = await api("/auth/google-config");
    if (!cfg.client_id) return; // Google no configurado: no se muestra el boton
    await new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
    google.accounts.id.initialize({ client_id: cfg.client_id, callback: onGoogle });
    google.accounts.id.renderButton($("google-btn"),
      { theme: "outline", size: "large", text: "signin_with", locale: "es" });
    googleListo = true;
  } catch { /* sin Google, el login normal sigue funcionando */ }
}
async function onGoogle(respuesta) {
  try {
    const r = await api("/auth/google", { method: "POST", headers: headers(),
      body: JSON.stringify({ id_token: respuesta.credential }) });
    if (r.registro_incompleto) {
      // Cuenta nueva: Google da nombre y correo; faltan fecha de nacimiento y municipio
      googleToken = respuesta.credential;
      const f = $("form-auth");
      f.nombre.value = r.nombre || "";
      f.apellido_paterno.value = r.apellido_paterno || "";
      f.email.value = r.email || "";
      f.contrasena.required = false; f.contrasena.hidden = true;
      document.querySelector('#form-auth button[value="registro"]').textContent = "Completar registro con Google";
      $("auth-error").textContent = "Casi listo: elige tu municipio y tu fecha de nacimiento para completar tu cuenta.";
      return;
    }
    entrarConToken(r.token);
  } catch (err) { $("auth-error").textContent = "Error: " + err.message; }
}
function entrarConToken(nuevoToken) {
  token = nuevoToken;
  localStorage.setItem("cdps_token", token);
  restablecerFormAuth();
  $("dlg-auth").close(); refrescarAuth(); cargarListas();
}
function restablecerFormAuth() {
  googleToken = "";
  const f = $("form-auth");
  f.contrasena.required = true; f.contrasena.hidden = false;
  document.querySelector('#form-auth button[value="registro"]').textContent = "Registrarme";
}

$("btn-login").onclick = () => { $("auth-error").textContent = ""; cargarEstados(); $("dlg-auth").showModal(); cargarGoogle(); };
$("btn-salir").onclick = () => { token = ""; localStorage.removeItem("cdps_token"); refrescarAuth(); };
$("form-auth").addEventListener("click", async (e) => {
  const accion = e.target.value;
  if (!accion) return;
  if (accion === "cancelar") { restablecerFormAuth(); $("dlg-auth").close(); return; }
  const f = new FormData($("form-auth"));
  if (accion === "registro" && !f.get("id_municipio")) {
    $("auth-error").textContent = "Error: elige tu estado y tu municipio.";
    return;
  }
  try {
    if (accion === "registro" && googleToken) {
      // Cuenta nueva con Google: completar con fecha de nacimiento y municipio
      if (!f.get("fecha_nacimiento")) {
        $("auth-error").textContent = "Error: elige tu fecha de nacimiento.";
        return;
      }
      const r = await api("/auth/google", { method: "POST", headers: headers(),
        body: JSON.stringify({ id_token: googleToken, fecha_nacimiento: f.get("fecha_nacimiento"),
          id_municipio: Number(f.get("id_municipio")) }) });
      entrarConToken(r.token);
      return;
    }
    if (accion === "registro") {
      const cuerpo = { nombre: f.get("nombre") || "Usuario", apellido_paterno: f.get("apellido_paterno") || "Prueba",
        fecha_nacimiento: f.get("fecha_nacimiento"), email: f.get("email"), contrasena: f.get("contrasena"),
        id_municipio: Number(f.get("id_municipio")) };
      if (f.get("apellido_materno")) cuerpo.apellido_materno = f.get("apellido_materno");
      if (ubic.lat) { cuerpo.latitud = ubic.lat; cuerpo.longitud = ubic.lon; }
      const r = await api("/auth/registro", { method: "POST", headers: headers(), body: JSON.stringify(cuerpo) });
      entrarConToken(r.token);
    } else {
      const r = await api("/auth/login", { method: "POST", headers: headers(),
        body: JSON.stringify({ email: f.get("email"), contrasena: f.get("contrasena") }) });
      entrarConToken(r.token);
    }
  } catch (err) { $("auth-error").textContent = "Error: " + err.message; }
});

// Ubicación: del navegador (necesita HTTPS en producción) o por código postal
$("btn-ubicacion").onclick = () => navigator.geolocation.getCurrentPosition(
  (p) => { ubic = { lat: p.coords.latitude, lon: p.coords.longitude, cp: "" };
    $("ubicacion-texto").textContent = `Ubicación: ${ubic.lat.toFixed(5)}, ${ubic.lon.toFixed(5)} (dispositivo)`; },
  () => { $("ubicacion-texto").textContent = "No se pudo obtener la ubicación: permite el acceso o usa el código postal."; });
$("btn-cp").onclick = () => { ubic = { lat: null, lon: null, cp: $("input-cp").value.trim() };
  $("ubicacion-texto").textContent = `Ubicación aproximada: centro de las sucursales del CP ${ubic.cp}`; };

// Catálogo y búsqueda
async function cargarCatalogos() {
  const cats = await api("/categorias");
  cats.forEach((c) => { const o = document.createElement("option"); o.value = c.nombre; o.textContent = c.nombre; $("select-categoria").appendChild(o); });
  const medios = await api("/medios-transporte");
  medios.forEach((m) => { const o = document.createElement("option"); o.value = m.id_transporte;
    o.textContent = `${m.nombre} (${m.factor_emision_kgco2_km ?? "sin factor"} kgCO2/km)`; $("select-transporte").appendChild(o); });
}
$("btn-buscar").onclick = async () => {
  const q = new URLSearchParams({ q: $("input-q").value, categoria: $("select-categoria").value });
  const data = await api("/presentaciones?" + q);
  $("resultados").innerHTML = data.resultados.map((r) => `
    <div class="producto"><strong>${r.producto}</strong> · ${r.marca} · ${r.descripcion_original}
    <br>Precio: mín ${dinero(r.precio_minimo)} · prom ${dinero(r.precio_promedio)} · máx ${dinero(r.precio_maximo)} (${r.sucursales_con_precio} sucursales)
    <br><button onclick="verPrecios(${r.id_presentacion})">Ver precios por sucursal</button>
    <button onclick="agregarALista(${r.id_presentacion})">+ A la lista</button></div>`).join("") || "Sin resultados.";
};
window.verPrecios = async (id) => {
  const precios = await api(`/presentaciones/${id}/precios`);
  $("detalle").innerHTML = "<h3>Precios por sucursal (del más barato al más caro)</h3>" + precios.slice(0, 10).map((p) => `
    <div class="sucursal"><strong>${dinero(p.precio)}</strong> · ${p.nombre_comercial} (${p.cadena}) — ${p.municipio}, ${p.estado}
    <br>${p.calle}, ${p.colonia}, CP ${p.codigo_postal} · ${p.fecha_registro}</div>`).join("");
};

// Mapa y sucursales cercanas
function initMapa() {
  mapa = L.map("mapa").setView([20.59, -100.39], 12); // Santiago de Querétaro
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap" }).addTo(mapa);
  capaMarcadores = L.layerGroup().addTo(mapa);
}
$("btn-cercanas").onclick = async () => {
  const q = new URLSearchParams({ radio_km: $("input-radio").value });
  if (ubic.lat) { q.set("latitud", ubic.lat); q.set("longitud", ubic.lon); }
  else if (ubic.cp) q.set("codigo_postal", ubic.cp);
  const data = await api("/sucursales/cercanas?" + q);
  capaMarcadores.clearLayers();
  if (data.ubicacion) L.marker([data.ubicacion.latitud, data.ubicacion.longitud]).addTo(capaMarcadores).bindPopup("Tú (aprox.)");
  data.sucursales.forEach((s) => L.marker([s.latitud, s.longitud]).addTo(capaMarcadores)
    .bindPopup(`<strong>${s.nombre_comercial}</strong><br>${s.km} km · ${s.cadena}`));
  $("lista-cercanas").innerHTML = data.sucursales.map((s) =>
    `<li>${s.nombre_comercial} (${s.cadena}) — ${s.km} km · ${s.calle}, ${s.colonia}</li>`).join("");
};

// Listas (CRUD) y recomendación: UNA sucursal por lista
async function cargarListas() {
  if (!token) return;
  const listas = await api("/listas", { headers: headers(false) });
  $("select-lista").innerHTML = listas.map((l) => `<option value="${l.id_lista}">${l.nombre} (${l.productos} productos)</option>`).join("");
  if (listas.length) verLista();
}
$("btn-crear-lista").onclick = async () => {
  const l = await api("/listas", { method: "POST", headers: headers(), body: JSON.stringify({ nombre: $("input-lista").value || "Mi lista" }) });
  await cargarListas(); $("select-lista").value = l.id_lista; verLista();
};
$("select-lista").onchange = verLista;
async function verLista() {
  const id = $("select-lista").value; if (!id) return;
  const l = await api(`/listas/${id}`, { headers: headers(false) });
  $("items-lista").innerHTML = l.items.map((i) => `
    <div class="item">${i.producto} · ${i.marca} · ${i.presentacion} — cantidad ${i.cantidad}
    <button onclick="quitarItem(${i.id_item})">Quitar</button></div>`).join("") || "Lista vacía.";
}
window.agregarALista = async (idPresentacion) => {
  const id = $("select-lista").value;
  if (!id) { alert("Primero crea una lista."); return; }
  await api(`/listas/${id}/items`, { method: "POST", headers: headers(), body: JSON.stringify({ id_presentacion: idPresentacion, cantidad: 1 }) });
  verLista();
};
window.quitarItem = async (idItem) => {
  await api(`/listas/${$("select-lista").value}/items/${idItem}`, { method: "DELETE", headers: headers(false) });
  verLista();
};
$("btn-recomendar").onclick = async () => {
  const id = $("select-lista").value; if (!id) { alert("Elige una lista."); return; }
  const cuerpo = { modo: $("select-modo").value, radio_km: Number($("input-radio").value) };
  if ($("select-transporte").value) cuerpo.id_medio_transporte = Number($("select-transporte").value);
  if (ubic.lat) { cuerpo.latitud = ubic.lat; cuerpo.longitud = ubic.lon; }
  else if (ubic.cp) cuerpo.codigo_postal = ubic.cp;
  const r = await api(`/listas/${id}/recomendar`, { method: "POST", headers: headers(), body: JSON.stringify(cuerpo) });
  const s = r.sucursal_recomendada;
  $("recomendacion").innerHTML = `
    <div class="recomendada"><h3>Compra todo en: ${s.nombre_comercial} (${s.cadena})</h3>
    ${s.calle}, ${s.colonia}, CP ${s.codigo_postal} · a ${s.distancia_km} km<br>
    Costo total ${dinero(r.resumen.costo_total)} · ahorro estimado ${dinero(r.resumen.ahorro_estimado)} ·
    huella total ${r.resumen.huella_total_kgco2e} kgCO2e ${r.resumen.huella_completa ? "" : "(parcial)"}<br>
    Productos cubiertos: ${r.resumen.productos_cubiertos} de ${r.resumen.productos_en_la_lista} ·
    sucursales comparadas: ${r.resumen.sucursales_comparadas}</div>
    ${r.avisos.map((a) => `<div class="aviso">${a}</div>`).join("")}
    <h4>Otras sucursales comparadas</h4>
    ${r.otras_sucursales.map((o) => `<div>${o.nombre_comercial} — ${o.distancia_km} km · ${dinero(o.costo_total)} · ${o.huella_total_kgco2e} kgCO2e</div>`).join("")}
    <h4>Detalle por producto</h4>
    ${r.items.map((i) => `<div>${i.producto} · ${i.presentacion} — ${dinero(i.precio_unitario)} c/u, subtotal ${dinero(i.subtotal)}</div>`).join("")}`;
};

refrescarAuth(); initMapa(); cargarCatalogos(); cargarListas();
