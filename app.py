"""
POWERS E-Commerce Product Management App v2.0
Backend: Flask + SQLAlchemy + WooCommerce Sync + RBAC + Audit Log + Draft/Live
"""

import os
import json
import uuid
import sys
import traceback
from functools import wraps
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, send_from_directory, g
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS

from dotenv import load_dotenv
load_dotenv()
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from woocommerce import API
import requests


def safe_print(message):
    try:
        print(message)
    except UnicodeEncodeError:
        encoding = sys.stdout.encoding or 'utf-8'
        print(str(message).encode(encoding, errors='replace').decode(encoding))

import hashlib
import base64
# ============================================================
# FLASK APP CONFIG
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'powers-ecommerce-secret-key-2024')

# --- CONFIGURATION BASE DE DONNÉES ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///powers_db.sqlite3')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)

# ============================================================
# CORS — CONFIGURATION EXPLICITE ET LARGE (CRITIQUE)
# ============================================================
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": ["Authorization", "Content-Type", "Accept", "X-Requested-With"],
        "supports_credentials": True,
        "expose_headers": ["Content-Type", "X-Total-Count"]
    }
})


def clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def parse_float(value, default=0.0):
    value = clean_text(value)
    if value is None:
        return default
    return float(value.replace(',', '.'))


def parse_int(value, default=0):
    value = clean_text(value)
    if value is None:
        return default
    return int(float(value.replace(',', '.')))

# ============================================================
# GESTIONNAIRES D'ERREURS GLOBAUX — CRITIQUE POUR DEBUG
# ============================================================
@app.errorhandler(Exception)
def handle_exception(e):
    """Capture toutes les exceptions et retourne du JSON propre"""
    db.session.rollback()
    traceback.print_exc()

    error_msg = str(e)
    error_type = type(e).__name__

    # Log détaillé dans la console serveur
    safe_print(f"\n❌❌❌ ERREUR 500 — {error_type}: {error_msg}")
    safe_print(f"📍 Route: {request.method} {request.path}")
    safe_print(f"🔑 Headers: {dict(request.headers)}")

    return jsonify({
        'success': False,
        'message': error_msg,
        'error_type': error_type,
        'route': f"{request.method} {request.path}"
    }), 500


@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'success': False,
        'message': 'Route non trouvée',
        'path': request.path,
        'method': request.method
    }), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({
        'success': False,
        'message': 'Méthode non autorisée',
        'method': request.method,
        'path': request.path
    }), 405


# ============================================================
# WOOCOMMERCE CONFIG — INITIALISATION LAZY
# ============================================================
BASE_IMAGE_URL = os.environ.get('BASE_IMAGE_URL', '').strip()

_wcapi_instance = None

def get_wcapi():
    """Initialise et retourne l'instance WooCommerce API (lazy singleton)."""
    global _wcapi_instance
    if _wcapi_instance is not None:
        return _wcapi_instance

    wp_url = os.environ.get('WP_URL', '').strip()
    ck = os.environ.get('WP_CONSUMER_KEY', '').strip()
    cs = os.environ.get('WP_CONSUMER_SECRET', '').strip()

    safe_print(f"🔍 Tentative connexion WooCommerce...")
    safe_print(f"   WP_URL présent: {'OUI (' + wp_url + ')' if wp_url else 'NON'}")
    safe_print(f"   WP_CONSUMER_KEY présent: {'OUI' if ck else 'NON'}")
    safe_print(f"   WP_CONSUMER_SECRET présent: {'OUI' if cs else 'NON'}")

    if wp_url and ck and cs:
        try:
            _wcapi_instance = API(
                url=wp_url,
                consumer_key=ck,
                consumer_secret=cs,
                version="wc/v3",
                timeout=15
            )
            safe_print(f"✅ WooCommerce connecté: {wp_url}")
            return _wcapi_instance
        except Exception as e:
            safe_print(f"❌ Erreur connexion WooCommerce: {e}")
            return None
    else:
        missing = []
        if not wp_url: missing.append('WP_URL')
        if not ck: missing.append('WP_CONSUMER_KEY')
        if not cs: missing.append('WP_CONSUMER_SECRET')
        safe_print(f"⚠️ WooCommerce non configuré — variables manquantes: {', '.join(missing)}")
        return None


# ============================================================
# RBAC - ROLE PERMISSIONS
# ============================================================
ROLE_PERMISSIONS = {
    'admin': ['*'],
    'product_manager': [
        'product:create', 'product:read', 'product:update', 'product:delete',
        'product:publish', 'product:duplicate', 'product:archive', 'product:draft',
        'category:create', 'category:read', 'category:update', 'category:delete',
        'user:read', 'audit:read'
    ],
    'sales_manager': [
        'product:read', 'category:read', 'user:read', 'audit:read'
    ],
    'content_editor': [
        'product:create', 'product:read', 'product:update', 'product:draft',
        'category:read', 'user:read'
    ],
    'customer_support': [
        'product:read', 'category:read', 'user:read'
    ],
    'technician': [
        'product:read', 'category:read', 'user:read'
    ]
}

VALID_ROLES = list(ROLE_PERMISSIONS.keys())


# ============================================================
# HELPERS & DECORATORS
# ============================================================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



# ============================================================
# CLOUDINARY CONFIG — Upload via API HTTP (PAS de module Python requis)
# ============================================================
CLOUDINARY_CONFIGURED = False
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '').strip()
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '').strip()
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '').strip()

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    CLOUDINARY_CONFIGURED = True
    safe_print(f"✅ Cloudinary configuré (API HTTP): {CLOUDINARY_CLOUD_NAME}")
else:
    missing = [k for k, v in {'CLOUDINARY_CLOUD_NAME': CLOUDINARY_CLOUD_NAME, 'CLOUDINARY_API_KEY': CLOUDINARY_API_KEY, 'CLOUDINARY_API_SECRET': CLOUDINARY_API_SECRET}.items() if not v]
    safe_print(f"⚠️ Cloudinary non configuré — variables manquantes: {', '.join(missing)}")

