"""
POWERS E-Commerce Product Management App v2.0
Backend: Flask + SQLAlchemy + WooCommerce Sync + RBAC + Audit Log + Draft/Live
"""

import os
import json
import uuid
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

# ============================================================
# FLASK APP CONFIG
# ============================================================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'powers-ecommerce-secret-key-2024')

# --- CONFIGURATION BASE DE DONNÉES ---
# Option 1: SQLite (Gratuit, parfait pour Render débutant)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///powers_db.sqlite3')

# Option 2: MySQL (Production - décommentez si vous avez un serveur MySQL)
# DB_USER = os.environ.get('DB_USER', 'root')
# DB_PASSWORD = os.environ.get('DB_PASSWORD', 'qwertyuiop123')
# DB_HOST = os.environ.get('DB_HOST', 'localhost')
# DB_NAME = os.environ.get('DB_NAME', 'powers_db')
# app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
CORS(app)

# ============================================================
# WOOCOMMERCE CONFIG
# ============================================================
WP_URL = os.environ.get('WP_URL', '').strip()
WP_CONSUMER_KEY = os.environ.get('WP_CONSUMER_KEY', '').strip()
WP_CONSUMER_SECRET = os.environ.get('WP_CONSUMER_SECRET', '').strip()
BASE_IMAGE_URL = os.environ.get('BASE_IMAGE_URL', '').strip()

wcapi = None
if WP_URL and WP_CONSUMER_KEY and WP_CONSUMER_SECRET:
    try:
        wcapi = API(
            url=WP_URL,
            consumer_key=WP_CONSUMER_KEY,
            consumer_secret=WP_CONSUMER_SECRET,
            version="wc/v3",
            timeout=30
        )
        print(f"✅ WooCommerce connecté: {WP_URL}")
    except Exception as e:
        print(f"❌ Erreur connexion WooCommerce: {e}")
else:
    print("⚠️ WooCommerce non configuré")


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


def save_uploaded_file(file):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
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


def get_public_base_url():
    if BASE_IMAGE_URL:
        return BASE_IMAGE_URL.rstrip('/')
    return request.host_url.rstrip('/')


def get_current_user():
    """Récupère l'utilisateur courant depuis le token Bearer"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ')[1]
    # Format: fake-jwt-token-{user_id}
    try:
        user_id = int(token.split('-')[-1])
        user = User.query.get(user_id)
        return user
    except (ValueError, IndexError):
        return None


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'message': 'Authentification requise'}), 401
        if user.is_suspended:
            return jsonify({'success': False, 'message': 'Compte suspendu. Contactez un administrateur.'}), 403
        g.current_user = user
        g.current_user_id = user.id
        g.current_username = user.username
        return f(*args, **kwargs)
    return decorated


def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'success': False, 'message': 'Authentification requise'}), 401
            if user.is_suspended:
                return jsonify({'success': False, 'message': 'Compte suspendu'}), 403
            perms = ROLE_PERMISSIONS.get(user.role, [])
            if '*' not in perms and permission not in perms:
                return jsonify({'success': False, 'message': 'Permission refusée'}), 403
            g.current_user = user
            g.current_user_id = user.id
            g.current_username = user.username
            return f(*args, **kwargs)
        return decorated
    return decorator


def log_action(action, entity_type=None, entity_id=None, details=None):
    """Enregistre une action dans le journal d'audit"""
    try:
        user_id = getattr(g, 'current_user_id', None)
        username = getattr(g, 'current_username', 'system')
        log = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Erreur audit log: {e}")


