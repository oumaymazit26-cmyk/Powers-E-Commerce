const API = window.location.origin;
let currentUser = null;
let userPermissions = [];
let categoriesFlat = [];
let allCategoriesTree = [];
let currentAttributes = [];
let currentVariations = [];
let currentProductPage = 1;
let currentAuditPage = 1;
let currentArchivePage = 1;
let showingArchived = false;

/* ==================== AUTH & PERMISSIONS ==================== */
function getAuthHeaders() {
    const token = localStorage.getItem('powers_token');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

function hasPermission(perm) {
    if (!userPermissions) return false;
    return userPermissions.includes('*') || userPermissions.includes(perm);
}

function applyPermissions() {
    // Masquer/afficher les éléments selon les permissions
    const adminOnly = document.querySelectorAll('.admin-only');
    if (hasPermission('user:create')) {
        adminOnly.forEach(el => el.style.display = '');
    }

    if (!hasPermission('product:create')) {
        const btn = document.getElementById('btn-add-product');
        if (btn) btn.style.display = 'none';
    }
    if (!hasPermission('category:create')) {
        const btn = document.getElementById('btn-add-category');
        if (btn) btn.style.display = 'none';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('powers_token');
    if (token) { initAuth(); }

    document.getElementById('login-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('login-user').value.trim();
        const password = document.getElementById('login-pass').value.trim();

        try {
            const res = await fetch(`${API}/api/auth/login`, {
                method: 'POST',
                headers: {'Content-Type':'application/json'},
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.success) {
                currentUser = data.user;
                userPermissions = data.user.permissions || [];
                localStorage.setItem('powers_token', data.token);
                localStorage.setItem('powers_user', JSON.stringify(data.user));
                showMain();
                initApp();
            } else {
                document.getElementById('login-error').textContent = data.message || 'Identifiants invalides';
            }
        } catch (err) {
            document.getElementById('login-error').textContent = 'Erreur réseau. Vérifiez que le serveur tourne.';
        }
    });

    document.getElementById('logout-btn').addEventListener('click', () => {
        localStorage.clear();
        location.reload();
    });

    document.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const view = link.dataset.view;
            switchView(view);
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
        });
    });
});

async function initAuth() {
    try {
        const res = await fetch(`${API}/api/auth/me`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) {
            currentUser = data.user;
            userPermissions = data.user.permissions || [];
            localStorage.setItem('powers_user', JSON.stringify(data.user));
            showMain();
            initApp();
        } else {
            localStorage.clear();
        }
    } catch (e) {
        localStorage.clear();
    }
}

function showMain() {
    document.getElementById('login-view').style.display = 'none';
    document.getElementById('main-view').style.display = 'flex';
    const u = JSON.parse(localStorage.getItem('powers_user') || '{}');
    document.getElementById('user-name').textContent = u.username || 'admin';
    document.getElementById('user-role').textContent = u.role ? u.role.replace('_', ' ') : 'Admin';
    applyPermissions();
}

function switchView(view) {
    document.querySelectorAll('.view').forEach(v => v.style.display = 'none');
    document.getElementById(`${view}-view`).style.display = 'block';
    if (view === 'dashboard') loadStats();
    if (view === 'products') { showingArchived = false; loadProducts(); }
    if (view === 'categories') loadCategories();
    if (view === 'archive') { showingArchived = true; loadArchive(); }
    if (view === 'users') loadUsers();
    if (view === 'audit') loadAuditLogs();
}

function initApp() {
    loadStats();
    loadCategoriesSelect();
    checkWpStatus();
    loadMessageStats();
}

async function checkWpStatus() {
    // On vérifie indirectement via les stats si WP est configuré
    const badge = document.getElementById('wp-status-badge');
    const text = document.getElementById('wp-status-text');
    try {
        const res = await fetch(`${API}/api/stats`, { headers: getAuthHeaders() });
        if (res.ok) {
            text.textContent = 'Connecté';
            badge.className = 'badge badge-synced';
        }
    } catch (e) {
        text.textContent = 'Hors ligne';
        badge.className = 'badge badge-danger';
    }
}

/* ==================== TABS ==================== */
function switchTab(btn) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
}

/* ==================== TOAST ==================== */
function toast(msg, type='success') {
    const container = document.getElementById('toast-container');
    const div = document.createElement('div');
    div.className = `toast ${type}`;
    div.innerHTML = `<i class="fas fa-${type==='success'?'check-circle':type==='error'?'exclamation-circle':'info-circle'}"></i> ${msg}`;
    container.appendChild(div);
    setTimeout(() => div.remove(), 3500);
}

/* ==================== STATS ==================== */
async function loadStats() {
    try {
        const res = await fetch(`${API}/api/stats`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) {
            document.getElementById('st-total').textContent = data.data.total_products;
            document.getElementById('st-active').textContent = data.data.active_products;
            document.getElementById('st-draft').textContent = data.data.draft_products;
            document.getElementById('st-low').textContent = data.data.low_stock;
            document.getElementById('st-out').textContent = data.data.out_of_stock;
            document.getElementById('st-variable').textContent = data.data.variable_products;
            document.getElementById('st-archived').textContent = data.data.archived_products;
            document.getElementById('st-synced').textContent = data.data.synced_products;
        }
    } catch (e) { console.error('Stats error:', e); }
}

