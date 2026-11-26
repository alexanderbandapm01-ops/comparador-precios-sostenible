-- Factores de emision ESTIMADOS para calcular la huella de carbono aproximada.
--
-- Que es: llena factor_emision_producto (un factor por producto, en kg de CO2e
-- por kg de producto) y medio_transporte (kg de CO2e por km) para que el
-- recomendador calcule la huella de cada lista en vez de dejarla parcial.
--
-- Fuentes (promedios globales, NO mediciones de cada producto ni de Mexico):
--   * Productos: Poore & Nemecek (2018), "Reducing food's environmental impacts
--     through producers and consumers", Science 360: 987-992. Promedios por kg
--     de producto, de la granja a la tienda, publicados por Our World in Data.
--     Valores usados: res 99.48, chocolate 46.65, cordero 39.72, cafe 28.53,
--     camaron 26.87, queso 23.88, pescado 13.63, cerdo 12.31, pollo 9.87,
--     huevo 4.67, arroz 4.45, leche 3.15, legumbres 1.80, trigo/pan 1.57,
--     jitomate 2.09, platano 0.86, papa 0.46, manzana 0.43.
--   * Cuando una categoria no tiene equivalente directo en ese estudio, el factor
--     es una ESTIMACION de CDPS (marcada en la columna fuente) y se explica en
--     los comentarios de cada bloque: refrescos 0.50, hortalizas 1.00,
--     frutas frescas 0.60, aceites 4.00, tortillas 1.00, azucar 1.80,
--     grasas animales 14.00, te 10.00, comida preparada 5.00, derivados de
--     leche 12.00, golosinas sin chocolate 2.00, cereales sin arroz 2.00,
--     condimentos 2.00, frutas/legumbres procesadas 1.50.
--   * Transporte: DEFRA / DESNZ, UK Government GHG Conversion Factors 2023:
--     auto (gasolina, promedio) 0.1709 kgCO2e/km; autobus local 0.10215
--     kgCO2e por pasajero-km. Bicicleta y A pie son 0.
--
-- Como se asigna: primero por nombre del producto (ej. "queso" -> 23.88),
-- luego por categoria. Si una categoria no aparece aqui, el factor queda en
-- 1.50 (ELSE) para que ningun producto se quede sin estimacion.
--
-- La pagina muestra estos numeros como ESTIMADOS, con sus fuentes. No son
-- datos de PROFECO ni mediciones locales.
--
-- Cargar con:  mysql comparador_precios_sostenible < sql/factores_estimados.sql
-- Es idempotente: se puede volver a correr sin duplicar filas.

DELETE FROM factor_emision_producto;

