# POWERS - E-Commerce Product Management App

Application web complète de gestion de produits e-commerce développée pour l'entreprise **POWERS**.

## 🚀 Fonctionnalités

### Backend (Python Flask)
- ✅ API REST complète (CRUD produits, catégories)
- ✅ Authentification utilisateur (admin/éditeur)
- ✅ Upload d'images produits
- ✅ Filtrage, recherche et pagination
- ✅ Gestion des stocks (en stock, faible, rupture)
- ✅ Statistiques tableau de bord

### Frontend (HTML/CSS/JS)
- ✅ Interface responsive et moderne
- ✅ Tableau de bord avec statistiques
- ✅ Liste des produits avec filtres avancés
- ✅ Formulaire d'ajout/édition de produit
- ✅ Upload d'images avec preview
- ✅ Gestion des catégories
- ✅ Pagination
- ✅ Notifications toast
- ✅ Authentification sécurisée

## 🛠 Stack Technique

| Couche | Technologie |
|--------|-------------|
| Backend | Python 3.12 + Flask |
| ORM | Flask-SQLAlchemy |
| Base de données | SQLite (démo) / MySQL (production) |
| CORS | Flask-CORS |
| Frontend | HTML5 + CSS3 + Vanilla JavaScript |
| Icons | Font Awesome 6 |

## 📦 Installation

### 1. Cloner/Extraire le projet
```bash
cd powers-ecommerce
```

### 2. Créer un environnement virtuel (recommandé)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Configuration MySQL (Production)
Modifier `app.py` ligne 24 :
```python
# SQLite (développement)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///powers_db.sqlite3'

# MySQL (production)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://user:password@localhost/powers_db'
```

Créer la base de données MySQL :
```sql
CREATE DATABASE powers_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 5. Lancer l'application
```bash
python app.py
```

L'application sera accessible sur : **http://localhost:5000**

## 🔑 Identifiants par défaut

| Rôle | Nom d'utilisateur | Mot de passe |
|------|-------------------|--------------|
| Admin | admin | admin123 |

## 📁 Structure du projet

```
powers-ecommerce/
├── app.py                  # Application Flask (backend)
├── requirements.txt        # Dépendances Python
├── README.md              # Documentation
├── powers_db.sqlite3      # Base de données SQLite
├── static/
│   ├── css/
│   │   └── style.css      # Styles CSS
│   ├── js/
│   │   └── app.js         # Frontend JavaScript
│   └── uploads/           # Images téléchargées
└── templates/
    └── index.html         # Interface utilisateur
```

## 🔌 API Endpoints

### Authentification
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/api/auth/login` | Connexion |
| POST | `/api/auth/register` | Inscription |

### Produits
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/products` | Liste des produits (avec filtres) |
| GET | `/api/products/<id>` | Détail d'un produit |
| POST | `/api/products` | Créer un produit |
| PUT | `/api/products/<id>` | Modifier un produit |
| DELETE | `/api/products/<id>` | Supprimer un produit |
| POST | `/api/products/bulk-delete` | Suppression multiple |

### Catégories
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/categories` | Liste des catégories |
| POST | `/api/categories` | Créer une catégorie |

### Statistiques
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/stats` | Statistiques tableau de bord |

## 🎨 Modèle de données

### Product (Produit)
- `id` - Identifiant
- `name` - Nom
- `slug` - URL friendly
- `sku` - Référence
- `description` - Description
- `price` - Prix
- `sale_price` - Prix promo
- `cost_price` - Prix d'achat
- `stock_quantity` - Quantité stock
- `stock_status` - Statut stock
- `image` - Image principale
- `category_id` - Catégorie
- `status` - active/inactive/draft
- `featured` - En vedette

### Category (Catégorie)
- `id` - Identifiant
- `name` - Nom
- `slug` - URL
- `description` - Description

### User (Utilisateur)
- `id` - Identifiant
- `username` - Nom d'utilisateur
- `email` - Email
- `password_hash` - Mot de passe hashé
- `role` - admin/editor

## 🚀 Déploiement Production

### Avec Gunicorn (Linux)
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

### Avec Waitress (Windows)
```bash
pip install waitress
waitress-serve --port=5000 app:app
```

### Variables d'environnement
```bash
export SECRET_KEY="votre-cle-secrete"
export DATABASE_URL="mysql+pymysql://user:password@localhost/powers_db"
export FLASK_ENV="production"
```

## 📝 Notes

- Les images sont stockées dans `static/uploads/`
- Par défaut, l'application utilise SQLite pour faciliter les tests
- Pour la production, passer à MySQL et configurer un serveur web (Nginx/Apache)
- Les mots de passe sont hashés avec Werkzeug

---

**Développé pour POWERS E-Commerce** | Stage 2024