# ==================== DATABASE MODELS ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default='content_editor')
    is_suspended = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def to_dict(self, include_sensitive=False):
        data = {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_suspended': self.is_suspended,
            'permissions': ROLE_PERMISSIONS.get(self.role, []),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
        if include_sensitive:
            data['password_hash'] = self.password_hash
        return data


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'username': self.username,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    level = db.Column(db.Integer, default=0)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parent = db.relationship('Category', remote_side=[id], backref='children')
    products = db.relationship('Product', backref='category', lazy='dynamic')

    def to_dict(self, include_children=False):
        data = {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'parent_id': self.parent_id,
            'level': self.level,
            'sort_order': self.sort_order,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_children:
            data['children'] = [child.to_dict(include_children=True) for child in 
                               sorted(self.children, key=lambda x: x.sort_order)]
        return data


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    sku = db.Column(db.String(100), unique=True)
    description = db.Column(db.Text)
    short_description = db.Column(db.String(500))
    price = db.Column(db.Float, nullable=False, default=0.0)
    sale_price = db.Column(db.Float, default=0.0)
    cost_price = db.Column(db.Float, default=0.0)
    stock_quantity = db.Column(db.Integer, default=0)
    stock_status = db.Column(db.String(20), default='in_stock')
    weight = db.Column(db.Float, default=0.0)
    dimensions = db.Column(db.String(100))
    image = db.Column(db.String(255))
    gallery = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    tags = db.Column(db.String(255))
    status = db.Column(db.String(20), default='draft')  # draft, active, inactive, archived

    product_type = db.Column(db.String(20), default='simple')
    brand = db.Column(db.String(100))
    attributes = db.Column(db.Text)
    variations = db.Column(db.Text)

    featured = db.Column(db.Boolean, default=False)
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.String(500))

    # Draft vs Live
    wp_sync_status = db.Column(db.String(20), default='local')  # local, synced, failed
    wp_product_id = db.Column(db.Integer, nullable=True)
    scheduled_publish_at = db.Column(db.DateTime, nullable=True)
    archived = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'sku': self.sku,
            'description': self.description,
            'short_description': self.short_description,
            'price': self.price,
            'sale_price': self.sale_price,
            'cost_price': self.cost_price,
            'stock_quantity': self.stock_quantity,
            'stock_status': self.stock_status,
            'weight': self.weight,
            'dimensions': self.dimensions,
            'image': self.image,
            'gallery': self.gallery,
            'category_id': self.category_id,
            'category': self.category.to_dict() if self.category else None,
            'tags': self.tags,
            'status': self.status,
            'product_type': self.product_type,
            'brand': self.brand,
            'attributes': self.attributes,
            'variations': self.variations,
            'featured': self.featured,
            'meta_title': self.meta_title,
            'meta_description': self.meta_description,
            'wp_sync_status': self.wp_sync_status,
            'wp_product_id': self.wp_product_id,
            'scheduled_publish_at': self.scheduled_publish_at.isoformat() if self.scheduled_publish_at else None,
            'archived': self.archived,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }




class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    product = db.Column(db.String(200))
    quantity = db.Column(db.String(50))
    source = db.Column(db.String(50), default='website')
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'subject': self.subject,
            'message': self.message,
            'product': self.product,
            'quantity': self.quantity,
            'source': self.source,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# ============================================================
# SYNCHRONISATION WOOCOMMERCE
# ============================================================
def sync_product_to_wordpress(product):
    if not wcapi:
        print("⚠️ WooCommerce non configuré, sync ignorée")
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

        # Marque → Attribut + MetaData
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

        # Attributs pour produits variables
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
                print(f"⚠️ Erreur parsing attributs: {e}")

        # Catégorie
        if product.category:
            cat_name = product.category.name
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

        # Images
        base_url = get_public_base_url()
        if base_url and product.image:
            data["images"].append({"src": f"{base_url}/uploads/{product.image}", "position": 0})

        if base_url and product.gallery:
            for idx, img in enumerate(product.gallery.split(',')):
                img = img.strip()
                if img:
                    data["images"].append({
                        "src": f"{base_url}/uploads/{img}",
                        "position": idx + 1
                    })

        # Envoi produit parent
        if existing_id:
            res = wcapi.put(f"products/{existing_id}", data)
            wp_product = res.json() if res.status_code in (200, 201) else None
            action = "mis à jour"
        else:
            res = wcapi.post("products", data)
            wp_product = res.json() if res.status_code == 201 else None
            action = "créé"

        if not wp_product or 'id' not in wp_product:
            print(f"❌ Erreur WooCommerce: {res.status_code} - {res.text[:300]}")
            product.wp_sync_status = 'failed'
            db.session.commit()
            return None

        parent_id = wp_product['id']
        product.wp_product_id = parent_id
        product.wp_sync_status = 'synced'
        db.session.commit()
        print(f"🔄 Produit WooCommerce {action} (ID: {parent_id})")

        # Sync variations si produit variable
        if ptype == 'variable' and product.variations:
            sync_variations_to_wc(product, parent_id)

        return wp_product

    except Exception as e:
        print(f"❌ Exception sync: {e}")
        import traceback
        traceback.print_exc()
        product.wp_sync_status = 'failed'
        db.session.commit()
        return None


def sync_variations_to_wc(product, parent_id):
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
                print(f"  ↳ Variation {sku} mise à jour" if r.status_code in (200,201) else f"  ⚠️ Err update var {sku}")
            else:
                r = wcapi.post(f"products/{parent_id}/variations", var_data)
                print(f"  ↳ Variation {sku} créée" if r.status_code == 201 else f"  ⚠️ Err create var {sku}")

    except Exception as e:
        print(f"❌ Erreur sync variations: {e}")


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
            print('✅ Admin créé: admin / admin123')

        print(f'✅ Base initialisée. Messages: {ContactMessage.query.count()}')
        if Category.query.count() == 0:
            print("⚠️ Aucune catégorie trouvée. Exécutez le script SQL powers_db_mysql.sql")