INSERT INTO factor_emision_producto (id_producto, kgco2_por_unidad, fuente)
SELECT pr.id_producto,
  CASE
    -- Por nombre del producto (mas preciso que la categoria)
    WHEN LOWER(pr.nombre) LIKE '%res%' OR LOWER(pr.nombre) LIKE '%bistec%' THEN 99.48
    WHEN LOWER(pr.nombre) LIKE '%cordero%' THEN 39.72
    WHEN LOWER(pr.nombre) LIKE '%chocolate%' THEN 46.65
    WHEN LOWER(pr.nombre) LIKE '%caf%' THEN 28.53
    WHEN LOWER(pr.nombre) LIKE '%camaron%' OR LOWER(pr.nombre) LIKE '%camarón%' THEN 26.87
    WHEN LOWER(pr.nombre) LIKE '%queso%' THEN 23.88
    WHEN LOWER(pr.nombre) LIKE '%mantequilla%' THEN 21.00
    WHEN LOWER(pr.nombre) LIKE '%pescado%' OR LOWER(pr.nombre) LIKE '%atun%'
      OR LOWER(pr.nombre) LIKE '%atún%' OR LOWER(pr.nombre) LIKE '%sardina%'
      OR LOWER(pr.nombre) LIKE '%salmon%' OR LOWER(pr.nombre) LIKE '%salmón%' THEN 13.63
    WHEN LOWER(pr.nombre) LIKE '%cerdo%' OR LOWER(pr.nombre) LIKE '%jamon%'
      OR LOWER(pr.nombre) LIKE '%jamón%' OR LOWER(pr.nombre) LIKE '%salchicha%'
      OR LOWER(pr.nombre) LIKE '%chorizo%' THEN 12.31
    WHEN LOWER(pr.nombre) LIKE '%pollo%' OR LOWER(pr.nombre) LIKE '%gallina%' THEN 9.87
    WHEN LOWER(pr.nombre) LIKE '%huevo%' THEN 4.67
    WHEN LOWER(pr.nombre) LIKE '%arroz%' THEN 4.45
    WHEN LOWER(pr.nombre) LIKE '%leche%' OR LOWER(pr.nombre) LIKE '%yogur%'
      OR LOWER(pr.nombre) LIKE '%yogurt%' OR LOWER(pr.nombre) LIKE '%crema%' THEN 3.15
    WHEN LOWER(pr.nombre) LIKE '%frijol%' OR LOWER(pr.nombre) LIKE '%lenteja%'
      OR LOWER(pr.nombre) LIKE '%garbanzo%' THEN 1.80
    WHEN LOWER(pr.nombre) LIKE '%jitomate%' OR LOWER(pr.nombre) LIKE '%tomate%' THEN 2.09
    WHEN LOWER(pr.nombre) LIKE '%platano%' OR LOWER(pr.nombre) LIKE '%plátano%'
      OR LOWER(pr.nombre) LIKE '%banana%' THEN 0.86
    WHEN LOWER(pr.nombre) LIKE '%papa%' THEN 0.46
    WHEN LOWER(pr.nombre) LIKE '%manzana%' THEN 0.43
    WHEN LOWER(pr.nombre) LIKE '%azucar%' OR LOWER(pr.nombre) LIKE '%azúcar%' THEN 1.80
    -- Por categoria (productos cuyo nombre no dio pista)
    WHEN c.nombre = 'Carne y Visceras de Res' THEN 99.48
    WHEN c.nombre = 'Cafe' THEN 28.53
    WHEN c.nombre = 'Carne y Visceras de Cerdo' OR c.nombre = 'Carnes Frias Secas y Embutidos' THEN 12.31
    WHEN c.nombre = 'Carne de Ave' THEN 9.87
    WHEN c.nombre = 'Huevo' THEN 4.67
    WHEN c.nombre = 'Leche Procesada' OR c.nombre = 'Leche Fresca' THEN 3.15
    WHEN c.nombre = 'Legumbres Secas' THEN 1.80
    WHEN c.nombre = 'Galletas Pastas y Harinas de Trigo' OR c.nombre = 'Pan' THEN 1.57
    WHEN c.nombre = 'Pescados y Mariscos' OR c.nombre = 'Pescados y Mariscos en Conserva' THEN 13.63
    WHEN c.nombre = 'Frutas y Legumbres Procesadas' THEN 1.50
    WHEN c.nombre = 'Hortalizas Frescas' THEN 1.00
    WHEN c.nombre = 'Tortillas y Derivados del Maiz' THEN 1.00
    WHEN c.nombre = 'Frutas Frescas' THEN 0.60
    WHEN c.nombre = 'Refrescos Envasados' THEN 0.50
    WHEN c.nombre = 'Aceites y Grasas Veg. Comestibles' THEN 4.00
    WHEN c.nombre = 'Derivados de Leche' THEN 12.00
    WHEN c.nombre = 'Chocolates y Golosinas' THEN 2.00
    WHEN c.nombre = 'Arroz y Cereales Preparados' THEN 2.00
    WHEN c.nombre = 'Condimentos' THEN 2.00
    WHEN c.nombre = 'Grasas Animales Comestibles' THEN 14.00
    WHEN c.nombre = 'Te' THEN 10.00
    WHEN c.nombre = 'Alimentos Cocinados F/casa' THEN 5.00
    ELSE 1.50
  END,
  CASE
    WHEN LOWER(pr.nombre) LIKE '%res%' OR LOWER(pr.nombre) LIKE '%bistec%'
      OR LOWER(pr.nombre) LIKE '%cordero%' OR LOWER(pr.nombre) LIKE '%chocolate%'
      OR LOWER(pr.nombre) LIKE '%caf%' OR LOWER(pr.nombre) LIKE '%camaron%'
      OR LOWER(pr.nombre) LIKE '%camarón%' OR LOWER(pr.nombre) LIKE '%queso%'
      OR LOWER(pr.nombre) LIKE '%mantequilla%' OR LOWER(pr.nombre) LIKE '%pescado%'
      OR LOWER(pr.nombre) LIKE '%atun%' OR LOWER(pr.nombre) LIKE '%atún%'
      OR LOWER(pr.nombre) LIKE '%sardina%' OR LOWER(pr.nombre) LIKE '%salmon%'
      OR LOWER(pr.nombre) LIKE '%salmón%' OR LOWER(pr.nombre) LIKE '%cerdo%'
      OR LOWER(pr.nombre) LIKE '%jamon%' OR LOWER(pr.nombre) LIKE '%jamón%'
      OR LOWER(pr.nombre) LIKE '%salchicha%' OR LOWER(pr.nombre) LIKE '%chorizo%'
      OR LOWER(pr.nombre) LIKE '%pollo%' OR LOWER(pr.nombre) LIKE '%gallina%'
      OR LOWER(pr.nombre) LIKE '%huevo%' OR LOWER(pr.nombre) LIKE '%arroz%'
      OR LOWER(pr.nombre) LIKE '%leche%' OR LOWER(pr.nombre) LIKE '%yogur%'
      OR LOWER(pr.nombre) LIKE '%yogurt%' OR LOWER(pr.nombre) LIKE '%crema%'
      OR LOWER(pr.nombre) LIKE '%frijol%' OR LOWER(pr.nombre) LIKE '%lenteja%'
      OR LOWER(pr.nombre) LIKE '%garbanzo%' OR LOWER(pr.nombre) LIKE '%jitomate%'
      OR LOWER(pr.nombre) LIKE '%tomate%' OR LOWER(pr.nombre) LIKE '%platano%'
      OR LOWER(pr.nombre) LIKE '%plátano%' OR LOWER(pr.nombre) LIKE '%banana%'
      OR LOWER(pr.nombre) LIKE '%papa%' OR LOWER(pr.nombre) LIKE '%manzana%'
      OR LOWER(pr.nombre) LIKE '%azucar%' OR LOWER(pr.nombre) LIKE '%azúcar%'
      THEN 'Poore & Nemecek (2018) via Our World in Data'
    WHEN c.nombre IN ('Cafe', 'Carne de Ave', 'Carne y Visceras de Cerdo',
      'Carne y Visceras de Res', 'Carnes Frias Secas y Embutidos', 'Huevo',
      'Leche Procesada', 'Leche Fresca', 'Legumbres Secas',
      'Galletas Pastas y Harinas de Trigo', 'Pan', 'Pescados y Mariscos',
      'Pescados y Mariscos en Conserva')
      THEN 'Poore & Nemecek (2018) via Our World in Data'
    ELSE 'CDPS: estimacion aproximada (ver sql/factores_estimados.sql)'
  END
FROM producto pr
JOIN categoria c ON c.id_categoria = pr.id_categoria;

-- Medios de transporte (la tabla estaba vacia en la BD de ejemplo: sin filas
-- el selector de transporte salia vacio y el traslado nunca se calculaba).
INSERT INTO medio_transporte (nombre, factor_emision_kgco2_km) VALUES
  ('Auto', 0.17090),
  ('Transporte público', 0.10215),
  ('Bicicleta', 0),
  ('A pie', 0)
ON DUPLICATE KEY UPDATE factor_emision_kgco2_km = VALUES(factor_emision_kgco2_km);
