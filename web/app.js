/* CDPS web — habla solo con la API, nunca con MySQL directamente. */
const API = ""; // mismo origen cuando FastAPI sirve web/; si no, pon "http://127.0.0.1:8000"
const $ = (id) => document.getElementById(id);
let token = localStorage.getItem("cdps_token") || "";
let ubic = { lat: null, lon: null, cp: "" };
let mapa, capaMarcadores;
let categorias = []; // /categorias, para los atajos y el onboarding

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
const kg = (n) => (n == null ? "—" : Number(n).toFixed(2) + " kg CO2e");

// ---------- Vistas (Buscar / Mi lista / Mapa) ----------
function mostrarVista(nombre) {
  for (const v of ["buscar", "lista", "mapa"]) {
    $("vista-" + v).hidden = v !== nombre;
    document.querySelector(`#nav-vistas button[data-vista="${v}"]`).classList.toggle("nav-activa", v === nombre);
  }
  if (nombre === "mapa") { asegurarMapa(); if (mapa) mapa.invalidateSize(); }
  if (location.hash !== "#/" + nombre) history.replaceState(null, "", "#/" + nombre);
}
document.querySelectorAll("#nav-vistas button").forEach((b) =>
  b.addEventListener("click", () => mostrarVista(b.dataset.vista)));
window.addEventListener("hashchange", () => {
  const v = location.hash.replace("#/", "") || "buscar";
  if (["buscar", "lista", "mapa"].includes(v)) mostrarVista(v);
});

// ---------- Sesión ----------
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
  $("lista-solo-cuenta").hidden = !!token;
  $("lista-contenido").hidden = !token;
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
let googleCargado = false;
const googleRenderizado = {};
async function cargarGoogle() {
  if (googleCargado) return true;
  try {
    const cfg = await api("/auth/google-config");
    if (!cfg.client_id) return false; // Google no configurado: no se muestra el boton
    await new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.onload = res; s.onerror = rej;
      document.head.appendChild(s);
    });
    google.accounts.id.initialize({ client_id: cfg.client_id, callback: onGoogle });
    googleCargado = true;
    return true;
  } catch { return false; } // sin Google, el login normal sigue funcionando
}
async function renderGoogleBoton(id) {
  if (googleRenderizado[id] || !$(id)) return;
  if (await cargarGoogle()) {
    google.accounts.id.renderButton($(id),
      { theme: "outline", size: "large", text: "signin_with", locale: "es" });
    googleRenderizado[id] = true;
  }
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
      if ($("dlg-bienvenida").open) $("dlg-bienvenida").close();
      $("auth-error").textContent = "Casi listo: elige tu municipio y tu fecha de nacimiento para completar tu cuenta.";
      $("dlg-auth").showModal(); cargarEstados();
      return;
    }
    entrarConToken(r.token);
  } catch (err) { $("auth-error").textContent = "Error: " + err.message; }
}
function entrarConToken(nuevoToken) {
  token = nuevoToken;
  localStorage.setItem("cdps_token", token);
  localStorage.setItem("cdps_modo", "cuenta");
  restablecerFormAuth();
  if ($("dlg-auth").open) $("dlg-auth").close();
  if ($("dlg-bienvenida").open) $("dlg-bienvenida").close();
  refrescarAuth(); cargarListas(); mostrarOnboarding();
}
function restablecerFormAuth() {
  googleToken = "";
  const f = $("form-auth");
  f.contrasena.required = true; f.contrasena.hidden = false;
  document.querySelector('#form-auth button[value="registro"]').textContent = "Registrarme";
}

function abrirAuth(mensaje) {
  if (mensaje) $("auth-error").textContent = mensaje;
  else $("auth-error").textContent = "";
  cargarEstados(); $("dlg-auth").showModal(); renderGoogleBoton("google-btn");
}
$("btn-login").onclick = () => abrirAuth();
$("btn-lista-login").onclick = () => abrirAuth();
$("btn-salir").onclick = () => {
  token = ""; localStorage.removeItem("cdps_token");
  localStorage.removeItem("cdps_modo"); refrescarAuth(); mostrarVista("buscar");
};
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

// ---------- Puerta de entrada y onboarding ----------
function mostrarBienvenida() {
  if (token) return; // con sesión no hay puerta
  if (localStorage.getItem("cdps_modo")) return; // ya eligió antes (invitado o cuenta)
  $("dlg-bienvenida").showModal();
  renderGoogleBoton("google-btn-bienvenida");
}
$("btn-gate-correo").onclick = () => { $("dlg-bienvenida").close(); abrirAuth(); };
$("btn-invitado").onclick = () => {
  localStorage.setItem("cdps_modo", "invitado");
  $("dlg-bienvenida").close();
  mostrarOnboarding();
};

