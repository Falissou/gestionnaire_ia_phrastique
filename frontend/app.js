const state = { products: [], commands: [], movements: [], alerts: [], agents: [] };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));
let toastTimer;

async function api(path, options = {}) {
  const token = localStorage.getItem("pharmastock-token");
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.detail || `Erreur API (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function notify(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

function dateText(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  const parsed = new Date(year, month - 1, day);
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString("fr-FR");
}

function statusFor(product) {
  if ((product.quantity ?? 0) === 0) return ["Rupture", "low"];
  if (product.expiry_date) {
    const [year, month, day] = String(product.expiry_date).slice(0, 10).split("-").map(Number);
    const expiryDay = new Date(year, month - 1, day);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const days = Math.round((expiryDay - today) / 86400000);
    if (days < 0) return ["Périmé", "expired"];
    if (days <= 90) return ["Expiration proche", "soon"];
  }
  if (product.quantity <= product.min_quantity) return ["Stock faible", "low"];
  return ["En stock", "ok"];
}

function alertMarkup(alert) {
  const symbol = alert.severity === "critical" ? "!" : "◉";
  return `<div class="alert-row"><span class="alert-symbol ${escapeHtml(alert.severity)}">${symbol}</span><div class="alert-copy"><strong>${escapeHtml(alert.product)}</strong><span>${escapeHtml(alert.message)}</span></div></div>`;
}

function renderDashboard(data) {
  $("#metric-products").textContent = data.product_count;
  $("#metric-units").textContent = data.total_units.toLocaleString("fr-FR");
  $("#metric-orders").textContent = data.pending_commands;
  $("#metric-alerts").textContent = data.low_stock_count + data.expiry_alert_count;
  $("#alert-count").textContent = data.low_stock_count + data.expiry_alert_count;
  $("#dashboard-alerts").innerHTML = data.alerts.length ? data.alerts.map(alertMarkup).join("") : '<div class="empty-state">Aucune alerte. Votre stock est sous contrôle.</div>';
  $("#recent-movements").innerHTML = data.recent_movements.length
    ? data.recent_movements.map((item) => `<div class="movement-row"><strong>${escapeHtml(item.product_name)}</strong><span class="type-tag ${escapeHtml(item.type)}">${item.type === "entree" ? "Entrée" : "Sortie"}</span><span>${escapeHtml(item.reason)}</span><span>${dateText(item.date)}</span></div>`).join("")
    : '<div class="empty-state">Aucun mouvement enregistré.</div>';
}

function renderProducts() {
  const query = $("#product-search").value.trim().toLocaleLowerCase("fr");
  const filtered = state.products.filter((item) => `${item.name} ${item.category}`.toLocaleLowerCase("fr").includes(query));
  $("#product-total").textContent = `${filtered.length} produit(s)`;
  $("#products-table").innerHTML = filtered.length ? filtered.map((product) => {
    const [label, cls] = statusFor(product);
    return `<tr><td><strong>${escapeHtml(product.name)}</strong></td><td>${escapeHtml(product.category)}</td><td><strong>${product.quantity}</strong></td><td>${product.min_quantity}</td><td>${dateText(product.expiry_date)}</td><td><span class="stock-tag ${cls}">${label}</span></td></tr>`;
  }).join("") : '<tr><td colspan="6" class="empty-state">Aucun produit à afficher.</td></tr>';
}

function renderMovements() {
  $("#movements-table").innerHTML = state.movements.length ? state.movements.slice().reverse().map((item) => `<tr><td>${dateText(item.date)}</td><td><strong>${escapeHtml(item.product_name)}</strong></td><td><span class="type-tag ${escapeHtml(item.type)}">${item.type === "entree" ? "Entrée" : "Sortie"}</span></td><td>${item.quantity}</td><td>${escapeHtml(item.reason)}</td><td>${escapeHtml(item.reference || "—")}</td></tr>`).join("") : '<tr><td colspan="6" class="empty-state">Aucun mouvement enregistré.</td></tr>';
}

function renderCommands() {
  $("#commands-table").innerHTML = state.commands.length ? state.commands.map((item) => `<tr><td><strong>${escapeHtml(item.product_name)}</strong></td><td>${item.quantity}</td><td>${escapeHtml(item.supplier)}</td><td>${dateText(item.expected_date)}</td><td><span class="stock-tag ${item.status === "Reçue" ? "ok" : "soon"}">${escapeHtml(item.status)}</span></td><td><select class="command-status" data-id="${escapeHtml(item.id)}"><option ${item.status === "En attente" ? "selected" : ""}>En attente</option><option ${item.status === "Commandée" ? "selected" : ""}>Commandée</option><option ${item.status === "Reçue" ? "selected" : ""}>Reçue</option><option ${item.status === "Annulée" ? "selected" : ""}>Annulée</option></select></td></tr>`).join("") : '<tr><td colspan="6" class="empty-state">Aucune commande enregistrée.</td></tr>';
  document.querySelectorAll(".command-status").forEach((select) => select.addEventListener("change", async () => {
    try {
      await api(`/commands/${encodeURIComponent(select.dataset.id)}`, { method: "PATCH", body: JSON.stringify({ status: select.value }) });
      await refresh();
      notify("Statut de commande mis à jour.");
    } catch (error) { notify(error.message); }
  }));
}

function renderAlerts() {
  $("#all-alerts").innerHTML = state.alerts.length ? state.alerts.map((item) => `<article class="alert-card ${escapeHtml(item.severity)}"><strong>${escapeHtml(item.product)}</strong><p>${escapeHtml(item.message)}</p></article>`).join("") : '<div class="panel empty-state">Aucune alerte de stock ou d’expiration.</div>';
}

async function refresh() {
  const [dashboard, products, commands, movements, alerts, agents] = await Promise.all([
    api("/dashboard"), api("/products"), api("/commands"), api("/movements"), api("/alerts"), api("/agents"),
  ]);
  state.products = products;
  state.commands = commands;
  state.movements = movements;
  state.alerts = alerts;
  state.agents = agents;
  renderDashboard(dashboard);
  renderProducts();
  renderCommands();
  renderMovements();
  renderAlerts();
  $("#chat-agent").innerHTML = agents.map((agent) => `<option value="${escapeHtml(agent.name)}">${escapeHtml(agent.name)}</option>`).join("");
  $("#chat-agent").value = agents.at(-1)?.name || "";
}

const field = (name, label, type = "text", options = {}) => {
  let control;
  if (options.choices) {
    control = `<select name="${name}" ${options.required === false ? "" : "required"}>${options.choices.map(([value, text]) => `<option value="${escapeHtml(value)}">${escapeHtml(text)}</option>`).join("")}</select>`;
  } else {
    control = `<input name="${name}" type="${type}" ${options.required === false ? "" : "required"} ${options.min !== undefined ? `min="${options.min}"` : ""} ${options.step ? `step="${options.step}"` : ""} ${options.value ? `value="${escapeHtml(options.value)}"` : ""}>`;
  }
  return `<div class="field ${options.full ? "full" : ""}"><label>${label}</label>${control}</div>`;
};

function openForm(title, fields, submit) {
  $("#dialog-title").textContent = title;
  $("#form-fields").innerHTML = `<div class="form-grid">${fields}</div>`;
  $("#form-dialog").showModal();
  $("#data-form").onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = Object.fromEntries(form.entries());
    try {
      await submit(payload);
      $("#form-dialog").close();
      event.currentTarget.reset();
      await refresh();
      notify("Enregistrement effectué.");
    } catch (error) { notify(error.message); }
  };
}

$("#add-product").addEventListener("click", () => openForm("Ajouter un produit", [
  field("name", "Nom du produit", "text", { full: true }),
  field("category", "Catégorie", "text", { value: "Médicament" }),
  field("quantity", "Quantité", "number", { min: 0 }),
  field("min_quantity", "Seuil minimum", "number", { min: 0, value: "5" }),
  field("unit_price", "Prix unitaire (€)", "number", { min: 0, step: "0.01", value: "0" }),
  field("expiry_date", "Date d'expiration", "date", { required: false }),
], (data) => api("/products", { method: "POST", body: JSON.stringify({ ...data, quantity: Number(data.quantity), min_quantity: Number(data.min_quantity), unit_price: Number(data.unit_price), expiry_date: data.expiry_date || null }) })));

$("#add-command").addEventListener("click", () => openForm("Nouvelle commande", [
  field("product_name", "Produit", "text", { full: true }),
  field("quantity", "Quantité", "number", { min: 1 }),
  field("supplier", "Fournisseur", "text"),
  field("expected_date", "Date de livraison prévue", "date", { required: false }),
], (data) => api("/commands", { method: "POST", body: JSON.stringify({ ...data, quantity: Number(data.quantity), expected_date: data.expected_date || null }) })));

$("#add-movement").addEventListener("click", () => openForm("Enregistrer un mouvement", [
  field("product_id", "Produit", "text", { choices: state.products.map((item) => [item.id, `${item.name} (${item.quantity} en stock)`]), full: true }),
  field("type", "Type de mouvement", "text", { choices: [["entree", "Entrée"], ["sortie", "Sortie"]] }),
  field("quantity", "Quantité", "number", { min: 1 }),
  field("reason", "Motif", "text", { full: true }),
  field("reference", "Référence (facultatif)", "text", { required: false }),
], (data) => api("/movements", { method: "POST", body: JSON.stringify({ ...data, quantity: Number(data.quantity), reference: data.reference || null }) })));

$("#product-search").addEventListener("input", renderProducts);
$("#send-alert-email").addEventListener("click", async () => {
  const recipient = window.prompt("Adresse e-mail du destinataire :");
  if (!recipient) return;
  try {
    const result = await api("/alerts/email", { method: "POST", body: JSON.stringify({ recipient }) });
    notify(`${result.alert_count} alerte(s) envoyée(s) à ${result.recipient}.`);
  } catch (error) { notify(error.message); }
});
document.querySelectorAll("[data-view]").forEach((link) => link.addEventListener("click", (event) => {
  event.preventDefault();
  const view = link.dataset.view;
  document.querySelectorAll(".view").forEach((section) => section.classList.add("hidden"));
  $(`#${view}-view`).classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.toggle("active", item.dataset.view === view));
  $("#page-title").textContent = { dashboard: "Tableau de bord", stock: "Produits & stock", mouvements: "Entrées & sorties", commandes: "Commandes fournisseurs", veille: "Veille & alertes" }[view];
}));