def save_uploaded_file(file):
    if file and allowed_file(file.filename):
        # ─── Essayer Cloudinary d'abord (via API HTTP) ───
        if CLOUDINARY_CONFIGURED:
            try:
                file.seek(0)
                file_bytes = file.read()
                file.seek(0)  # Reset pour le fallback

                # Upload via API HTTP Cloudinary
                url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload"

                timestamp = str(int(datetime.utcnow().timestamp()))

                # Cloudinary signature: paramètres triés alphabétiquement + API_SECRET
                # Paramètres à signer: folder, timestamp
                # Tous les paramètres envoyés (sauf file, api_key) doivent être dans la signature
                params = {
                    'folder': 'powers/products',
                    'timestamp': timestamp
                }
                # Trier les paramètres par clé alphabétique
                sorted_params = '&'.join([f"{k}={v}" for k, v in sorted(params.items())])
                params_to_sign = f"{sorted_params}{CLOUDINARY_API_SECRET}"
                signature = hashlib.sha1(params_to_sign.encode()).hexdigest()

                files = {'file': ('image.jpg', file_bytes, file.content_type or 'image/jpeg')}
                # Les paramètres doivent aussi être dans l'ordre alphabétique
                data = [
                    ('api_key', CLOUDINARY_API_KEY),
                    ('folder', 'powers/products'),
                    ('signature', signature),
                    ('timestamp', timestamp)
                ]

                response = requests.post(url, files=files, data=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    url = result.get('secure_url')
                    if url:
                        safe_print(f"✅ Image Cloudinary: {url[:60]}...")
                        return url
                else:
                    safe_print(f"❌ Cloudinary API error: {response.status_code} - {response.text[:200]}")
            except Exception as e:
                safe_print(f"❌ Cloudinary upload failed: {e}")
                # Fallback local ci-dessous

        # ─── Fallback local (développement / sans Cloudinary) ───
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.seek(0)
        file.save(filepath)
        return unique_filename
    return None

def build_category_tree():
    roots = Category.query.filter_by(parent_id=None).order_by(Category.sort_order).all()
    return [root.to_dict(include_children=True) for root in roots]


def get_category_descendants(category_id):
    result = [category_id]
    children = Category.query.filter_by(parent_id=category_id).all()
    for child in children:
        result.extend(get_category_descendants(child.id))
    return result




# ============================================================
# SYNCHRONISATION WOOCOMMERCE
# ============================================================
def sync_product_to_wordpress(product):
    wcapi = get_wcapi()
    if not wcapi:
        product._last_sync_error = 'WooCommerce non configuré: vérifiez WP_URL, WP_CONSUMER_KEY et WP_CONSUMER_SECRET.'
        safe_print("⚠️ WooCommerce non configuré, sync ignorée")
        return None

    try:
        product_sku = product.sku or f"POWERS-{product.id:06d}"
        if not product.sku:
            product.sku = product_sku
            db.session.commit()

        existing_id = None
        response = wcapi.get("products", params={"sku": product_sku})
        if response.status_code == 200:
            items = response.json()
            if items:
                existing_id = items[0]["id"]

        wc_stock = product.stock_status
        if wc_stock == 'in_stock':
            wc_stock = 'instock'
        elif wc_stock == 'out_of_stock':
            wc_stock = 'outofstock'

        ptype = product.product_type if product.product_type in ('simple', 'variable', 'grouped', 'external') else 'simple'

        data = {
            "name": product.name,
            "type": ptype,
            "regular_price": str(float(product.price)) if ptype != 'variable' else "",
            "description": product.description or "",
            "short_description": product.short_description or "",
            "sku": product_sku,
            "manage_stock": ptype == 'simple',
            "stock_quantity": product.stock_quantity if ptype == 'simple' else None,
            "stock_status": wc_stock,
            "status": "publish" if product.status == "active" else "draft",
            "categories": [],
            "images": [],
            "tags": [],
            "attributes": [],
            "meta_data": []
        }

        if product.sale_price and float(product.sale_price) > 0:
            data["sale_price"] = str(float(product.sale_price))

        if product.weight and float(product.weight) > 0:
            data["weight"] = str(float(product.weight))

        if product.dimensions:
            data["dimensions"] = {"length": "", "width": "", "height": ""}
            parts = product.dimensions.split('x')
            if len(parts) == 3:
                data["dimensions"] = {
                    "length": parts[0].strip(),
                    "width": parts[1].strip(),
                    "height": parts[2].strip()
                }

        if product.tags:
            data["tags"] = [{"name": tag.strip()} for tag in product.tags.split(',') if tag.strip()]

        if product.brand:
            data["attributes"].append({
                "name": "Marque",
                "slug": "marque",
                "position": 0,
                "visible": True,
                "variation": False,
                "options": [product.brand]
            })
            data["meta_data"].append({"key": "_product_brand", "value": product.brand})

        if product.attributes and ptype == 'variable':
            try:
                attrs = json.loads(product.attributes) if isinstance(product.attributes, str) else product.attributes
                for attr in attrs:
                    data["attributes"].append({
                        "name": attr.get("name"),
                        "slug": attr.get("slug", attr.get("name", "").lower().replace(" ", "-")),
                        "position": attr.get("position", 0),
                        "visible": attr.get("visible", True),
                        "variation": attr.get("variation", True),
                        "options": attr.get("options", [])
                    })
            except Exception as e:
                safe_print(f"⚠️ Erreur parsing attributs: {e}")

        if product.category:
            cat_name = product.category.name
            try:
                cat_res = wcapi.get("products/categories", params={"search": cat_name, "per_page": 100})
                if cat_res.status_code == 200:
                    cats = cat_res.json()
                    matched = next((c for c in cats if c["name"].lower() == cat_name.lower()), None)
                    if matched:
                        data["categories"] = [{"id": matched["id"]}]
                    else:
                        new_cat = wcapi.post("products/categories", {
                            "name": cat_name,
                            "slug": product.category.slug
                        })
                        if new_cat.status_code == 201:
                            data["categories"] = [{"id": new_cat.json()["id"]}]
            except Exception as e:
                safe_print(f"⚠️ Erreur catégorie WP: {e}")

        # Images — Cloudinary URL directe ou locale
        if product.image:
            img_url = get_image_url(product.image)
            if img_url:
                data["images"].append({"src": img_url, "position": 0})

        if product.gallery:
            for idx, img in enumerate(product.gallery.split(',')):
                img = img.strip()
                if img:
                    img_url = get_image_url(img)
                    if img_url:
                        data["images"].append({
                            "src": img_url,
                            "position": idx + 1
                        })

        if existing_id:
            res = wcapi.put(f"products/{existing_id}", data)
            wp_product = res.json() if res.status_code in (200, 201) else None
            action = "mis à jour"
        else:
            res = wcapi.post("products", data)
            wp_product = res.json() if res.status_code == 201 else None
            action = "créé"

        if not wp_product or 'id' not in wp_product:
            error_text = ""
            try:
                error_text = res.text[:500]
            except:
                pass
            product._last_sync_error = f"WooCommerce HTTP {res.status_code}: {error_text}"
            safe_print(f"❌ Erreur WooCommerce: {res.status_code} - {error_text[:300]}")
            product.wp_sync_status = 'failed'
            db.session.commit()
            return None

        parent_id = wp_product['id']
        product.wp_product_id = parent_id
        product.wp_sync_status = 'synced'
        db.session.commit()
        safe_print(f"🔄 Produit WooCommerce {action} (ID: {parent_id})")

        if ptype == 'variable' and product.variations:
            sync_variations_to_wc(product, parent_id)

        return wp_product

    except Exception as e:
        # 🔴 CORRECTION CRITIQUE : rollback avant tout
        db.session.rollback()
        product._last_sync_error = f"{type(e).__name__}: {e}"
        safe_print(f"❌ Exception sync: {e}")
        traceback.print_exc()
        product.wp_sync_status = 'failed'
        try:
            db.session.commit()
        except Exception as commit_err:
            safe_print(f"❌ Impossible de sauvegarder le statut failed: {commit_err}")
        return None


def sync_variations_to_wc(product, parent_id):
    wcapi = get_wcapi()
    if not wcapi or not product.variations:
        return

    try:
        variations = json.loads(product.variations) if isinstance(product.variations, str) else product.variations
        if not variations:
            return

        existing_resp = wcapi.get(f"products/{parent_id}/variations", params={"per_page": 100})
        existing_vars = existing_resp.json() if existing_resp.status_code == 200 else []
        existing_by_sku = {v['sku']: v['id'] for v in existing_vars if v.get('sku')}

        for var in variations:
            var_data = {
                "sku": var.get('sku', ''),
                "regular_price": str(var.get('regular_price', product.price)),
                "manage_stock": True,
                "stock_quantity": int(var.get('stock_quantity', 0)),
                "stock_status": "instock" if int(var.get('stock_quantity', 0)) > 0 else "outofstock",
                "attributes": []
            }

            if var.get('sale_price') and float(var['sale_price']) > 0:
                var_data["sale_price"] = str(float(var['sale_price']))

            if var.get('weight') and float(var['weight']) > 0:
                var_data["weight"] = str(float(var['weight']))

            attrs = var.get('attributes', {})
            if isinstance(attrs, dict):
                for attr_name, attr_option in attrs.items():
                    var_data["attributes"].append({
                        "name": attr_name,
                        "option": str(attr_option)
                    })
            elif isinstance(attrs, list):
                var_data["attributes"] = attrs

            sku = var_data['sku']
            if sku and sku in existing_by_sku:
                r = wcapi.put(f"products/{parent_id}/variations/{existing_by_sku[sku]}", var_data)
                safe_print(f"  ↳ Variation {sku} mise à jour" if r.status_code in (200,201) else f"  ⚠️ Err update var {sku}")
            else:
                r = wcapi.post(f"products/{parent_id}/variations", var_data)
                safe_print(f"  ↳ Variation {sku} créée" if r.status_code == 201 else f"  ⚠️ Err create var {sku}")

    except Exception as e:
        safe_print(f"❌ Erreur sync variations: {e}")


# ==================== INIT DB ====================

def init_db():
    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@powers.com',
                password_hash=generate_password_hash('admin123'),
                role='admin',
                is_suspended=False
            )
            db.session.add(admin)
            db.session.commit()
            safe_print('✅ Admin créé: admin / admin123')

        safe_print(f'✅ Base initialisée. Messages: {ContactMessage.query.count()}')
        if Category.query.count() == 0:
            safe_print("⚠️ Aucune catégorie trouvée. Exécutez le script SQL powers_db_mysql.sql")