let onboardingMostrado = false;
function mostrarOnboarding() {
  if (onboardingMostrado || localStorage.getItem("cdps_onboarding")) return;
  onboardingMostrado = true;
  construirChipsOnboarding();
  $("dlg-onboarding").showModal();
}
function construirChipsOnboarding() {
  const elegidas = new Set(JSON.parse(localStorage.getItem("cdps_categorias") || "[]"));
  $("chips-onboarding").innerHTML = categorias.map((c) =>
    `<button type="button" class="chip${elegidas.has(c.nombre) ? " chip-activo" : ""}" data-cat="${c.nombre}">${c.nombre}</button>`).join("");
  $("chips-onboarding").querySelectorAll(".chip").forEach((b) =>
    b.addEventListener("click", () => b.classList.toggle("chip-activo")));
}
function guardarOnboarding() {
  const elegidas = [...$("chips-onboarding").querySelectorAll(".chip-activo")].map((b) => b.dataset.cat);
  localStorage.setItem("cdps_categorias", JSON.stringify(elegidas));
  localStorage.setItem("cdps_onboarding", "1");
  $("dlg-onboarding").close();
  aplicarChipsBusqueda();
}
$("btn-onb-continuar").onclick = guardarOnboarding;
$("btn-onb-saltar").onclick = () => {
  localStorage.setItem("cdps_onboarding", "1");
  $("dlg-onboarding").close();
};
function aplicarChipsBusqueda() {
  const elegidas = JSON.parse(localStorage.getItem("cdps_categorias") || "[]");
  $("chips-categorias").innerHTML = elegidas.map((c) =>
    `<button type="button" class="chip" data-cat="${c}">${c}</button>`).join("");
  $("chips-categorias").querySelectorAll(".chip").forEach((b) =>
    b.addEventListener("click", () => {
      $("select-categoria").value = b.dataset.cat;
      $("input-q").value = "";
      buscar();
    }));
}

// ---------- Ubicación ----------
function fijarUbicacion(lat, lon, texto) {
  ubic = { lat, lon, cp: "" };
  $("ubicacion-texto").textContent = texto;
  $("onb-ubicacion-texto").textContent = texto;
  if (token) api("/auth/ubicacion", { method: "PUT", headers: headers(),
    body: JSON.stringify({ latitud: lat, longitud: lon }) }).catch(() => {});
}
function pedirUbicacionDispositivo() {
  navigator.geolocation.getCurrentPosition(
    (p) => fijarUbicacion(p.coords.latitude, p.coords.longitude,
      `Ubicación: ${p.coords.latitude.toFixed(5)}, ${p.coords.longitude.toFixed(5)} (dispositivo)`),
    () => {
      $("ubicacion-texto").textContent = "No se pudo obtener la ubicación: permite el acceso o usa el código postal.";
      $("onb-ubicacion-texto").textContent = "No se pudo obtener la ubicación: permite el acceso o usa el código postal.";
    });
}
$("btn-ubicacion").onclick = pedirUbicacionDispositivo;
$("btn-onb-ubicacion").onclick = pedirUbicacionDispositivo;
function usarCP(valor) {
  ubic = { lat: null, lon: null, cp: valor.trim() };
  const texto = `Ubicación aproximada: centro de las sucursales del CP ${ubic.cp}`;
  $("ubicacion-texto").textContent = texto;
  $("onb-ubicacion-texto").textContent = texto;
}
$("btn-cp").onclick = () => usarCP($("input-cp").value);
$("btn-onb-cp").onclick = () => usarCP($("input-onb-cp").value);