def send_contact_email(data):
    """Envoie un email de notification pour un nouveau contact"""
    smtp_host = os.environ.get('SMTP_HOST', '').strip()
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USER', '').strip()
    smtp_pass = os.environ.get('SMTP_PASSWORD', '').strip()
    to_email = os.environ.get('CONTACT_EMAIL', 'comercial@technoclim.ma').strip()

    if not all([smtp_host, smtp_user, smtp_pass]):
        print("⚠️ SMTP non configuré, email non envoyé")
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
        print(f"✅ Email envoyé à {to_email}")
        return True
    except Exception as e:
        print(f"❌ Erreur envoi email: {e}")
        import traceback
        traceback.print_exc()
        return False

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
    """Reçoit les soumissions du formulaire de devis du site web

    Cette route est appelée par HookSure (WordPress) ou tout autre webhook.
    Pas besoin d'authentification - sécurisée par clé secrète optionnelle.
    """
    data = request.get_json() or request.form.to_dict()

    # Vérification clé secrète optionnelle (sécurité basique)
    secret = data.get('secret', '')
    expected_secret = os.environ.get('CONTACT_SECRET', '')
    if expected_secret and secret != expected_secret:
        return jsonify({'success': False, 'message': 'Clé secrète invalide'}), 403

    if not data.get('email') or not data.get('message'):
        return jsonify({'success': False, 'message': 'Email et message requis'}), 400

    msg = ContactMessage(
        name=data.get('name', 'Anonyme'),
        email=data.get('email'),
        phone=data.get('phone'),
        subject=data.get('subject', 'Demande de devis'),
        message=data.get('message'),
        product=data.get('product'),
        quantity=data.get('quantity'),
        source=data.get('source', 'website')
    )
    db.session.add(msg)
    db.session.commit()

    # Envoi simultané de l'email à comercial@technoclim.ma
    email_sent = send_contact_email(data)

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

    query = ContactMessage.query.order_by(ContactMessage.created_at.desc())
    if unread_only:
        query = query.filter_by(is_read=False)

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
    return jsonify({
        'success': True,
        'data': {'total': total, 'unread': unread, 'today': today}
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
        # Par défaut, ne pas montrer les archivés
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
            name=data.get('name', ''),
            slug=data.get('slug', data.get('name', '').lower().replace(' ', '-')),
            sku=data.get('sku'),
            description=data.get('description'),
            short_description=data.get('short_description'),
            price=float(data.get('price', 0)),
            sale_price=float(data.get('sale_price', 0)) if data.get('sale_price') else 0,
            cost_price=float(data.get('cost_price', 0)) if data.get('cost_price') else 0,
            stock_quantity=int(data.get('stock_quantity', 0)),
            stock_status=data.get('stock_status', 'in_stock'),
            weight=float(data.get('weight', 0)) if data.get('weight') else 0,
            dimensions=data.get('dimensions'),
            image=image_filename,
            gallery=','.join(gallery_files) if gallery_files else None,
            category_id=int(data.get('category_id')) if data.get('category_id') else None,
            tags=data.get('tags'),
            status=status,
            product_type=data.get('product_type', 'simple'),
            brand=data.get('brand'),
            attributes=data.get('attributes'),
            variations=data.get('variations'),
            featured=data.get('featured') == 'true' or data.get('featured') == '1',
            meta_title=data.get('meta_title'),
            meta_description=data.get('meta_description'),
            wp_sync_status='local',
            scheduled_publish_at=datetime.fromisoformat(data.get('scheduled_publish_at')) if data.get('scheduled_publish_at') else None
        )

        db.session.add(product)
        db.session.commit()

        if product.category_id:
            product.category = Category.query.get(product.category_id)

        # Sync WordPress uniquement si demandé ET permission
        wp_result = None
        if publish_to_wp and status == 'active':
            if '*' in ROLE_PERMISSIONS.get(g.current_user.role, []) or 'product:publish' in ROLE_PERMISSIONS.get(g.current_user.role, []):
                wp_result = sync_product_to_wordpress(product)
            else:
                product.wp_sync_status = 'local'
                db.session.commit()

        log_action('PRODUCT_CREATE', 'product', product.id, {
            'name': product.name,
            'status': product.status,
            'published_to_wp': bool(wp_result),
            'sku': product.sku
        })

        return jsonify({'success': True, 'data': product.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400


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
                setattr(product, field, data[field])

        if 'price' in data:
            product.price = float(data['price'])
        if 'sale_price' in data:
            product.sale_price = float(data['sale_price'])
        if 'cost_price' in data:
            product.cost_price = float(data['cost_price'])
        if 'stock_quantity' in data:
            product.stock_quantity = int(data['stock_quantity'])
        if 'weight' in data:
            product.weight = float(data['weight'])
        if 'category_id' in data:
            product.category_id = int(data['category_id']) if data['category_id'] else None
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

        # Sync WordPress
        wp_result = None
        if publish_to_wp and product.status == 'active' and not product.archived:
            if '*' in ROLE_PERMISSIONS.get(g.current_user.role, []) or 'product:publish' in ROLE_PERMISSIONS.get(g.current_user.role, []):
                wp_result = sync_product_to_wordpress(product)

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
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 400


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
            'message': 'Échec de la publication sur WordPress. Vérifiez la configuration.'
        }), 500


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
        return jsonify({'success': False, 'message': str(e)}), 400


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
        return jsonify({'success': False, 'message': str(e)}), 400


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


# ==================== MAIN ====================

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)