def send_contact_email(data):
    """Envoie un email de notification pour un nouveau contact"""
    smtp_host = os.environ.get('SMTP_HOST', '').strip()
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '').strip()
    smtp_pass = os.environ.get('SMTP_PASSWORD', '').strip()
    to_email = os.environ.get('CONTACT_EMAIL', 'comercial@technoclim.ma').strip()

    if not all([smtp_host, smtp_user, smtp_pass]):
        safe_print("⚠️ SMTP non configuré, email non envoyé")
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = to_email
        msg['Subject'] = f"[Technoclim] Nouveau message: {data.get('subject', 'Formulaire de devis')}"

        body = f"""
        🔧 NOUVEAU MESSAGE TECHNOCLIM

        ───────────────────────────────
        👤 Nom: {data.get('name', 'Non renseigné')}
        📧 Email: {data.get('email')}
        📞 Téléphone: {data.get('phone', 'Non renseigné')}
        📦 Produit: {data.get('product', 'Non renseigné')}
        🔢 Quantité: {data.get('quantity', 'Non renseignée')}
        🔧 Service: {data.get('service', 'Non renseigné')}
        ───────────────────────────────

        💬 Message:
        {data.get('message', '')}

        ───────────────────────────────
        📅 Reçu le: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}
        🌐 Source: {data.get('source', 'website')}
        ───────────────────────────────
        """

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        safe_print(f"✅ Email envoyé à {to_email}")
        return True
    except Exception as e:
        safe_print(f"❌ Erreur envoi email: {e}")
        traceback.print_exc()
        return False

# ============================================================
# DIAGNOSTIC ROUTES
# ============================================================

