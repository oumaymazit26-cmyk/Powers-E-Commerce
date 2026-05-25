-- ============================================================
-- POWERS E-Commerce - Base de données MySQL
-- Catégories hiérarchiques : Climatisation, Désenfumage, Ventilation, Accessoires
-- Structure exacte selon spécifications métier
-- ============================================================

CREATE DATABASE IF NOT EXISTS powers_db 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

USE powers_db;

-- ============================================================
-- 1. TABLE USERS (Utilisateurs)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    email VARCHAR(120) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'admin',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 2. TABLE CATEGORIES (Hiérarchique : parent_id)
-- ============================================================
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id INT NULL,
    level INT DEFAULT 0,
    sort_order INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL,
    INDEX idx_parent (parent_id),
    INDEX idx_level (level),
    INDEX idx_slug (slug)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. TABLE PRODUCTS (Produits)
-- ============================================================
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200) NOT NULL UNIQUE,
    sku VARCHAR(100) UNIQUE,
    description TEXT,
    short_description VARCHAR(500),
    price DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    sale_price DECIMAL(10,2) DEFAULT 0.00,
    cost_price DECIMAL(10,2) DEFAULT 0.00,
    stock_quantity INT DEFAULT 0,
    stock_status VARCHAR(20) DEFAULT 'in_stock',
    weight DECIMAL(8,2) DEFAULT 0.00,
    dimensions VARCHAR(100),
    image VARCHAR(255),
    gallery TEXT,
    category_id INT,
    tags VARCHAR(255),
    status VARCHAR(20) DEFAULT 'active',
    featured BOOLEAN DEFAULT FALSE,
    meta_title VARCHAR(200),
    meta_description VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    INDEX idx_category (category_id),
    INDEX idx_status (status),
    INDEX idx_stock (stock_status),
    INDEX idx_featured (featured)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 4. INSERTION DES CATÉGORIES RÉELLES (Structure exacte)
-- ============================================================
-- ==================== 1. CLIMATISATION ====================
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Climatisation', 'climatisation', 'Produits de climatisation', NULL, 0, 1);
SET @clim = LAST_INSERT_ID();

-- Niveau 1 sous Climatisation
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Split système Inverter', 'split-systeme-inverter', 'Splits système inverter', @clim, 1, 1),
('Multi split', 'multi-split', 'Systèmes multi-split', @clim, 1, 2),
('VRF', 'vrf', 'Variable Refrigerant Flow', @clim, 1, 3),
('Atome', 'atome', 'Systèmes Atome', @clim, 1, 4),
('Pompe à chaleur', 'pompe-a-chaleur', 'Pompes à chaleur', @clim, 1, 5),
('Rafraîchisseur', 'rafraichisseur', 'Rafraîchisseurs d\'air', @clim, 1, 6);

SET @split = (SELECT id FROM categories WHERE slug = 'split-systeme-inverter');
SET @vrf   = (SELECT id FROM categories WHERE slug = 'vrf');
SET @atome = (SELECT id FROM categories WHERE slug = 'atome');
SET @pac   = (SELECT id FROM categories WHERE slug = 'pompe-a-chaleur');

-- Niveau 2 & 3 sous Split
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Mural inverter', 'mural-inverter', 'Climatiseurs muraux', @split, 2, 1),
('Mobile', 'mobile', 'Mobiles', @split, 2, 2),
('Armoire', 'armoire', 'Armoires', @split, 2, 3),
('Cassette', 'cassette-split', 'Cassettes', @split, 2, 4),
('Console', 'console', 'Consoles', @split, 2, 5),
('Gainable inverter', 'gainable-inverter', 'Gainables', @split, 2, 6);

SET @mural = (SELECT id FROM categories WHERE slug = 'mural-inverter');
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('smart inverter ART COOL', 'smart-inverter-art-cool', 'Design ART COOL', @mural, 3, 1),
('Normal inverter', 'normal-inverter', 'Standard', @mural, 3, 2);

-- Niveau 2 & 3 sous VRF
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Unité extérieure', 'unite-exterieure-vrf', 'UE VRF', @vrf, 2, 1),
('Unité intérieure', 'unite-interieure-vrf', 'UI VRF', @vrf, 2, 2);