/* ==================== PRODUCTS ==================== */
async function loadProducts(page=1) {
    currentProductPage = page;
    const params = new URLSearchParams({ page, per_page: 10, archived: '0' });
    const search = document.getElementById('prod-search')?.value || '';
    const status = document.getElementById('prod-status')?.value || '';
    const stock = document.getElementById('prod-stock')?.value || '';
    const ptype = document.getElementById('prod-type')?.value || '';
    const sync = document.getElementById('prod-sync')?.value || '';
    if (search) params.append('search', search);
    if (status) params.append('status', status);
    if (stock) params.append('stock_status', stock);
    if (ptype) params.append('product_type', ptype);
    if (sync) params.append('wp_sync_status', sync);

    try {
        const res = await fetch(`${API}/api/products?${params}`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.getElementById('products-tbody');
        tbody.innerHTML = '';

        if (data.success) {
            data.data.forEach(p => {
                const tr = document.createElement('tr');
                const typeBadge = p.product_type === 'variable' 
                    ? '<span class="badge badge-info">Variable</span>' 
                    : '<span class="badge badge-secondary">Simple</span>';
                const statusBadge = p.status === 'active' 
                    ? '<span class="badge badge-success">Actif</span>'
                    : p.status === 'draft'
                    ? '<span class="badge badge-draft">Brouillon</span>'
                    : '<span class="badge badge-warning">Inactif</span>';
                const wpBadge = p.wp_sync_status === 'synced'
                    ? '<span class="badge badge-synced" title="ID WP: ' + (p.wp_product_id || '') + '"><i class="fas fa-check"></i></span>'
                    : p.wp_sync_status === 'failed'
                    ? '<span class="badge badge-failed"><i class="fas fa-times"></i></span>'
                    : '<span class="badge badge-local"><i class="fas fa-hdd"></i></span>';

                let actions = '';
                if (hasPermission('product:update')) {
                    actions += `<button class="btn btn-sm" onclick="editProduct(${p.id})" title="Modifier"><i class="fas fa-edit"></i></button>`;
                }
                if (hasPermission('product:publish') && p.wp_sync_status !== 'synced' && p.status === 'active') {
                    actions += `<button class="btn btn-sm btn-success" onclick="publishToWP(${p.id})" title="Publier sur WP"><i class="fas fa-cloud-upload-alt"></i></button>`;
                }
                if (hasPermission('product:duplicate')) {
                    actions += `<button class="btn btn-sm btn-secondary" onclick="duplicateProduct(${p.id})" title="Dupliquer"><i class="fas fa-copy"></i></button>`;
                }
                if (hasPermission('product:archive')) {
                    actions += `<button class="btn btn-sm btn-warning" onclick="archiveProduct(${p.id})" title="Archiver"><i class="fas fa-archive"></i></button>`;
                }
                if (hasPermission('product:delete')) {
                    actions += `<button class="btn btn-sm btn-danger" onclick="deleteProduct(${p.id})" title="Supprimer"><i class="fas fa-trash"></i></button>`;
                }

                tr.innerHTML = `
                    <td><strong>${p.name}</strong><br><small style="color:var(--gray-400)">${p.category ? p.category.name : '-'}</small></td>
                    <td>${typeBadge}</td>
                    <td>${p.sku || '-'}</td>
                    <td>${p.price ? p.price.toFixed(2) + ' €' : '-'}</td>
                    <td>${p.stock_quantity}</td>
                    <td>${statusBadge}</td>
                    <td>${wpBadge}</td>
                    <td><div class="action-btns">${actions}</div></td>
                `;
                tbody.appendChild(tr);
            });
            renderPagination(data.pagination, 'products-pagination', loadProducts);
        }
    } catch (e) { console.error('Products error:', e); }
}

async function loadArchive(page=1) {
    currentArchivePage = page;
    const params = new URLSearchParams({ page, per_page: 10, archived: '1' });
    try {
        const res = await fetch(`${API}/api/products?${params}`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.getElementById('archive-tbody');
        tbody.innerHTML = '';
        if (data.success) {
            data.data.forEach(p => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${p.name}</strong></td>
                    <td>${p.sku || '-'}</td>
                    <td>${p.price ? p.price.toFixed(2) + ' €' : '-'}</td>
                    <td>${p.updated_at ? new Date(p.updated_at).toLocaleDateString('fr-FR') : '-'}</td>
                    <td>
                        <div class="action-btns">
                            ${hasPermission('product:archive') ? `<button class="btn btn-sm btn-success" onclick="restoreProduct(${p.id})"><i class="fas fa-undo"></i> Restaurer</button>` : ''}
                            ${hasPermission('product:delete') ? `<button class="btn btn-sm btn-danger" onclick="deleteProduct(${p.id}, true)"><i class="fas fa-trash"></i> Supprimer définitivement</button>` : ''}
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
            renderPagination(data.pagination, 'archive-pagination', loadArchive);
        }
    } catch (e) { console.error('Archive error:', e); }
}

function toggleArchivedView() {
    showingArchived = !showingArchived;
    const btn = document.getElementById('btn-show-archived');
    if (showingArchived) {
        btn.innerHTML = '<i class="fas fa-box"></i> Voir actifs';
        loadArchive();
    } else {
        btn.innerHTML = '<i class="fas fa-archive"></i> Voir archivés';
        loadProducts();
    }
}

function renderPagination(pag, containerId, callback) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    for (let i = 1; i <= pag.pages; i++) {
        const btn = document.createElement('button');
        btn.textContent = i;
        if (i === pag.page) btn.className = 'active';
        btn.onclick = () => callback(i);
        container.appendChild(btn);
    }
}

/* ==================== PRODUCT MODAL ==================== */
function openProductModal() {
    document.getElementById('prod-id').value = '';
    document.getElementById('prod-modal-title').textContent = 'Nouveau produit';
    document.getElementById('product-form').reset();
    document.getElementById('p-type').value = 'simple';
    document.getElementById('p-status').value = 'draft';
    document.getElementById('p-publish-wp').checked = false;
    onProductTypeChange();
    currentAttributes = [];
    currentVariations = [];
    renderAttributesList();
    renderVariationsList();
    clearImagePreviews();
    loadCategoriesSelect();
    switchTab(document.querySelector('[data-tab="tab-general"]'));
    document.getElementById('product-modal').classList.add('active');
}

function closeModal(id) { 
    document.getElementById(id).classList.remove('active'); 
}

function onProductTypeChange() {
    const type = document.getElementById('p-type').value;
    const simplePricing = document.getElementById('simple-pricing');
    const varInfo = document.getElementById('variable-pricing-info');
    const btnAddVar = document.getElementById('btn-add-variation');

    if (type === 'variable') {
        simplePricing.style.opacity = '0.5';
        simplePricing.style.pointerEvents = 'none';
        varInfo.style.display = 'block';
        btnAddVar.style.display = 'inline-flex';
    } else {
        simplePricing.style.opacity = '1';
        simplePricing.style.pointerEvents = 'auto';
        varInfo.style.display = 'none';
        btnAddVar.style.display = 'none';
    }
}

/* ==================== ATTRIBUTES ==================== */
function addAttributeRow() {
    currentAttributes.push({ name: '', options: '', variation: true, visible: true });
    renderAttributesList();
}

function removeAttributeRow(index) {
    currentAttributes.splice(index, 1);
    renderAttributesList();
}

function updateAttribute(index, field, value) {
    currentAttributes[index][field] = value;
}

function renderAttributesList() {
    const container = document.getElementById('attributes-list');
    container.innerHTML = '';
    currentAttributes.forEach((attr, idx) => {
        const div = document.createElement('div');
        div.className = 'attribute-row';
        div.innerHTML = `
            <div class="attr-inputs">
                <input type="text" placeholder="Nom (ex: Couleur)" value="${attr.name}" onchange="updateAttribute(${idx}, 'name', this.value)">
                <input type="text" placeholder="Options (ex: Rouge, Bleu, Vert)" value="${attr.options}" onchange="updateAttribute(${idx}, 'options', this.value)">
                <label class="checkbox-label"><input type="checkbox" ${attr.variation ? 'checked' : ''} onchange="updateAttribute(${idx}, 'variation', this.checked)"> Variation</label>
                <label class="checkbox-label"><input type="checkbox" ${attr.visible ? 'checked' : ''} onchange="updateAttribute(${idx}, 'visible', this.checked)"> Visible</label>
            </div>
            <button type="button" class="btn-icon-delete" onclick="removeAttributeRow(${idx})"><i class="fas fa-times"></i></button>
        `;
        container.appendChild(div);
    });
}

/* ==================== VARIATIONS ==================== */
function addVariationRow() {
    currentVariations.push({ sku: '', regular_price: '', sale_price: '', stock_quantity: 0, weight: '', attributes: {} });
    renderVariationsList();
}

function removeVariationRow(index) {
    currentVariations.splice(index, 1);
    renderVariationsList();
}

function updateVariation(index, field, value) {
    currentVariations[index][field] = value;
}

function updateVariationAttr(varIdx, attrName, value) {
    if (!currentVariations[varIdx].attributes) currentVariations[varIdx].attributes = {};
    currentVariations[varIdx].attributes[attrName] = value;
}

function renderVariationsList() {
    const container = document.getElementById('variations-list');
    container.innerHTML = '';

    if (currentVariations.length === 0) {
        container.innerHTML = '<p class="empty-msg">Aucune variation. Cliquez sur "Ajouter une variation".</p>';
        return;
    }

    currentVariations.forEach((varObj, idx) => {
        const div = document.createElement('div');
        div.className = 'variation-card';

        let attrInputs = '';
        currentAttributes.forEach(attr => {
            if (attr.name) {
                const val = varObj.attributes && varObj.attributes[attr.name] ? varObj.attributes[attr.name] : '';
                attrInputs += `
                    <div class="form-group small">
                        <label>${attr.name}</label>
                        <input type="text" placeholder="${attr.options.split(',')[0] || ''}" value="${val}" 
                            onchange="updateVariationAttr(${idx}, '${attr.name.replace(/'/g, "\'")}', this.value)">
                    </div>
                `;
            }
        });

        div.innerHTML = `
            <div class="variation-header">
                <span class="var-number">#${idx + 1}</span>
                <button type="button" class="btn-icon-delete" onclick="removeVariationRow(${idx})"><i class="fas fa-trash"></i></button>
            </div>
            <div class="variation-body">
                <div class="form-grid-4">
                    <div class="form-group small"><label>SKU</label><input type="text" value="${varObj.sku}" onchange="updateVariation(${idx}, 'sku', this.value)"></div>
                    <div class="form-group small"><label>Prix</label><input type="number" step="0.01" value="${varObj.regular_price}" onchange="updateVariation(${idx}, 'regular_price', this.value)"></div>
                    <div class="form-group small"><label>Prix promo</label><input type="number" step="0.01" value="${varObj.sale_price}" onchange="updateVariation(${idx}, 'sale_price', this.value)"></div>
                    <div class="form-group small"><label>Stock</label><input type="number" value="${varObj.stock_quantity}" onchange="updateVariation(${idx}, 'stock_quantity', this.value)"></div>
                </div>
                <div class="form-grid-4">
                    <div class="form-group small"><label>Poids (kg)</label><input type="number" step="0.01" value="${varObj.weight}" onchange="updateVariation(${idx}, 'weight', this.value)"></div>
                    ${attrInputs}
                </div>
            </div>
        `;
        container.appendChild(div);
    });
}

/* ==================== IMAGES ==================== */
function previewImage(input, previewId) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = document.getElementById(previewId);
            img.src = e.target.result;
            img.style.display = 'block';
            input.parentElement.querySelector('.upload-placeholder').style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

function previewGalleryImage(input, slot) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const img = document.getElementById(`gallery-preview-${slot}`);
            img.src = e.target.result;
            img.style.display = 'block';
            const slotEl = document.querySelector(`.gallery-slot[data-slot="${slot}"]`);
            slotEl.querySelector('i').style.display = 'none';
        };
        reader.readAsDataURL(input.files[0]);
    }
}

