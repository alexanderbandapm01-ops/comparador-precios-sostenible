DROP DATABASE IF EXISTS comparador_precios_sostenible;
CREATE DATABASE comparador_precios_sostenible
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE comparador_precios_sostenible;

CREATE TABLE estado (
    id_estado     INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL UNIQUE,
    region        VARCHAR(50)
);

CREATE TABLE municipio (
    id_municipio  INT AUTO_INCREMENT PRIMARY KEY,
    id_estado     INT NOT NULL,
    nombre        VARCHAR(100) NOT NULL,
    UNIQUE KEY uq_municipio (id_estado, nombre),
    CONSTRAINT fk_municipio_estado FOREIGN KEY (id_estado)
        REFERENCES estado(id_estado) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE catalogo (
    id_catalogo   INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE categoria (
    id_categoria  INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(150) NOT NULL UNIQUE
);

CREATE TABLE marca (
    id_marca      INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE unidad_medida (
    id_unidad     INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(40) NOT NULL,
    abreviatura   VARCHAR(10) NOT NULL UNIQUE,
    tipo          ENUM('masa','volumen','pieza','otro') NOT NULL
);

CREATE TABLE producto (
    id_producto   INT AUTO_INCREMENT PRIMARY KEY,
    id_categoria  INT NOT NULL,
    id_marca      INT NOT NULL,
    nombre        VARCHAR(200) NOT NULL,
    UNIQUE KEY uq_producto (id_categoria, id_marca, nombre),
    CONSTRAINT fk_producto_categoria FOREIGN KEY (id_categoria)
        REFERENCES categoria(id_categoria) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_producto_marca FOREIGN KEY (id_marca)
        REFERENCES marca(id_marca) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE presentacion (
    id_presentacion      INT AUTO_INCREMENT PRIMARY KEY,
    id_producto          INT NOT NULL,
    id_unidad            INT NOT NULL,
    cantidad             DECIMAL(10,3),
    envase               VARCHAR(50),
    variante             VARCHAR(150),
    descripcion_original VARCHAR(255) NOT NULL,
    UNIQUE KEY uq_presentacion (id_producto, descripcion_original),
    CONSTRAINT fk_presentacion_producto FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_presentacion_unidad FOREIGN KEY (id_unidad)
        REFERENCES unidad_medida(id_unidad) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE presentacion_catalogo (
    id_presentacion INT NOT NULL,
    id_catalogo     INT NOT NULL,
    PRIMARY KEY (id_presentacion, id_catalogo),
    CONSTRAINT fk_pc_presentacion FOREIGN KEY (id_presentacion)
        REFERENCES presentacion(id_presentacion) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_pc_catalogo FOREIGN KEY (id_catalogo)
        REFERENCES catalogo(id_catalogo) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE giro (
    id_giro       INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE cadena_comercial (
    id_cadena     INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE sucursal (
    id_sucursal      INT AUTO_INCREMENT PRIMARY KEY,
    id_cadena        INT NOT NULL,
    id_municipio     INT NOT NULL,
    id_giro          INT NOT NULL,
    nombre_comercial VARCHAR(200) NOT NULL,
    calle            VARCHAR(300) NOT NULL,
    colonia          VARCHAR(150) NOT NULL,
    codigo_postal    CHAR(5) NOT NULL,
    ubicacion        POINT NOT NULL SRID 4326,
    UNIQUE KEY uq_sucursal (id_cadena, nombre_comercial, calle, colonia, codigo_postal),
    SPATIAL INDEX idx_sucursal_ubicacion (ubicacion),
    CONSTRAINT fk_sucursal_cadena FOREIGN KEY (id_cadena)
        REFERENCES cadena_comercial(id_cadena) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_sucursal_municipio FOREIGN KEY (id_municipio)
        REFERENCES municipio(id_municipio) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_sucursal_giro FOREIGN KEY (id_giro)
        REFERENCES giro(id_giro) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE fuente_datos (
    id_fuente      INT AUTO_INCREMENT PRIMARY KEY,
    nombre_archivo VARCHAR(120) NOT NULL,
    periodo        VARCHAR(30),
    fecha_carga    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE registro_precio (
    id_registro     BIGINT AUTO_INCREMENT PRIMARY KEY,
    id_presentacion INT NOT NULL,
    id_sucursal     INT NOT NULL,
    id_fuente       INT NOT NULL,
    fecha_registro  DATE NOT NULL,
    precio          DECIMAL(10,2) NOT NULL,
    UNIQUE KEY uq_registro (id_presentacion, id_sucursal, id_fuente, fecha_registro),
    KEY idx_registro_fecha (fecha_registro),
    CONSTRAINT fk_registro_presentacion FOREIGN KEY (id_presentacion)
        REFERENCES presentacion(id_presentacion) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_registro_sucursal FOREIGN KEY (id_sucursal)
        REFERENCES sucursal(id_sucursal) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_registro_fuente FOREIGN KEY (id_fuente)
        REFERENCES fuente_datos(id_fuente) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE medio_transporte (
    id_transporte            INT AUTO_INCREMENT PRIMARY KEY,
    nombre                   VARCHAR(60) NOT NULL UNIQUE,
    factor_emision_kgco2_km  DECIMAL(10,5) NOT NULL
);

CREATE TABLE factor_emision_producto (
    id_factor         INT AUTO_INCREMENT PRIMARY KEY,
    id_producto       INT NOT NULL,
    kgco2_por_unidad  DECIMAL(10,4) NOT NULL,
    fuente            VARCHAR(200),
    CONSTRAINT fk_factor_producto FOREIGN KEY (id_producto)
        REFERENCES producto(id_producto) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE usuario (
    id_usuario    INT AUTO_INCREMENT PRIMARY KEY,
    nombre            VARCHAR(100) NOT NULL,
    apellido_paterno  VARCHAR(100) NOT NULL,
    apellido_materno  VARCHAR(100),
    fecha_nacimiento  DATE NOT NULL,
    email             VARCHAR(150) NOT NULL UNIQUE,
    contrasena_hash   VARCHAR(255) NOT NULL,
    id_municipio      INT NOT NULL,
    ubicacion         POINT SRID 4326,
    CONSTRAINT fk_usuario_municipio FOREIGN KEY (id_municipio)
        REFERENCES municipio(id_municipio) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE lista_compra (
    id_lista        INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario      INT NOT NULL,
    nombre          VARCHAR(100) NOT NULL,
    descripcion     VARCHAR(255),
    fecha_creacion  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado          ENUM('borrador','activa','completada') NOT NULL DEFAULT 'borrador',
    CONSTRAINT fk_lista_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE TABLE item_lista (
    id_item          INT AUTO_INCREMENT PRIMARY KEY,
    id_lista         INT NOT NULL,
    id_presentacion  INT NOT NULL,
    cantidad         DECIMAL(10,3) NOT NULL DEFAULT 1,
    UNIQUE KEY uq_item (id_lista, id_presentacion),
    CONSTRAINT fk_item_lista FOREIGN KEY (id_lista)
        REFERENCES lista_compra(id_lista) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_item_presentacion FOREIGN KEY (id_presentacion)
        REFERENCES presentacion(id_presentacion) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE recomendacion (
    id_recomendacion      INT AUTO_INCREMENT PRIMARY KEY,
    id_item               INT NOT NULL,
    id_sucursal           INT NOT NULL,
    precio_estimado       DECIMAL(10,2),
    ahorro_estimado       DECIMAL(10,2),
    huella_estimada_kgco2 DECIMAL(10,4),
    fecha_generacion      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_recomendacion_item FOREIGN KEY (id_item)
        REFERENCES item_lista(id_item) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_recomendacion_sucursal FOREIGN KEY (id_sucursal)
        REFERENCES sucursal(id_sucursal) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE distancia_usuario_sucursal (
    id_distancia   INT AUTO_INCREMENT PRIMARY KEY,
    id_usuario     INT NOT NULL,
    id_sucursal    INT NOT NULL,
    id_transporte  INT NOT NULL,
    distancia_km   DECIMAL(8,3) NOT NULL,
    UNIQUE KEY uq_distancia (id_usuario, id_sucursal, id_transporte),
    CONSTRAINT fk_distancia_usuario FOREIGN KEY (id_usuario)
        REFERENCES usuario(id_usuario) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_distancia_sucursal FOREIGN KEY (id_sucursal)
        REFERENCES sucursal(id_sucursal) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_distancia_transporte FOREIGN KEY (id_transporte)
        REFERENCES medio_transporte(id_transporte) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE VIEW vista_usuario AS
SELECT id_usuario, nombre, apellido_paterno, apellido_materno,
       fecha_nacimiento,
       TIMESTAMPDIFF(YEAR, fecha_nacimiento, CURDATE()) AS edad,
       email, id_municipio, ubicacion
FROM usuario;

INSERT INTO unidad_medida (nombre, abreviatura, tipo)
VALUES ('Sin unidad', 'N/A', 'otro');