@app.route('/api/diag/env', methods=['GET'])
def diag_env():
    """Route de diagnostic — montre les variables d'environnement (masquées)"""
    wp_url = os.environ.get('WP_URL', '')
    ck = os.environ.get('WP_CONSUMER_KEY', '')
    cs = os.environ.get('WP_CONSUMER_SECRET', '')
    db_url = os.environ.get('DATABASE_URL', '')

    return jsonify({
        'success': True,
        'woocommerce': {
            'wp_url_configured': bool(wp_url),
            'wp_url_preview': wp_url[:30] + '...' if len(wp_url) > 30 else wp_url,
            'consumer_key_configured': bool(ck),
            'consumer_key_preview': ck[:8] + '...' if len(ck) > 8 else ('OK' if ck else 'MISSING'),
            'consumer_secret_configured': bool(cs),
            'consumer_secret_preview': cs[:8] + '...' if len(cs) > 8 else ('OK' if cs else 'MISSING'),
        },
        'database': {
            'configured': bool(db_url),
            'type': 'MySQL' if 'mysql' in db_url.lower() else ('SQLite' if 'sqlite' in db_url.lower() else 'Unknown')
        },
        'base_image_url': bool(os.environ.get('BASE_IMAGE_URL', '')),
        'all_env_keys': [k for k in os.environ.keys() if not k.startswith('_')]
    })


@app.route('/api/diag/wc-test', methods=['GET'])
@require_auth
def diag_wc_test():
    """Teste la connexion WooCommerce en temps réel"""
    wcapi = get_wcapi()
    if not wcapi:
        return jsonify({
            'success': False,
            'message': 'WooCommerce non configuré. Vérifiez WP_URL, WP_CONSUMER_KEY, WP_CONSUMER_SECRET dans Railway.',
            'env_check': {
                'WP_URL': bool(os.environ.get('WP_URL', '')),
                'WP_CONSUMER_KEY': bool(os.environ.get('WP_CONSUMER_KEY', '')),
                'WP_CONSUMER_SECRET': bool(os.environ.get('WP_CONSUMER_SECRET', ''))
            }
        }), 400

    try:
        res = wcapi.get("products", params={"per_page": 1})
        return jsonify({
            'success': True,
            'wp_connected': res.status_code == 200,
            'wp_status': res.status_code,
            'wp_response_preview': str(res.json())[:200] if res.status_code == 200 else res.text[:200]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
            'error_type': type(e).__name__
        }), 502


# ============================================================
# AUTH ROUTES
# ============================================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'Username and password required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    if user.is_suspended:
        return jsonify({'success': False, 'message': 'Compte suspendu. Contactez un administrateur.'}), 403

    user.last_login = datetime.utcnow()
    db.session.commit()

    log_action('LOGIN', 'user', user.id, {'username': user.username, 'role': user.role})

    return jsonify({
        'success': True,
        'user': user.to_dict(),
        'token': f'fake-jwt-token-{user.id}'
    })


@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_me():
    return jsonify({'success': True, 'user': g.current_user.to_dict()})


@app.route('/api/auth/register', methods=['POST'])
@require_auth
@require_permission('user:create')
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()
    role = data.get('role', 'content_editor').strip()

    if not all([username, email, password]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if role not in VALID_ROLES:
        return jsonify({'success': False, 'message': f'Rôle invalide. Choix: {", ".join(VALID_ROLES)}'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Username already exists'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

    user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(password),
        role=role
    )
    db.session.add(user)
    db.session.commit()

    log_action('USER_CREATE', 'user', user.id, {'new_username': username, 'role': role})

    return jsonify({'success': True, 'user': user.to_dict()})




# ============================================================
# CONTACT / FORMULAIRE WEB (Pour HookSure / WordPress)
# ============================================================

@app.route('/api/contact', methods=['POST'])
def receive_contact():
    """Reçoit les soumissions du formulaire de devis - accepte tout format"""
    data = {}

    if request.is_json:
        data = request.get_json()
    elif request.form:
        data = request.form.to_dict()
    elif request.args:
        data = request.args.to_dict()
    else:
        try:
            data = request.get_json(force=True)
        except:
            data = {}

    safe_print(f"📨 Données reçues: {data}")
    safe_print(f"📨 Clés: {list(data.keys())}")

    secret = data.get('secret', '')
    expected_secret = os.environ.get('CONTACT_SECRET', '')
    if expected_secret and secret != expected_secret:
        return jsonify({'success': False, 'message': 'Clé secrète invalide'}), 403

    def find_value(*keys):
        for key in keys:
            if key in data and data[key]:
                return data[key]
        for k, v in data.items():
            for key in keys:
                if key in k and v:
                    return v
        return ''

    name = find_value('name', 'nom', 'sureforms_name', 'srfm-name')
    email = find_value('email', 'e-mail', 'sureforms_email', 'srfm-email', 'srfm-sender-email-field')
    phone = find_value('phone', 'telephone', 'tel', 'sureforms_phone', 'srfm-phone')
    message = find_value('message', 'msg', 'details', 'sureforms_message', 'srfm-message')
    product = find_value('product', 'produit', 'sureforms_product', 'srfm-product', 'embed_post_title')
    quantity = find_value('quantity', 'quantite', 'qty', 'sureforms_quantity', 'srfm-quantity')
    service = find_value('service', 'service_type', 'sureforms_service', 'srfm-service')
    message_type = find_value('message_type', 'type', 'msg_type')

    name = name or 'Anonyme'
    email = email or ''
    message = message or ''

    if not email:
        return jsonify({'success': False, 'message': 'Email requis'}), 400

    # Détection auto du type si non fourni
    if not message_type:
        if service and not product:
            message_type = 'service'
        elif product:
            message_type = 'devis'
        else:
            message_type = 'devis'

    msg = ContactMessage(
        name=name,
        email=email,
        phone=phone,
        subject=data.get('subject', 'Demande de ' + message_type),
        message=message,
        product=product,
        quantity=quantity,
        service=service,
        message_type=message_type,
        source=data.get('source', 'website')
    )
    db.session.add(msg)
    db.session.commit()

    email_sent = False
    try:
        email_sent = send_contact_email({
            'name': name, 'email': email, 'phone': phone,
            'message': message, 'product': product, 'quantity': quantity,
            'service': service, 'subject': msg.subject
        })
    except Exception as e:
        safe_print(f"⚠️ Erreur email: {e}")

    return jsonify({
        'success': True,
        'message': 'Message reçu' + (' et email envoyé' if email_sent else ''),
        'id': msg.id,
        'email_sent': email_sent
    }), 201

@app.route('/api/contact', methods=['GET'])
@require_auth
@require_permission('product:read')
def list_contacts():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    unread_only = request.args.get('unread', 'false').lower() == 'true'
    message_type = request.args.get('message_type', '')

    query = ContactMessage.query.order_by(ContactMessage.created_at.desc())
    if unread_only:
        query = query.filter_by(is_read=False)
    if message_type:
        query = query.filter_by(message_type=message_type)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'success': True,
        'data': [m.to_dict() for m in pagination.items],
        'pagination': {
            'page': page, 'per_page': per_page,
            'total': pagination.total, 'pages': pagination.pages
        }
    })