// ---------- Catálogo y búsqueda ----------
async function cargarCatalogos() {
  categorias = await api("/categorias");
  categorias.forEach((c) => { const o = document.createElement("option"); o.value = c.nombre; o.textContent = c.nombre; $("select-categoria").appendChild(o); });
  const medios = await api("/medios-transporte");
  medios.forEach((m) => { const o = document.createElement("option"); o.value = m.id_transporte;
    o.textContent = `${m.nombre} (${m.factor_emision_kgco2_km ?? "sin factor"} kgCO2/km)`; $("select-transporte").appendChild(o); });
  aplicarChipsBusqueda();
}
async function buscar() {
  const q = new URLSearchParams({ q: $("input-q").value, categoria: $("select-categoria").value });
  const data = await api("/presentaciones?" + q);
  $("resultados").innerHTML = data.resultados.map((r) => `
    <div class="producto"><strong>${r.producto}</strong> · ${r.marca} · ${r.descripcion_original}
    <br>Precio: mín ${dinero(r.precio_minimo)} · prom ${dinero(r.precio_promedio)} · máx ${dinero(r.precio_maximo)} (${r.sucursales_con_precio} sucursales)
    <br><button onclick="verPrecios(${r.id_presentacion})">Ver precios por sucursal</button>
    <button onclick="agregarALista(${r.id_presentacion})">+ A la lista</button></div>`).join("") || "Sin resultados.";
}
$("btn-buscar").onclick = buscar;
window.verPrecios = async (id) => {
  const precios = await api(`/presentaciones/${id}/precios`);
  $("detalle").innerHTML = "<h3>Precios por sucursal (del más barato al más caro)</h3>" + precios.slice(0, 10).map((p) => `
    <div class="sucursal"><strong>${dinero(p.precio)}</strong> · ${p.nombre_comercial} (${p.cadena}) — ${p.municipio}, ${p.estado}
    <br>${p.calle}, ${p.colonia}, CP ${p.codigo_postal} · ${p.fecha_registro}</div>`).join("");
};

// ---------- Mapa y sucursales cercanas ----------
function asegurarMapa() {
  if (mapa) return;
  if (typeof L === "undefined") { // Leaflet no cargó (sin conexión): no romper la página
    $("mapa-mensaje").textContent = "No se pudo cargar el mapa: revisa tu conexión a internet e inténtalo de nuevo.";
    return;
  }
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap" }).addTo(mapa);
  capaMarcadores = L.layerGroup().addTo(mapa);
}
$("btn-cercanas").onclick = async () => {
  const q = new URLSearchParams({ radio_km: $("input-radio").value });
  if (ubic.lat) { q.set("latitud", ubic.lat); q.set("longitud", ubic.lon); }
  else if (ubic.cp) q.set("codigo_postal", ubic.cp);
  try {
    const data = await api("/sucursales/cercanas?" + q);
    asegurarMapa();
    capaMarcadores.clearLayers();
    const limites = [];
    if (data.ubicacion) {
      L.marker([data.ubicacion.latitud, data.ubicacion.longitud]).addTo(capaMarcadores).bindPopup("Tú (aprox.)");
      limites.push([data.ubicacion.latitud, data.ubicacion.longitud]);
    }
    data.sucursales.forEach((s) => {
      L.marker([s.latitud, s.longitud]).addTo(capaMarcadores)
        .bindPopup(`<strong>${s.nombre_comercial}</strong><br>${s.km} km · ${s.cadena}`);
      limites.push([s.latitud, s.longitud]);
    });
    if (limites.length > 1) mapa.fitBounds(limites, { padding: [24, 24] });
    else if (limites.length === 1) mapa.setView(limites[0], 14);
    $("mapa-mensaje").textContent = `${data.sucursales.length} sucursales a menos de ${$("input-radio").value} km.`;
    $("lista-cercanas").innerHTML = data.sucursales.map((s) =>
      `<li>${s.nombre_comercial} (${s.cadena}) — ${s.km} km · ${s.calle}, ${s.colonia}</li>`).join("");
  } catch (err) {
    $("mapa-mensaje").textContent = "Para ver el mapa necesito tu ubicación: usa 'Usar mi ubicación' o escribe tu código postal en Buscar.";
  }
};