SET @ue_vrf = (SELECT id FROM categories WHERE slug = 'unite-exterieure-vrf');
SET @ui_vrf = (SELECT id FROM categories WHERE slug = 'unite-interieure-vrf');

INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Min', 'unite-ext-min', 'Mini VRF', @ue_vrf, 3, 1),
('Modulaire/Non modulaire', 'unite-ext-modulaire', 'Modulaire', @ue_vrf, 3, 2),
('Cassette VRF', 'cassette-vrf', 'Cassette', @ui_vrf, 3, 1),
('Gainable VRF', 'gainable-vrf', 'Gainable', @ui_vrf, 3, 2),
('Mural VRF', 'mural-vrf', 'Mural', @ui_vrf, 3, 3);

-- Niveau 2 sous Atome et PAC
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Unité intérieure', 'unite-interieure-atome', 'UI Atome', @atome, 2, 1),
('Unité extérieure', 'unite-exterieure-atome', 'UE Atome', @atome, 2, 2),
('Air/Air', 'pompe-air-air', 'PAC Air/Air', @pac, 2, 1),
('Air/Eau', 'pompe-air-eau', 'PAC Air/Eau', @pac, 2, 2);

-- ==================== 2. DÉSENFUMAGE ====================
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Désenfumage', 'desenfumage', 'Désenfumage', NULL, 0, 2);
SET @desenf = LAST_INSERT_ID();
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Caisson', 'caisson-desenfumage', 'Caissons', @desenf, 1, 1),
('Clapet', 'clapet', 'Clapets', @desenf, 1, 2),
('Volet', 'volet', 'Volets', @desenf, 1, 3),
('Autre', 'autre-desenfumage', 'Autres', @desenf, 1, 4);

-- ==================== 3. VENTILATION ====================
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Ventilation', 'ventilation', 'Ventilation', NULL, 0, 3);
SET @ventil = LAST_INSERT_ID();
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Caisson', 'caisson-ventilation', 'Caissons', @ventil, 1, 1),
('Ventilateur', 'ventilateur', 'Ventilateurs', @ventil, 1, 2),
('Rideau d\'Air', 'rideau-d-air', 'Rideaux d\'air', @ventil, 1, 3),
('Autres', 'autres-ventilation', 'Autres', @ventil, 1, 4);

-- ==================== 4. ACCESSOIRES ====================
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Accessoires', 'accessoires', 'Accessoires', NULL, 0, 4);
SET @access = LAST_INSERT_ID();
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Chauffe Eau Solaire', 'chauffe-eau-solaire', 'Solaire', @access, 1, 1),
('Diffusion', 'diffusion', 'Diffusion', @access, 1, 2),
('Autre', 'autre-accessoire', 'Autres', @access, 1, 3);

SET @diff = (SELECT id FROM categories WHERE slug = 'diffusion');
INSERT INTO categories (name, slug, description, parent_id, level, sort_order) VALUES
('Diffuseur', 'diffuseur', 'Diffuseurs', @diff, 2, 1),
('Grille', 'grille', 'Grilles', @diff, 2, 2),
('Ventouse', 'ventouse', 'Ventouses', @diff, 2, 3);
-- ============================================================
-- 5. VUE HIÉRARCHIQUE (Optionnel)
-- ============================================================
CREATE OR REPLACE VIEW v_categories_tree AS
WITH RECURSIVE category_tree AS (
    SELECT 
        id, name, slug, parent_id, level, sort_order,
        CAST(name AS CHAR(1000)) AS path,
        CAST(id AS CHAR(1000)) AS path_id
    FROM categories WHERE parent_id IS NULL
    UNION ALL
    SELECT 
        c.id, c.name, c.slug, c.parent_id, c.level, c.sort_order,
        CONCAT(ct.path, ' > ', c.name),
        CONCAT(ct.path_id, '>', c.id)
    FROM categories c
    INNER JOIN category_tree ct ON c.parent_id = ct.id
)
SELECT * FROM category_tree ORDER BY path;