@app.route('/api/contact/<int:id>/read', methods=['POST'])
@require_auth
@require_permission('product:read')
def mark_contact_read(id):
    msg = ContactMessage.query.get_or_404(id)
    msg.is_read = True
    db.session.commit()
    return jsonify({'success': True, 'data': msg.to_dict()})


@app.route('/api/contact/<int:id>', methods=['DELETE'])
@require_auth
@require_permission('product:delete')
def delete_contact(id):
    msg = ContactMessage.query.get_or_404(id)
    db.session.delete(msg)
    db.session.commit()
    log_action('CONTACT_DELETE', 'contact', id, {'email': msg.email})
    return jsonify({'success': True, 'message': 'Message supprimé'})


@app.route('/api/contact/stats', methods=['GET'])
@require_auth
@require_permission('product:read')
def contact_stats():
    total = ContactMessage.query.count()
    unread = ContactMessage.query.filter_by(is_read=False).count()
    today = ContactMessage.query.filter(
        db.func.date(ContactMessage.created_at) == db.func.date(datetime.utcnow())
    ).count()
    devis = ContactMessage.query.filter_by(message_type='devis').count()
    service = ContactMessage.query.filter_by(message_type='service').count()
    return jsonify({
        'success': True,
        'data': {'total': total, 'unread': unread, 'today': today, 'devis': devis, 'service': service}
    })

# ============================================================
# USER MANAGEMENT ROUTES (Admin only)
# ============================================================

@app.route('/api/users', methods=['GET'])
@require_auth
@require_permission('user:read')
def get_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'success': True, 'data': [u.to_dict() for u in users]})


@app.route('/api/users/<int:id>', methods=['GET'])
@require_auth
@require_permission('user:read')
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify({'success': True, 'data': user.to_dict()})


@app.route('/api/users/<int:id>', methods=['PUT'])
@require_auth
@require_permission('user:update')
def update_user(id):
    user = User.query.get_or_404(id)
    data = request.get_json()

    old_data = {'username': user.username, 'email': user.email, 'role': user.role, 'is_suspended': user.is_suspended}

    if 'username' in data:
        user.username = data['username']
    if 'email' in data:
        user.email = data['email']
    if 'role' in data and data['role'] in VALID_ROLES:
        user.role = data['role']
    if 'password' in data and data['password']:
        user.password_hash = generate_password_hash(data['password'])
    if 'is_suspended' in data:
        user.is_suspended = bool(data['is_suspended'])

    db.session.commit()

    log_action('USER_UPDATE', 'user', user.id, {
        'old': old_data,
        'new': {'username': user.username, 'email': user.email, 'role': user.role, 'is_suspended': user.is_suspended}
    })

    return jsonify({'success': True, 'data': user.to_dict()})


@app.route('/api/users/<int:id>', methods=['DELETE'])
@require_auth
@require_permission('user:delete')
def delete_user(id):
    user = User.query.get_or_404(id)
    if user.id == g.current_user_id:
        return jsonify({'success': False, 'message': 'Vous ne pouvez pas supprimer votre propre compte'}), 400

    username = user.username
    db.session.delete(user)
    db.session.commit()

    log_action('USER_DELETE', 'user', id, {'deleted_username': username})

    return jsonify({'success': True, 'message': 'Utilisateur supprimé'})


@app.route('/api/users/<int:id>/suspend', methods=['POST'])
@require_auth
@require_permission('user:update')
def suspend_user(id):
    user = User.query.get_or_404(id)
    if user.id == g.current_user_id:
        return jsonify({'success': False, 'message': 'Vous ne pouvez pas suspendre votre propre compte'}), 400

    user.is_suspended = True
    db.session.commit()

    log_action('USER_SUSPEND', 'user', user.id, {'username': user.username})

    return jsonify({'success': True, 'message': f'Utilisateur {user.username} suspendu'})


@app.route('/api/users/<int:id>/activate', methods=['POST'])
@require_auth
@require_permission('user:update')
def activate_user(id):
    user = User.query.get_or_404(id)
    user.is_suspended = False
    db.session.commit()

    log_action('USER_ACTIVATE', 'user', user.id, {'username': user.username})

    return jsonify({'success': True, 'message': f'Utilisateur {user.username} réactivé'})


# ============================================================
# AUDIT LOG ROUTES
# ============================================================

@app.route('/api/audit-logs', methods=['GET'])
@require_auth
@require_permission('audit:read')
def get_audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    user_id = request.args.get('user_id', type=int)
    action = request.args.get('action', '')
    entity_type = request.args.get('entity_type', '')

    query = AuditLog.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    if action:
        query = query.filter(AuditLog.action.ilike(f'%{action}%'))
    if entity_type:
        query = query.filter_by(entity_type=entity_type)

    query = query.order_by(AuditLog.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'success': True,
        'data': [log.to_dict() for log in pagination.items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages
        }
    })


# ============================================================
# CATEGORY ROUTES
# ============================================================

@app.route('/api/categories', methods=['GET'])
@require_auth
@require_permission('category:read')
def get_categories():
    tree_mode = request.args.get('tree', 'false').lower() == 'true'
    parent_id = request.args.get('parent_id')

    if tree_mode:
        return jsonify({'success': True, 'data': build_category_tree()})

    query = Category.query
    if parent_id is not None:
        if parent_id == '':
            query = query.filter_by(parent_id=None)
        else:
            query = query.filter_by(parent_id=int(parent_id))

    categories = query.order_by(Category.sort_order, Category.name).all()
    return jsonify({'success': True, 'data': [c.to_dict() for c in categories]})