function clearImagePreviews() {
    document.getElementById('main-image-preview').style.display = 'none';
    document.getElementById('main-image-preview').src = '';
    const placeholder = document.querySelector('#main-image-zone .upload-placeholder');
    if (placeholder) placeholder.style.display = 'flex';
    for (let i = 1; i <= 4; i++) {
        document.getElementById(`gallery-preview-${i}`).style.display = 'none';
        document.getElementById(`gallery-preview-${i}`).src = '';
        const slot = document.querySelector(`.gallery-slot[data-slot="${i}"] i`);
        if (slot) slot.style.display = 'block';
    }
}

/* ==================== SAVE PRODUCT ==================== */
document.getElementById('product-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('prod-id').value;
    const form = document.getElementById('product-form');
    const formData = new FormData(form);

    // Add attributes JSON
    const attrs = currentAttributes.map(a => ({
        name: a.name,
        slug: a.name.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''),
        options: a.options.split(',').map(o => o.trim()).filter(o => o),
        variation: a.variation,
        visible: a.visible
    })).filter(a => a.name && a.options.length > 0);
    formData.set('attributes', JSON.stringify(attrs));

    // Add variations JSON
    const vars = currentVariations.map(v => ({
        sku: v.sku,
        regular_price: v.regular_price,
        sale_price: v.sale_price || '',
        stock_quantity: parseInt(v.stock_quantity) || 0,
        weight: v.weight || '',
        attributes: v.attributes || {}
    })).filter(v => v.sku && v.regular_price);
    formData.set('variations', JSON.stringify(vars));

    const url = id ? `${API}/api/products/${id}` : `${API}/api/products`;
    const method = id ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, { method, headers: getAuthHeaders(), body: formData });
        const data = await res.json();
        if (data.success) {
            const wpMsg = data.data.wp_sync_status === 'synced' ? ' et publié sur WordPress' : '';
            toast(id ? `Produit mis à jour${wpMsg}` : `Produit créé${wpMsg}`);
            closeModal('product-modal');
            if (showingArchived) loadArchive(currentArchivePage);
            else loadProducts(currentProductPage);
            loadStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { 
        console.error('Save product error:', e);
        toast('Erreur lors de l\'enregistrement', 'error');
    }
});