document.querySelectorAll("[data-open-chat]").forEach((button) => button.addEventListener("click", () => $("#chat-dialog").showModal()));
$("#close-chat").addEventListener("click", () => $("#chat-dialog").close());
$("#chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("#chat-message");
  const message = input.value.trim();
  if (!message) return;
  const box = $("#chat-messages");
  box.insertAdjacentHTML("beforeend", `<div class="chat-bubble user">${escapeHtml(message)}</div>`);
  input.value = "";
  const waiting = document.createElement("div");
  waiting.className = "chat-bubble assistant";
  waiting.textContent = "Analyse en cours…";
  box.append(waiting);
  box.scrollTop = box.scrollHeight;
  try {
    const answer = await api(`/agents/${encodeURIComponent($("#chat-agent").value)}/chat`, { method: "POST", body: JSON.stringify({ message }) });
    waiting.textContent = answer.reply;
  } catch (error) { waiting.textContent = error.message; }
  box.scrollTop = box.scrollHeight;
});

$("#token-button").addEventListener("click", () => {
  const current = localStorage.getItem("pharmastock-token") || "";
  const token = window.prompt("Jeton d'accès Microsoft Entra (laisser vide pour le supprimer) :", current);
  if (token === null) return;
  if (token.trim()) localStorage.setItem("pharmastock-token", token.trim());
  else localStorage.removeItem("pharmastock-token");
  refresh().then(() => notify("Connexion actualisée.")).catch((error) => notify(error.message));
});

$("#today-label").textContent = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long" }).format(new Date());
refresh().catch((error) => notify(`Connexion impossible : ${error.message}`));