// ---------- Listas (CRUD) y recomendación: UNA sucursal por lista ----------
async function cargarListas() {
  if (!token) return;
  const listas = await api("/listas", { headers: headers(false) });
  $("select-lista").innerHTML = listas.map((l) => `<option value="${l.id_lista}">${l.nombre} (${l.productos} productos)</option>`).join("");
  if (listas.length) verLista();
  else { $("items-lista").innerHTML = "Aún no tienes listas: crea una y agrega productos desde Buscar."; actualizarBadge(0); }
}
$("btn-crear-lista").onclick = async () => {
  const l = await api("/listas", { method: "POST", headers: headers(), body: JSON.stringify({ nombre: $("input-lista").value || "Mi lista" }) });
  await cargarListas(); $("select-lista").value = l.id_lista; verLista();
};
$("select-lista").onchange = verLista;
function actualizarBadge(n) {
  $("badge-lista").hidden = n === 0;
  $("badge-lista").textContent = n;
}
async function verLista() {
  const id = $("select-lista").value; if (!id) return;
  const l = await api(`/listas/${id}`, { headers: headers(false) });
  actualizarBadge(l.items.length);
  $("items-lista").innerHTML = l.items.map((i) => `
    <div class="item"><strong>${i.producto}</strong> · ${i.marca} · ${i.presentacion}
    <br><button onclick="cambiarCantidad(${i.id_item}, ${i.cantidad - 1})">−</button>
    cantidad ${i.cantidad}
    <button onclick="cambiarCantidad(${i.id_item}, ${i.cantidad + 1})">+</button>
    <button onclick="quitarItem(${i.id_item})">Quitar</button></div>`).join("") || "Lista vacía.";
}
window.cambiarCantidad = async (idItem, nueva) => {
  const id = $("select-lista").value;
  if (nueva <= 0) { await quitarItem(idItem); return; }
  await api(`/listas/${id}/items/${idItem}`, { method: "PUT", headers: headers(),
    body: JSON.stringify({ cantidad: nueva }) });
  verLista();
};
window.agregarALista = async (idPresentacion) => {
  if (!token) { abrirAuth("Inicia sesión o regístrate para guardar productos en tu lista."); return; }
  const id = $("select-lista").value;
  if (!id) { alert("Primero crea una lista."); return; }
  try {
    await api(`/listas/${id}/items`, { method: "POST", headers: headers(), body: JSON.stringify({ id_presentacion: idPresentacion, cantidad: 1 }) });
  } catch (err) {
    if (/ya esta en la lista/i.test(err.message)) {
      // Ya estaba: sube la cantidad en 1 en vez de fallar
      const l = await api(`/listas/${id}`, { headers: headers(false) });
      const item = l.items.find((i) => i.id_presentacion === idPresentacion);
      if (item) await api(`/listas/${id}/items/${item.id_item}`, { method: "PUT", headers: headers(),
        body: JSON.stringify({ cantidad: Number(item.cantidad) + 1 }) });
    } else { alert("Error: " + err.message); return; }
  }
  await verLista();
  $("detalle").innerHTML = `<p class="aviso">Agregado a tu lista.
    <button onclick="mostrarVista('lista')">Ver mi lista completa</button></p>` + $("detalle").innerHTML;
};
window.quitarItem = async (idItem) => {
  await api(`/listas/${$("select-lista").value}/items/${idItem}`, { method: "DELETE", headers: headers(false) });
  verLista();
};
$("btn-ir-buscar").onclick = () => mostrarVista("buscar");
$("btn-recomendar").onclick = async () => {
  const id = $("select-lista").value; if (!id) { alert("Elige una lista."); return; }
  const cuerpo = { modo: $("select-modo").value, radio_km: Number($("input-radio").value) };
  if ($("select-transporte").value) cuerpo.id_medio_transporte = Number($("select-transporte").value);
  if (ubic.lat) { cuerpo.latitud = ubic.lat; cuerpo.longitud = ubic.lon; }
  else if (ubic.cp) cuerpo.codigo_postal = ubic.cp;
  try {
    const r = await api(`/listas/${id}/recomendar`, { method: "POST", headers: headers(), body: JSON.stringify(cuerpo) });
    mostrarRecomendacion(r);
  } catch (err) {
    $("recomendacion").innerHTML = `<p class="aviso">No se pudo recomendar: ${err.message}. Revisa tu ubicación y el radio.</p>`;
    $("impacto").innerHTML = "";
  }
};
function mostrarRecomendacion(r) {
  const s = r.sucursal_recomendada;
  $("recomendacion").innerHTML = `
    <div class="recomendada"><h3>Compra todo en: ${s.nombre_comercial} (${s.cadena})</h3>
    ${s.calle}, ${s.colonia}, CP ${s.codigo_postal} · a ${s.distancia_km} km<br>
    Costo total ${dinero(r.resumen.costo_total)} · ahorro estimado ${dinero(r.resumen.ahorro_estimado)} ·
    huella total ${kg(r.resumen.huella_total_kgco2e)} ${r.resumen.huella_completa ? "" : "(parcial)"}<br>
    Productos cubiertos: ${r.resumen.productos_cubiertos} de ${r.resumen.productos_en_la_lista} ·
    sucursales comparadas: ${r.resumen.sucursales_comparadas}</div>
    ${r.avisos.map((a) => `<div class="aviso">${a}</div>`).join("")}
    <h4>Otras sucursales comparadas</h4>
    ${r.otras_sucursales.map((o) => `<div>${o.nombre_comercial} — ${o.distancia_km} km · ${dinero(o.costo_total)} · ${kg(o.huella_total_kgco2e)}</div>`).join("") || "Ninguna otra."}
    <h4>Detalle por producto</h4>
    ${r.items.map((i) => `<div>${i.producto} · ${i.presentacion} — ${dinero(i.precio_unitario)} c/u, subtotal ${dinero(i.subtotal)}${i.huella_producto_kgco2e != null ? ` · ${kg(i.huella_producto_kgco2e)}` : ""}</div>`).join("")}`;
  mostrarImpacto(r);
}