async function editProduct(id) {
    try {
        const res = await fetch(`${API}/api/products/${id}`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (!data.success) return;
        const p = data.data;

        document.getElementById('prod-id').value = p.id;
        document.getElementById('p-name').value = p.name;
        document.getElementById('p-slug').value = p.slug || '';
        document.getElementById('p-sku').value = p.sku || '';
        document.getElementById('p-type').value = p.product_type || 'simple';
        document.getElementById('p-brand').value = p.brand || '';
        document.getElementById('p-tags').value = p.tags || '';
        document.getElementById('p-status').value = p.status;
        document.getElementById('p-short-desc').value = p.short_description || '';
        document.getElementById('p-desc').value = p.description || '';
        document.getElementById('p-featured').checked = p.featured;
        document.getElementById('p-price').value = p.price;
        document.getElementById('p-sale').value = p.sale_price || '';
        document.getElementById('p-cost').value = p.cost_price || '';
        document.getElementById('p-stock').value = p.stock_quantity;
        document.getElementById('p-stock-status').value = p.stock_status;
        document.getElementById('p-weight').value = p.weight || '';
        document.getElementById('p-dimensions').value = p.dimensions || '';
        document.getElementById('p-meta-title').value = p.meta_title || '';
        document.getElementById('p-meta-desc').value = p.meta_description || '';
        document.getElementById('p-scheduled').value = p.scheduled_publish_at ? p.scheduled_publish_at.slice(0, 16) : '';
        document.getElementById('p-publish-wp').checked = false;

        await loadCategoriesSelect();
        document.getElementById('p-category').value = p.category_id || '';

        if (p.attributes) {
            try {
                const attrs = typeof p.attributes === 'string' ? JSON.parse(p.attributes) : p.attributes;
                currentAttributes = attrs.map(a => ({
                    name: a.name,
                    options: Array.isArray(a.options) ? a.options.join(', ') : a.options,
                    variation: a.variation,
                    visible: a.visible
                }));
            } catch(e) { currentAttributes = []; }
        } else {
            currentAttributes = [];
        }
        renderAttributesList();

        if (p.variations) {
            try {
                const vars = typeof p.variations === 'string' ? JSON.parse(p.variations) : p.variations;
                currentVariations = vars.map(v => ({
                    sku: v.sku || '',
                    regular_price: v.regular_price || '',
                    sale_price: v.sale_price || '',
                    stock_quantity: v.stock_quantity || 0,
                    weight: v.weight || '',
                    attributes: v.attributes || {}
                }));
            } catch(e) { currentVariations = []; }
        } else {
            currentVariations = [];
        }
        renderVariationsList();

        onProductTypeChange();
        clearImagePreviews();

        document.getElementById('prod-modal-title').textContent = 'Modifier le produit';
        switchTab(document.querySelector('[data-tab="tab-general"]'));
        document.getElementById('product-modal').classList.add('active');
    } catch (e) { console.error('Edit product error:', e); }
}

async function deleteProduct(id, fromArchive=false) {
    const msg = fromArchive ? 'Supprimer définitivement ce produit ?' : 'Supprimer ce produit ?';
    if (!confirm(msg)) return;
    try {
        const res = await fetch(`${API}/api/products/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) { 
            toast('Produit supprimé'); 
            if (fromArchive) loadArchive(currentArchivePage);
            else loadProducts(currentProductPage);
            loadStats(); 
        }
        else toast(data.message, 'error');
    } catch (e) { console.error('Delete product error:', e); }
}

async function publishToWP(id) {
    if (!confirm('Publier ce produit sur WordPress ?')) return;
    try {
        const res = await fetch(`${API}/api/products/${id}/publish`, { 
            method: 'POST', 
            headers: getAuthHeaders() 
        });
        const data = await res.json();
        if (data.success) {
            toast('Produit publié sur WordPress !');
            loadProducts(currentProductPage);
            loadStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { 
        console.error('Publish error:', e);
        toast('Erreur de publication', 'error');
    }
}

async function duplicateProduct(id) {
    if (!confirm('Dupliquer ce produit ?')) return;
    try {
        const res = await fetch(`${API}/api/products/${id}/duplicate`, { 
            method: 'POST', 
            headers: getAuthHeaders() 
        });
        const data = await res.json();
        if (data.success) {
            toast('Produit dupliqué');
            loadProducts(currentProductPage);
            loadStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { 
        console.error('Duplicate error:', e);
        toast('Erreur de duplication', 'error');
    }
}

async function archiveProduct(id) {
    if (!confirm('Archiver ce produit ? Il ne sera plus visible dans la liste principale.')) return;
    try {
        const res = await fetch(`${API}/api/products/${id}/archive`, { 
            method: 'POST', 
            headers: getAuthHeaders() 
        });
        const data = await res.json();
        if (data.success) {
            toast('Produit archivé');
            loadProducts(currentProductPage);
            loadStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { 
        console.error('Archive error:', e);
        toast('Erreur lors de l\'archivage', 'error');
    }
}

async function restoreProduct(id) {
    try {
        const res = await fetch(`${API}/api/products/${id}/restore`, { 
            method: 'POST', 
            headers: getAuthHeaders() 
        });
        const data = await res.json();
        if (data.success) {
            toast('Produit restauré');
            loadArchive(currentArchivePage);
            loadStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { 
        console.error('Restore error:', e);
        toast('Erreur lors de la restauration', 'error');
    }
}

/* ==================== CATEGORIES ==================== */
async function loadCategories() {
    try {
        const res = await fetch(`${API}/api/categories?tree=true`, { headers: getAuthHeaders() });
        const data = await res.json();
        const container = document.getElementById('category-tree-root');
        container.innerHTML = '';
        if (data.success) {
            allCategoriesTree = data.data;
            renderCategoryNodes(allCategoriesTree, container);
            updateCategorySelects();
        }
    } catch (e) { console.error('Categories error:', e); }
}

function buildTreeOptions(nodes, prefix = '', isRoot = true) {
    let result = [];
    nodes.forEach((node, idx) => {
        const isLast = idx === nodes.length - 1;
        const connector = isLast ? '└─ ' : '├─ ';
        const childPrefix = isLast ? '    ' : '│   ';
        const fullPrefix = isRoot ? '' : prefix + connector;
        const nextPrefix = isRoot ? '' : prefix + childPrefix;
        result.push({ id: node.id, label: fullPrefix + node.name, level: node.level });
        if (node.children && node.children.length > 0) {
            result = result.concat(buildTreeOptions(node.children, nextPrefix, false));
        }
    });
    return result;
}

function updateCategorySelects() {
    if (!allCategoriesTree.length) return;
    const options = buildTreeOptions(allCategoriesTree);
    const pSel = document.getElementById('p-category');
    if (pSel) {
        const cur = pSel.value;
        pSel.innerHTML = '<option value="">-- Sans catégorie --</option>';
        options.forEach(o => {
            const opt = document.createElement('option');
            opt.value = o.id;
            opt.textContent = o.label;
            pSel.appendChild(opt);
        });
        pSel.value = cur;
    }
    const cSel = document.getElementById('c-parent');
    if (cSel) {
        const cur = cSel.value;
        cSel.innerHTML = '<option value="">-- Racine --</option>';
        options.filter(o => o.level < 3).forEach(o => {
            const opt = document.createElement('option');
            opt.value = o.id;
            opt.textContent = o.label;
            cSel.appendChild(opt);
        });
        cSel.value = cur;
    }
}

function renderCategoryNodes(nodes, container) {
    nodes.forEach(node => {
        const hasChildren = node.children && node.children.length > 0;
        const div = document.createElement('div');
        div.className = `cat-node level-${node.level}`;
        const icons = ['fas fa-folder', 'fas fa-folder-open', 'fas fa-cube', 'fas fa-tag'];
        const iconClass = icons[Math.min(node.level, 3)] || 'fas fa-tag';

        let actions = '';
        if (hasPermission('category:update')) {
            actions += `<button onclick="editCategory(${node.id})" title="Modifier"><i class="fas fa-edit"></i></button>`;
        }
        if (hasPermission('category:create')) {
            actions += `<button onclick="addSubCategory(${node.id})" title="Ajouter sous-catégorie"><i class="fas fa-plus"></i></button>`;
        }
        if (hasPermission('category:delete')) {
            actions += `<button class="btn-delete" onclick="deleteCategory(${node.id})" title="Supprimer"><i class="fas fa-trash"></i></button>`;
        }

        div.innerHTML = `
            <div class="cat-content">
                <button class="toggle-btn ${hasChildren ? '' : 'leaf'}" onclick="toggleCategoryNode(this)">
                    ${hasChildren ? '<i class="fas fa-chevron-right"></i>' : '<i class="fas fa-circle" style="font-size:6px"></i>'}
                </button>
                <div class="cat-icon"><i class="${iconClass}"></i></div>
                <div class="cat-info">
                    <h4>${node.name} <span class="lvl-badge lvl-${node.level}">Niv. ${node.level}</span></h4>
                    <span class="slug">${node.slug}</span>
                    ${node.description ? `<span class="desc">${node.description}</span>` : ''}
                </div>
                <div class="cat-actions">${actions}</div>
            </div>
            <div class="cat-children ${hasChildren ? '' : 'empty'}"></div>
        `;
        if (hasChildren) renderCategoryNodes(node.children, div.querySelector('.cat-children'));
        container.appendChild(div);
    });
}

function toggleCategoryNode(btn) {
    const node = btn.closest('.cat-node');
    const children = node.querySelector('.cat-children');
    const icon = btn.querySelector('i');
    if (!children || children.classList.contains('empty')) return;
    const isExpanded = children.classList.contains('expanded');
    if (isExpanded) {
        children.classList.remove('expanded');
        icon.className = 'fas fa-chevron-right';
    } else {
        children.classList.add('expanded');
        icon.className = 'fas fa-chevron-down';
    }
}

function expandAllCategories() {
    document.querySelectorAll('.cat-children').forEach(el => {
        if (!el.classList.contains('empty')) {
            el.classList.add('expanded');
            const icon = el.previousElementSibling?.querySelector('.toggle-btn i');
            if (icon) icon.className = 'fas fa-chevron-down';
        }
    });
}

function openCategoryModal() {
    document.getElementById('cat-id').value = '';
    document.getElementById('cat-modal-title').textContent = 'Nouvelle catégorie';
    document.getElementById('category-form').reset();
    document.getElementById('category-modal').classList.add('active');
}

function addSubCategory(parentId) {
    openCategoryModal();
    document.getElementById('c-parent').value = parentId;
    document.getElementById('cat-modal-title').textContent = 'Nouvelle sous-catégorie';
}

async function editCategory(id) {
    let found = null;
    const find = (nodes) => {
        for (const n of nodes) {
            if (n.id === id) { found = n; return; }
            if (n.children) find(n.children);
        }
    };
    find(allCategoriesTree);
    if (!found) return;
    document.getElementById('cat-id').value = found.id;
    document.getElementById('c-name').value = found.name;
    document.getElementById('c-slug').value = found.slug;
    document.getElementById('c-parent').value = found.parent_id || '';
    document.getElementById('c-desc').value = found.description || '';
    document.getElementById('c-order').value = found.sort_order || 0;
    document.getElementById('cat-modal-title').textContent = 'Modifier la catégorie';
    document.getElementById('category-modal').classList.add('active');
}

document.getElementById('category-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('cat-id').value;
    const payload = {
        name: document.getElementById('c-name').value,
        slug: document.getElementById('c-slug').value || undefined,
        description: document.getElementById('c-desc').value,
        parent_id: document.getElementById('c-parent').value || null,
        sort_order: parseInt(document.getElementById('c-order').value) || 0
    };
    const url = id ? `${API}/api/categories/${id}` : `${API}/api/categories`;
    const method = id ? 'PUT' : 'POST';
    try {
        const res = await fetch(url, {
            method,
            headers: { ...getAuthHeaders(), 'Content-Type':'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            toast(id ? 'Catégorie mise à jour' : 'Catégorie créée');
            closeModal('category-modal');
            loadCategories();
            loadCategoriesSelect();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { console.error('Save category error:', e); }
});

async function deleteCategory(id) {
    if (!confirm('Supprimer cette catégorie ?')) return;
    try {
        const res = await fetch(`${API}/api/categories/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) { toast('Catégorie supprimée'); loadCategories(); loadCategoriesSelect(); }
        else toast(data.message, 'error');
    } catch (e) { console.error('Delete category error:', e); }
}

async function loadCategoriesSelect() {
    if (allCategoriesTree.length === 0) {
        try {
            const res = await fetch(`${API}/api/categories?tree=true`, { headers: getAuthHeaders() });
            const data = await res.json();
            if (data.success) {
                allCategoriesTree = data.data;
                updateCategorySelects();
            }
        } catch (e) { console.error('Load categories select error:', e); }
    } else {
        updateCategorySelects();
    }
}

/* ==================== USER MANAGEMENT ==================== */
async function loadUsers() {
    if (!hasPermission('user:read')) {
        toast('Permission refusée', 'error');
        return;
    }
    try {
        const res = await fetch(`${API}/api/users`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.getElementById('users-tbody');
        tbody.innerHTML = '';
        if (data.success) {
            data.data.forEach(u => {
                const tr = document.createElement('tr');
                const statusHtml = u.is_suspended 
                    ? '<span class="user-status"><span class="dot dot-suspended"></span> Suspendu</span>'
                    : '<span class="user-status"><span class="dot dot-active"></span> Actif</span>';

                let actions = '';
                if (hasPermission('user:update')) {
                    actions += `<button class="btn btn-sm" onclick="editUser(${u.id})" title="Modifier"><i class="fas fa-edit"></i></button>`;
                }
                if (hasPermission('user:update') && !u.is_suspended) {
                    actions += `<button class="btn btn-sm btn-warning" onclick="suspendUser(${u.id})" title="Suspendre"><i class="fas fa-ban"></i></button>`;
                }
                if (hasPermission('user:update') && u.is_suspended) {
                    actions += `<button class="btn btn-sm btn-success" onclick="activateUser(${u.id})" title="Réactiver"><i class="fas fa-check"></i></button>`;
                }
                if (hasPermission('user:delete')) {
                    actions += `<button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id})" title="Supprimer"><i class="fas fa-trash"></i></button>`;
                }

                tr.innerHTML = `
                    <td>${u.id}</td>
                    <td><strong>${u.username}</strong></td>
                    <td>${u.email}</td>
                    <td><span class="badge badge-secondary">${u.role.replace('_', ' ')}</span></td>
                    <td>${statusHtml}</td>
                    <td>${u.last_login ? new Date(u.last_login).toLocaleString('fr-FR') : 'Jamais'}</td>
                    <td><div class="action-btns">${actions}</div></td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (e) { console.error('Users error:', e); }
}

function openUserModal() {
    if (!hasPermission('user:create')) {
        toast('Permission refusée', 'error');
        return;
    }
    document.getElementById('u-id').value = '';
    document.getElementById('user-modal-title').textContent = 'Nouvel utilisateur';
    document.getElementById('user-form').reset();
    document.getElementById('u-pass-hint').textContent = '*';
    document.getElementById('u-password').required = true;
    document.getElementById('user-modal').classList.add('active');
}

async function editUser(id) {
    if (!hasPermission('user:update')) return;
    try {
        const res = await fetch(`${API}/api/users/${id}`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (!data.success) return;
        const u = data.data;

        document.getElementById('u-id').value = u.id;
        document.getElementById('u-username').value = u.username;
        document.getElementById('u-email').value = u.email;
        document.getElementById('u-role').value = u.role;
        document.getElementById('u-suspended').checked = u.is_suspended;
        document.getElementById('u-password').value = '';
        document.getElementById('u-password').required = false;
        document.getElementById('u-pass-hint').textContent = '(laisser vide pour ne pas changer)';
        document.getElementById('user-modal-title').textContent = 'Modifier l\'utilisateur';
        document.getElementById('user-modal').classList.add('active');
    } catch (e) { console.error('Edit user error:', e); }
}

document.getElementById('user-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('u-id').value;
    const payload = {
        username: document.getElementById('u-username').value,
        email: document.getElementById('u-email').value,
        role: document.getElementById('u-role').value,
        is_suspended: document.getElementById('u-suspended').checked
    };
    const password = document.getElementById('u-password').value;
    if (password) payload.password = password;

    const url = id ? `${API}/api/users/${id}` : `${API}/api/auth/register`;
    const method = id ? 'PUT' : 'POST';

    try {
        const res = await fetch(url, {
            method,
            headers: { ...getAuthHeaders(), 'Content-Type':'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            toast(id ? 'Utilisateur mis à jour' : 'Utilisateur créé');
            closeModal('user-modal');
            loadUsers();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { console.error('Save user error:', e); }
});

async function deleteUser(id) {
    if (!confirm('Supprimer cet utilisateur ? Cette action est irréversible.')) return;
    try {
        const res = await fetch(`${API}/api/users/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) { toast('Utilisateur supprimé'); loadUsers(); }
        else toast(data.message, 'error');
    } catch (e) { console.error('Delete user error:', e); }
}

async function suspendUser(id) {
    if (!confirm('Suspendre cet utilisateur ? Il ne pourra plus se connecter.')) return;
    try {
        const res = await fetch(`${API}/api/users/${id}/suspend`, { method: 'POST', headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) { toast('Utilisateur suspendu'); loadUsers(); }
        else toast(data.message, 'error');
    } catch (e) { console.error('Suspend user error:', e); }
}

async function activateUser(id) {
    try {
        const res = await fetch(`${API}/api/users/${id}/activate`, { method: 'POST', headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) { toast('Utilisateur réactivé'); loadUsers(); }
        else toast(data.message, 'error');
    } catch (e) { console.error('Activate user error:', e); }
}

/* ==================== AUDIT LOG ==================== */
async function loadAuditLogs(page=1) {
    currentAuditPage = page;
    if (!hasPermission('audit:read')) {
        toast('Permission refusée', 'error');
        return;
    }
    const params = new URLSearchParams({ page, per_page: 50 });
    const search = document.getElementById('audit-search')?.value || '';
    const entity = document.getElementById('audit-entity')?.value || '';
    if (search) params.append('action', search);
    if (entity) params.append('entity_type', entity);

    try {
        const res = await fetch(`${API}/api/audit-logs?${params}`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.getElementById('audit-tbody');
        tbody.innerHTML = '';
        if (data.success) {
            data.data.forEach(log => {
                const tr = document.createElement('tr');
                const actionClass = `audit-action-${log.action}`;
                let details = '';
                if (log.details) {
                    try {
                        const d = JSON.parse(log.details);
                        details = Object.entries(d).map(([k,v]) => `${k}: ${JSON.stringify(v)}`).join(', ');
                    } catch(e) { details = log.details; }
                }
                tr.innerHTML = `
                    <td style="white-space:nowrap">${new Date(log.created_at).toLocaleString('fr-FR')}</td>
                    <td><strong>${log.username}</strong></td>
                    <td><span class="audit-action ${actionClass}">${log.action}</span></td>
                    <td>${log.entity_type || '-'} ${log.entity_id ? '(#'+log.entity_id+')' : ''}</td>
                    <td>
                        ${details ? `<div class="audit-details" title="${details}">${details}</div>` : '-'}
                    </td>
                `;
                tbody.appendChild(tr);
            });
            renderPagination(data.pagination, 'audit-pagination', loadAuditLogs);
        }
    } catch (e) { console.error('Audit error:', e); }
}



/* ==================== MESSAGES / CONTACT ==================== */
let currentMessagePage = 1;

async function loadMessageStats() {
    try {
        const res = await fetch(`${API}/api/contact/stats`, { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.success) {
            const badge = document.getElementById('msg-badge');
            if (badge && data.data.unread > 0) {
                badge.textContent = data.data.unread;
                badge.style.display = 'inline-flex';
            } else if (badge) {
                badge.style.display = 'none';
            }
        }
    } catch (e) { console.error('Message stats error:', e); }
}

async function loadMessages(page=1) {
    currentMessagePage = page;
    const params = new URLSearchParams({ page, per_page: 15 });
    const filter = document.getElementById('msg-filter')?.value || '';
    const search = document.getElementById('msg-search')?.value || '';
    if (filter === 'unread') params.append('unread', 'true');

    try {
        const res = await fetch(`${API}/api/contact?${params}`, { headers: getAuthHeaders() });
        const data = await res.json();
        const tbody = document.getElementById('messages-tbody');
        tbody.innerHTML = '';

        if (data.success) {
            // Stats dans la vue
            const statsRes = await fetch(`${API}/api/contact/stats`, { headers: getAuthHeaders() });
            const statsData = await statsRes.json();
            if (statsData.success) {
                document.getElementById('msg-total').textContent = statsData.data.total;
                document.getElementById('msg-unread').textContent = statsData.data.unread;
                document.getElementById('msg-today').textContent = statsData.data.today;
                const statsText = document.getElementById('msg-stats');
                if (statsText) statsText.textContent = `${statsData.data.unread} non lu(s)`;
            }
            loadMessageStats(); // Mettre à jour le badge sidebar

            if (data.data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="8" class="empty-msg">Aucun message</td></tr>';
            } else {
                data.data.forEach(m => {
                    const tr = document.createElement('tr');
                    if (!m.is_read) tr.style.fontWeight = '600';
                    tr.style.background = m.is_read ? '' : 'rgba(37,99,235,0.03)';

                    const dateStr = new Date(m.created_at).toLocaleString('fr-FR', {
                        day: '2-digit', month: '2-digit', year: 'numeric',
                        hour: '2-digit', minute: '2-digit'
                    });

                    const readIcon = m.is_read
                        ? '<i class="fas fa-envelope-open" style="color:var(--gray-400)"></i>'
                        : '<i class="fas fa-envelope" style="color:var(--primary)"></i>';

                    const productInfo = m.product || m.subject || '-';

                    let actions = '';
                    if (!m.is_read) {
                        actions += `<button class="btn btn-sm btn-success" onclick="markMessageRead(${m.id})" title="Marquer comme lu"><i class="fas fa-check"></i></button>`;
                    }
                    actions += `<button class="btn btn-sm btn-danger" onclick="deleteMessage(${m.id})" title="Supprimer"><i class="fas fa-trash"></i></button>`;

                    tr.innerHTML = `
                        <td style="text-align:center">${readIcon}</td>
                        <td style="white-space:nowrap;font-size:13px">${dateStr}</td>
                        <td><strong>${m.name}</strong></td>
                        <td><a href="mailto:${m.email}">${m.email}</a></td>
                        <td>${m.phone || '-'}</td>
                        <td><span class="badge badge-info">${productInfo}</span> ${m.quantity ? `<small style="color:var(--gray-500)">Qté: ${m.quantity}</small>` : ''}</td>
                        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis" title="${m.message.replace(/"/g, '&quot;')}">${m.message}</td>
                        <td><div class="action-btns">${actions}</div></td>
                    `;
                    tbody.appendChild(tr);
                });
            }
            renderPagination(data.pagination, 'messages-pagination', loadMessages);
        }
    } catch (e) { console.error('Messages error:', e); }
}

async function markMessageRead(id) {
    try {
        const res = await fetch(`${API}/api/contact/${id}/read`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.success) {
            toast('Message marqué comme lu');
            loadMessages(currentMessagePage);
        }
    } catch (e) { console.error('Mark read error:', e); }
}

async function deleteMessage(id) {
    if (!confirm('Supprimer ce message ?')) return;
    try {
        const res = await fetch(`${API}/api/contact/${id}`, {
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        const data = await res.json();
        if (data.success) {
            toast('Message supprimé');
            loadMessages(currentMessagePage);
            loadMessageStats();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { console.error('Delete message error:', e); }
}

window.onclick = function(e) {
    if (e.target.classList.contains('modal')) e.target.classList.remove('active');
};