@app.route('/api/categories/tree', methods=['GET'])
@require_auth
@require_permission('category:read')
def get_category_tree():
    return jsonify({'success': True, 'data': build_category_tree()})


@app.route('/api/categories/<int:id>/descendants', methods=['GET'])
@require_auth
@require_permission('category:read')
def get_category_descendants_endpoint(id):
    category = Category.query.get_or_404(id)
    descendants = get_category_descendants(id)
    return jsonify({
        'success': True, 
        'category': category.to_dict(),
        'descendant_ids': descendants,
        'count': len(descendants)
    })


@app.route('/api/categories', methods=['POST'])
@require_auth
@require_permission('category:create')
def create_category():
    data = request.get_json()
    parent_id = data.get('parent_id')
    level = 0
    if parent_id:
        parent = Category.query.get(parent_id)
        if parent:
            level = parent.level + 1

    category = Category(
        name=data['name'],
        slug=data.get('slug', data['name'].lower().replace(' ', '-').replace('/', '-')),
        description=data.get('description'),
        parent_id=parent_id,
        level=level,
        sort_order=data.get('sort_order', 0)
    )
    db.session.add(category)
    db.session.commit()

    log_action('CATEGORY_CREATE', 'category', category.id, {'name': category.name})

    return jsonify({'success': True, 'data': category.to_dict()}), 201


@app.route('/api/categories/<int:id>', methods=['PUT'])
@require_auth
@require_permission('category:update')
def update_category(id):
    category = Category.query.get_or_404(id)
    data = request.get_json()

    old_name = category.name

    if 'name' in data:
        category.name = data['name']
    if 'slug' in data:
        category.slug = data['slug']
    if 'description' in data:
        category.description = data['description']
    if 'sort_order' in data:
        category.sort_order = data['sort_order']
    if 'parent_id' in data:
        new_parent_id = data['parent_id']
        if new_parent_id != category.parent_id:
            category.parent_id = new_parent_id
            if new_parent_id:
                parent = Category.query.get(new_parent_id)
                category.level = parent.level + 1 if parent else 0
            else:
                category.level = 0
            _update_children_level(category)

    db.session.commit()

    log_action('CATEGORY_UPDATE', 'category', category.id, {
        'old_name': old_name,
        'new_name': category.name
    })

    return jsonify({'success': True, 'data': category.to_dict()})


def _update_children_level(category):
    for child in category.children:
        child.level = category.level + 1
        _update_children_level(child)


@app.route('/api/categories/<int:id>', methods=['DELETE'])
@require_auth
@require_permission('category:delete')
def delete_category(id):
    category = Category.query.get_or_404(id)
    if category.children:
        return jsonify({'success': False, 'message': 'Cannot delete category with sub-categories'}), 400
    if category.products.count() > 0:
        return jsonify({'success': False, 'message': 'Cannot delete category with products'}), 400

    cat_name = category.name
    db.session.delete(category)
    db.session.commit()

    log_action('CATEGORY_DELETE', 'category', id, {'name': cat_name})

    return jsonify({'success': True, 'message': 'Category deleted'})


# ============================================================
# PRODUCT ROUTES
# ============================================================

@app.route('/api/products', methods=['GET'])
@require_auth
@require_permission('product:read')
def get_products():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', type=int)
    include_subcategories = request.args.get('include_subcategories', 'false').lower() == 'true'
    status = request.args.get('status', '')
    stock_status = request.args.get('stock_status', '')
    featured = request.args.get('featured', type=int)
    product_type = request.args.get('product_type', '')
    brand = request.args.get('brand', '')
    archived = request.args.get('archived', type=int)
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')

    query = Product.query

    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            )
        )

    if category_id:
        if include_subcategories:
            descendant_ids = get_category_descendants(category_id)
            query = query.filter(Product.category_id.in_(descendant_ids))
        else:
            query = query.filter_by(category_id=category_id)

    if status:
        query = query.filter_by(status=status)
    if stock_status:
        query = query.filter_by(stock_status=stock_status)
    if product_type:
        query = query.filter_by(product_type=product_type)
    if brand:
        query = query.filter(Product.brand.ilike(f'%{brand}%'))
    if featured is not None:
        query = query.filter_by(featured=bool(featured))
    if archived is not None:
        query = query.filter_by(archived=bool(archived))
    else:
        query = query.filter_by(archived=False)

    sort_column = getattr(Product, sort_by, Product.created_at)
    if sort_order == 'desc':
        sort_column = sort_column.desc()
    query = query.order_by(sort_column)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    products = pagination.items

    return jsonify({
        'success': True,
        'data': [p.to_dict() for p in products],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@app.route('/api/products/<int:id>', methods=['GET'])
@require_auth
@require_permission('product:read')
def get_product(id):
    product = Product.query.get_or_404(id)
    return jsonify({'success': True, 'data': product.to_dict()})


@app.route('/api/products', methods=['POST'])
@require_auth
@require_permission('product:create')
def create_product():
    try:
        data = request.form.to_dict()
        publish_to_wp = data.get('publish_to_wp') in ('true', '1', 'on')

        image_filename = None
        if 'image' in request.files:
            image_filename = save_uploaded_file(request.files['image'])

        gallery_files = []
        for key in request.files:
            if key.startswith('gallery_'):
                fname = save_uploaded_file(request.files[key])
                if fname:
                    gallery_files.append(fname)

        status = data.get('status', 'draft')
        if status not in ('draft', 'active', 'inactive'):
            status = 'draft'

        product = Product(
            name=clean_text(data.get('name')) or '',
            slug=clean_text(data.get('slug')) or (clean_text(data.get('name')) or '').lower().replace(' ', '-'),
            sku=clean_text(data.get('sku')) or f'POWERS-{uuid.uuid4().hex[:8].upper()}',
            description=clean_text(data.get('description')),
            short_description=clean_text(data.get('short_description')),
            price=parse_float(data.get('price')),
            sale_price=parse_float(data.get('sale_price')),
            cost_price=parse_float(data.get('cost_price')),
            stock_quantity=parse_int(data.get('stock_quantity')),
            stock_status=clean_text(data.get('stock_status')) or 'in_stock',
            weight=parse_float(data.get('weight')),
            dimensions=clean_text(data.get('dimensions')),
            image=image_filename,
            gallery=','.join(gallery_files) if gallery_files else None,
            category_id=parse_int(data.get('category_id'), None) if clean_text(data.get('category_id')) else None,
            tags=clean_text(data.get('tags')),
            status=status,
            product_type=clean_text(data.get('product_type')) or 'simple',
            brand=clean_text(data.get('brand')),
            attributes=clean_text(data.get('attributes')),
            variations=clean_text(data.get('variations')),
            featured=data.get('featured') == 'true' or data.get('featured') == '1',
            meta_title=clean_text(data.get('meta_title')),
            meta_description=clean_text(data.get('meta_description')),
            wp_sync_status='local',
            scheduled_publish_at=datetime.fromisoformat(data.get('scheduled_publish_at')) if data.get('scheduled_publish_at') else None
        )

        db.session.add(product)
        db.session.commit()

        if product.category_id:
            product.category = Category.query.get(product.category_id)

        # --- SYNC WP (isolé pour ne pas crasher la création du produit) ---
        wp_result = None
        if publish_to_wp and status == 'active':
            can_publish = ('*' in ROLE_PERMISSIONS.get(g.current_user.role, []) or 
                          'product:publish' in ROLE_PERMISSIONS.get(g.current_user.role, []))
            if can_publish:
                try:
                    wp_result = sync_product_to_wordpress(product)
                except Exception as wp_err:
                    safe_print(f"⚠️ Sync WP échouée mais produit sauvegardé: {wp_err}")
                    product.wp_sync_status = 'failed'
                    try:
                        db.session.commit()
                    except Exception as commit_err:
                        safe_print(f"❌ Impossible de sauver le statut failed: {commit_err}")

        log_action('PRODUCT_CREATE', 'product', product.id, {
            'name': product.name,
            'status': product.status,
            'published_to_wp': bool(wp_result),
            'sku': product.sku
        })

        return jsonify({'success': True, 'data': product.to_dict()}), 201

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e), 'error_type': type(e).__name__}), 400