// ---------- Resumen de impacto: ahorro + huella estimada ----------
const HUELLA_ANUAL_PERSONA_PROMEDIO = 2000; // kg CO2e/año solo por comida, dieta promedio (Scarborough et al., 2014)
const KGCO2_POR_KM_AUTO = 0.17; // DEFRA 2023, auto gasolina promedio
function mostrarImpacto(r) {
  const res = r.resumen;
  const ahorro = res.ahorro_estimado || 0;
  const huella = res.huella_total_kgco2e || 0;
  const otras = r.otras_sucursales || [];
  const promCosto = otras.length ? otras.reduce((a, o) => a + o.costo_total, 0) / otras.length : null;
  const promHuella = otras.length ? otras.reduce((a, o) => a + o.huella_total_kgco2e, 0) / otras.length : null;
  const pctCosto = promCosto ? Math.round((promCosto - res.costo_total) / promCosto * 100) : null;
  const pctHuella = promHuella ? Math.round((promHuella - huella) / promHuella * 100) : null;
  const huellaAnual = huella * 52; // si esta lista fuera la compra semanal
  const difPersona = Math.round((huellaAnual - HUELLA_ANUAL_PERSONA_PROMEDIO) / HUELLA_ANUAL_PERSONA_PROMEDIO * 100);
  const kmAuto = huella / KGCO2_POR_KM_AUTO;
  const lineas = [];
  lineas.push(`<p><strong>Con esta compra ahorraste ${dinero(ahorro)}</strong> frente al promedio de las sucursales comparadas.</p>`);
  lineas.push(`<p>Tu huella estimada es de <strong>${kg(huella)}</strong>${res.huella_completa ? "" : " (parcial: algunos productos aún no tienen factor o peso)"}. Eso equivale a manejar unos ${Math.round(kmAuto)} km en auto.</p>`);
  if (pctCosto != null || pctHuella != null) {
    lineas.push(`<p>Frente a las otras tiendas comparadas, esta opción es ${pctCosto != null ? `<strong>${pctCosto}% más barata</strong>` : "—"} y ${pctHuella != null ? `<strong>${pctHuella}% menos huella</strong>` : "—"}.</p>`);
  }
  lineas.push(`<p>Si esta fuera tu compra semanal y siguieras así todo el año, ahorrarías unos <strong>${dinero(ahorro * 52)} al año</strong> y evitarías unos <strong>${huellaAnual.toFixed(1)} kg CO2e</strong> frente a comprar sin comparar.</p>`);
  const comparacion = difPersona <= 0
    ? `un <strong>${Math.abs(difPersona)}% menos</strong> que el promedio`
    : `un <strong>${difPersona}% más</strong> que el promedio`;
  lineas.push(`<p>Si todas tus compras fueran como esta, tu huella anual de comida sería de unos <strong>${Math.round(huellaAnual)} kg CO2e</strong>. Una persona con dieta promedio genera unos 2,000 kg CO2e al año solo por su comida (Scarborough et al., 2014): eso es ${comparacion}.</p>`);
  lineas.push(`<p class="nota">Estimación con factores de Poore &amp; Nemecek (2018) vía Our World in Data y DEFRA 2023. Son promedios globales por kg de producto, no mediciones de tu compra. La proyección anual supone que esta lista es tu compra semanal.</p>`);
  $("impacto").innerHTML = `<div class="impacto"><h3>Tu impacto con esta compra</h3>${lineas.join("")}</div>`;
}

// ---------- Arranque ----------
refrescarAuth();
mostrarVista((location.hash.replace("#/", "") || "buscar"));
cargarCatalogos().catch(() => {});
cargarListas();
mostrarBienvenida();
