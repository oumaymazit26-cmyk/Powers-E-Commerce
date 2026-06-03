# ============================================================
# POWERS E-Commerce - Dockerfile pour Railway
# ============================================================
FROM python:3.11-slim

# Dépendances système
RUN apt-get update && apt-get install -y     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*

# Répertoire de travail
WORKDIR /app

# Copier et installer les dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le code
COPY . .

# Créer le dossier uploads
RUN mkdir -p /app/static/uploads

# Port exposé
EXPOSE 8080

# Commande de démarrage
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "wsgi:application"]