@app.route('/api/products/<int:id>', methods=['PUT'])
@require_auth
@require_permission('product:update')
def update_product(id):
    try:
        product = Product.query.get_or_404(id)
        data = request.form.to_dict()
        publish_to_wp = data.get('publish_to_wp') in ('true', '1', 'on')

        old_data = {
            'name': product.name,
            'price': product.price,
            'stock_quantity': product.stock_quantity,
            'status': product.status
        }

        fields = ['name', 'slug', 'sku', 'description', 'short_description', 
                  'stock_status', 'dimensions', 'tags', 'status', 
                  'product_type', 'brand', 'attributes', 'variations',
                  'meta_title', 'meta_description']
        for field in fields:
            if field in data:
                value = clean_text(data[field])
                if field in ('name', 'status', 'stock_status', 'product_type'):
                    value = value or getattr(product, field)
                setattr(product, field, value)

        if 'price' in data:
            product.price = parse_float(data['price'])
        if 'sale_price' in data:
            product.sale_price = parse_float(data['sale_price'])
        if 'cost_price' in data:
            product.cost_price = parse_float(data['cost_price'])
        if 'stock_quantity' in data:
            product.stock_quantity = parse_int(data['stock_quantity'])
        if 'weight' in data:
            product.weight = parse_float(data['weight'])
        if 'category_id' in data:
            product.category_id = parse_int(data['category_id'], None) if clean_text(data['category_id']) else None
        if 'featured' in data:
            product.featured = data['featured'] == 'true' or data['featured'] == '1'
        if 'scheduled_publish_at' in data and data['scheduled_publish_at']:
            product.scheduled_publish_at = datetime.fromisoformat(data['scheduled_publish_at'])

        if 'image' in request.files and request.files['image'].filename:
            image_filename = save_uploaded_file(request.files['image'])
            if image_filename:
                product.image = image_filename

        gallery_files = []
        for key in request.files:
            if key.startswith('gallery_'):
                fname = save_uploaded_file(request.files[key])
                if fname:
                    gallery_files.append(fname)

        if gallery_files:
            existing = product.gallery.split(',') if product.gallery else []
            product.gallery = ','.join(existing + gallery_files)

        product.updated_at = datetime.utcnow()
        db.session.commit()

        if product.category_id:
            product.category = Category.query.get(product.category_id)

        # --- SYNC WP (isolé pour ne pas crasher la mise à jour du produit) ---
        wp_result = None
        if publish_to_wp and product.status == 'active' and not product.archived:
            can_publish = ('*' in ROLE_PERMISSIONS.get(g.current_user.role, []) or 
                          'product:publish' in ROLE_PERMISSIONS.get(g.current_user.role, []))
            if can_publish:
                try:
                    wp_result = sync_product_to_wordpress(product)
                except Exception as wp_err:
                    safe_print(f"⚠️ Sync WP échouée mais produit sauvegardé: {wp_err}")
                    product.wp_sync_status = 'failed'
                    try:
                        db.session.commit()
                    except Exception as commit_err:
                        safe_print(f"❌ Impossible de sauver le statut failed: {commit_err}")

        log_action('PRODUCT_UPDATE', 'product', product.id, {
            'old': old_data,
            'new': {
                'name': product.name,
                'price': product.price,
                'stock_quantity': product.stock_quantity,
                'status': product.status
            },
            'published_to_wp': bool(wp_result)
        })

        return jsonify({'success': True, 'data': product.to_dict()})
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e), 'error_type': type(e).__name__}), 400

@app.route('/api/products/<int:id>/publish', methods=['POST'])
@require_auth
@require_permission('product:publish')
def publish_product_to_wp(id):
    """Force la publication d'un produit sur WordPress"""
    product = Product.query.get_or_404(id)

    if product.archived:
        return jsonify({'success': False, 'message': 'Produit archivé, impossible de publier'}), 400

    if product.status != 'active':
        product.status = 'active'
        db.session.commit()

    wp_result = sync_product_to_wordpress(product)

    if wp_result:
        log_action('PRODUCT_PUBLISH_WP', 'product', product.id, {
            'name': product.name,
            'wp_product_id': wp_result.get('id')
        })
        return jsonify({
            'success': True,
            'message': 'Produit publié sur WordPress',
            'wp_product_id': wp_result.get('id'),
            'data': product.to_dict()
        })
    else:
        return jsonify({
            'success': False,
            'message': getattr(product, '_last_sync_error', None) or 'Échec de la publication sur WordPress. Vérifiez la configuration.'
        }), 502


@app.route('/api/products/<int:id>/duplicate', methods=['POST'])
@require_auth
@require_permission('product:duplicate')
def duplicate_product(id):
    """Duplique un produit existant"""
    original = Product.query.get_or_404(id)

    new_product = Product(
        name=f"{original.name} (Copie)",
        slug=f"{original.slug}-copy-{uuid.uuid4().hex[:6]}",
        sku=f"{original.sku}-COPY-{uuid.uuid4().hex[:4]}" if original.sku else None,
        description=original.description,
        short_description=original.short_description,
        price=original.price,
        sale_price=original.sale_price,
        cost_price=original.cost_price,
        stock_quantity=0,
        stock_status='in_stock',
        weight=original.weight,
        dimensions=original.dimensions,
        image=original.image,
        gallery=original.gallery,
        category_id=original.category_id,
        tags=original.tags,
        status='draft',
        product_type=original.product_type,
        brand=original.brand,
        attributes=original.attributes,
        variations=original.variations,
        featured=False,
        meta_title=original.meta_title,
        meta_description=original.meta_description,
        wp_sync_status='local',
        archived=False
    )

    db.session.add(new_product)
    db.session.commit()

    if new_product.category_id:
        new_product.category = Category.query.get(new_product.category_id)

    log_action('PRODUCT_DUPLICATE', 'product', new_product.id, {
        'original_id': original.id,
        'original_name': original.name,
        'new_name': new_product.name
    })

    return jsonify({
        'success': True,
        'message': 'Produit dupliqué',
        'data': new_product.to_dict()
    })


@app.route('/api/products/<int:id>/archive', methods=['POST'])
@require_auth
@require_permission('product:archive')
def archive_product(id):
    """Archive un produit (soft delete)"""
    product = Product.query.get_or_404(id)
    product.archived = True
    product.status = 'inactive'
    db.session.commit()

    log_action('PRODUCT_ARCHIVE', 'product', product.id, {'name': product.name})

    return jsonify({
        'success': True,
        'message': 'Produit archivé',
        'data': product.to_dict()
    })


@app.route('/api/products/<int:id>/restore', methods=['POST'])
@require_auth
@require_permission('product:archive')
def restore_product(id):
    """Restaure un produit archivé"""
    product = Product.query.get_or_404(id)
    product.archived = False
    db.session.commit()

    log_action('PRODUCT_RESTORE', 'product', product.id, {'name': product.name})

    return jsonify({
        'success': True,
        'message': 'Produit restauré',
        'data': product.to_dict()
    })


@app.route('/api/products/<int:id>', methods=['DELETE'])
@require_auth
@require_permission('product:delete')
def delete_product(id):
    try:
        product = Product.query.get_or_404(id)
        name = product.name
        db.session.delete(product)
        db.session.commit()

        log_action('PRODUCT_DELETE', 'product', id, {'name': name})

        return jsonify({'success': True, 'message': 'Product deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e), 'error_type': type(e).__name__}), 400


@app.route('/api/products/bulk-delete', methods=['POST'])
@require_auth
@require_permission('product:delete')
def bulk_delete_products():
    try:
        data = request.get_json()
        ids = data.get('ids', [])
        Product.query.filter(Product.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()

        log_action('PRODUCT_BULK_DELETE', 'product', None, {'count': len(ids), 'ids': ids})

        return jsonify({'success': True, 'message': f'{len(ids)} products deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e), 'error_type': type(e).__name__}), 400


@app.route('/api/products/publish-scheduled', methods=['POST'])
@require_auth
@require_permission('product:publish')
def publish_scheduled_products():
    """Publie les produits dont la date planifiée est atteinte"""
    now = datetime.utcnow()
    scheduled = Product.query.filter(
        Product.scheduled_publish_at <= now,
        Product.status == 'draft',
        Product.archived == False
    ).all()

    results = []
    for product in scheduled:
        product.status = 'active'
        db.session.commit()
        wp_result = sync_product_to_wordpress(product)
        results.append({
            'id': product.id,
            'name': product.name,
            'published': bool(wp_result)
        })
        log_action('PRODUCT_SCHEDULED_PUBLISH', 'product', product.id, {
            'name': product.name,
            'published': bool(wp_result)
        })

    return jsonify({
        'success': True,
        'message': f'{len(results)} produits publiés',
        'data': results
    })


# ==================== STATS ROUTE ====================

@app.route('/api/stats', methods=['GET'])
@require_auth
@require_permission('product:read')
def get_stats():
    total_products = Product.query.filter_by(archived=False).count()
    active_products = Product.query.filter_by(status='active', archived=False).count()
    draft_products = Product.query.filter_by(status='draft', archived=False).count()
    low_stock = Product.query.filter(Product.stock_quantity <= 5, Product.archived == False).count()
    out_of_stock = Product.query.filter_by(stock_status='out_of_stock', archived=False).count()
    categories_count = Category.query.count()
    variable_products = Product.query.filter_by(product_type='variable', archived=False).count()
    archived_products = Product.query.filter_by(archived=True).count()
    synced_products = Product.query.filter_by(wp_sync_status='synced', archived=False).count()

    return jsonify({
        'success': True,
        'data': {
            'total_products': total_products,
            'active_products': active_products,
            'draft_products': draft_products,
            'low_stock': low_stock,
            'out_of_stock': out_of_stock,
            'categories_count': categories_count,
            'variable_products': variable_products,
            'archived_products': archived_products,
            'synced_products': synced_products
        }
    })


# ==================== FILE SERVING ====================

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ==================== FRONTEND ROUTE ====================

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok'})
# ==================== MAIN ====================

init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)