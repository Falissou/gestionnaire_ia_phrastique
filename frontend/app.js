const state = { products: [], commands: [], movements: [], alerts: [] };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));
let toastTimer;
let commandImportFile = null;
let commandImportPreviewId = null;
let dataImportFile = null;
let dataImportPreviewId = null;
let referenceFiles = [];

async function api(path, options = {}) {
  const token = localStorage.getItem("pharmastock-token");
  const headers = { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) };
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
    return `<tr><td>${escapeHtml(product.product_code || "—")}</td><td><strong>${escapeHtml(product.name)}</strong></td><td>${escapeHtml(product.category)}</td><td><strong>${product.quantity}</strong></td><td>${product.min_quantity}</td><td>${dateText(product.expiry_date)}</td><td><span class="stock-tag ${cls}">${label}</span></td></tr>`;
  }).join("") : '<tr><td colspan="7" class="empty-state">Aucun produit à afficher.</td></tr>';
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
  const [dashboard, products, commands, movements, alerts] = await Promise.all([
    api("/dashboard"), api("/products"), api("/commands"), api("/movements"), api("/alerts"),
  ]);
  state.products = products;
  state.commands = commands;
  state.movements = movements;
  state.alerts = alerts;
  renderDashboard(dashboard);
  renderProducts();
  renderCommands();
  renderMovements();
  renderAlerts();
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
  field("product_code", "Code produit", "text", { required: false }),
  field("name", "Nom du produit", "text", { full: true }),
  field("category", "Catégorie", "text", { value: "Médicament" }),
  field("quantity", "Quantité", "number", { min: 0 }),
  field("min_quantity", "Seuil minimum", "number", { min: 0, value: "5" }),
  field("unit_price", "Prix unitaire (€)", "number", { min: 0, step: "0.01", value: "0" }),
  field("expiry_date", "Date d'expiration", "date", { required: false }),
], (data) => api("/products", { method: "POST", body: JSON.stringify({ ...data, product_code: data.product_code || null, quantity: Number(data.quantity), min_quantity: Number(data.min_quantity), unit_price: Number(data.unit_price), expiry_date: data.expiry_date || null }) })));

$("#add-command").addEventListener("click", () => openForm("Nouvelle commande", [
  field("product_name", "Produit", "text", { full: true }),
  field("quantity", "Quantité", "number", { min: 1 }),
  field("supplier", "Fournisseur", "text"),
  field("expected_date", "Date de livraison prévue", "date", { required: false }),
], (data) => api("/commands", { method: "POST", body: JSON.stringify({ ...data, quantity: Number(data.quantity), expected_date: data.expected_date || null }) })));

$("#import-commands").addEventListener("click", () => {
  commandImportFile = null;
  commandImportPreviewId = null;
  $("#command-file").value = "";
  $("#import-preview").innerHTML = "";
  $("#confirm-command-import").disabled = true;
  $("#import-dialog").showModal();
});
$("#command-file").addEventListener("change", () => {
  commandImportFile = $("#command-file").files[0] || null;
  commandImportPreviewId = null;
  $("#import-preview").innerHTML = "";
  $("#confirm-command-import").disabled = true;
});
$("#preview-command-import").addEventListener("click", async () => {
  commandImportPreviewId = null;
  if (!commandImportFile) {
    notify("Sélectionnez un fichier CSV ou Excel.");
    return;
  }
  const form = new FormData();
  form.append("file", commandImportFile);
  try {
    const preview = await api("/commands/import/preview", { method: "POST", body: form });
    commandImportPreviewId = preview.preview_id;
    const rows = preview.rows.map((row) => {
      const status = row.status === "ready" ? "Prête" : row.status === "duplicate" ? "Doublon ignoré" : "À corriger";
      return `<tr><td>${row.row}</td><td>${escapeHtml(row.product_name)}</td><td>${escapeHtml(row.quantity)}</td><td>${escapeHtml(row.supplier)}</td><td>${escapeHtml(row.expected_date || "—")}</td><td><span class="import-status ${row.status}">${status}</span>${row.error ? `<small>${escapeHtml(row.error)}</small>` : ""}</td></tr>`;
    }).join("");
    $("#import-preview").innerHTML = `<p class="import-summary">${preview.ready_count} commande(s) prête(s), ${preview.duplicate_count} doublon(s), ${preview.invalid_count} ligne(s) à corriger.</p><div class="table-wrap"><table><thead><tr><th>LIGNE</th><th>PRODUIT</th><th>QUANTITÉ</th><th>FOURNISSEUR</th><th>LIVRAISON</th><th>ÉTAT</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    $("#confirm-command-import").disabled = preview.invalid_count > 0 || preview.ready_count === 0;
  } catch (error) {
    $("#import-preview").innerHTML = `<p class="import-error">${escapeHtml(error.message)}</p>`;
    $("#confirm-command-import").disabled = true;
  }
});
$("#confirm-command-import").addEventListener("click", async () => {
  if (!commandImportPreviewId) return;
  const form = new FormData();
  form.append("preview_id", commandImportPreviewId);
  try {
    const result = await api("/commands/import", { method: "POST", body: form });
    commandImportPreviewId = null;
    $("#import-dialog").close();
    await refresh();
    notify(`${result.created_count} commande(s) ajoutée(s), ${result.duplicate_count} doublon(s) ignoré(s).`);
  } catch (error) {
    notify(error.message);
    commandImportPreviewId = null;
    $("#confirm-command-import").disabled = true;
  }
});
$("#close-import").addEventListener("click", () => $("#import-dialog").close());

function updateReferenceOptions() {
  dataImportPreviewId = null;
  $("#data-import-preview").innerHTML = "";
  $("#confirm-data-import").disabled = true;
  const target = $("#migration-target").value;
  const select = $("#reference-file");
  const current = select.value;
  select.innerHTML = '<option value="">Choisir un fichier local à téléverser…</option>' +
    referenceFiles.filter((item) => item.target === target).map((item) =>
      `<option value="${escapeHtml(item.filename)}">${escapeHtml(item.filename)}</option>`).join("");
  if (referenceFiles.some((item) => item.target === target && item.filename === current)) {
    select.value = current;
  }
  const movements = target === "entree" || target === "sortie";
  $("#adjust-import-stock").disabled = !movements;
  $("#adjust-import-stock").checked = false;
}

function migrationFormData() {
  const form = new FormData();
  form.append("target", $("#migration-target").value);
  form.append("adjust_stock", String($("#adjust-import-stock").checked));
  if (dataImportFile) form.append("file", dataImportFile);
  else if ($("#reference-file").value) form.append("reference_file", $("#reference-file").value);
  return form;
}

function renderImportPreview(preview) {
  const rows = preview.rows;
  const keys = [...new Set(rows.flatMap((row) => Object.keys(row)
    .filter((key) => !["source_row", "status", "error"].includes(key))))];
  const header = ["LIGNE", ...keys.map((key) => key.replaceAll("_", " ").toUpperCase()), "ÉTAT"];
  const body = rows.map((row) => {
    const status = row.status === "ready" ? "Prête" : row.status === "duplicate" ? "Doublon ignoré" : "À corriger";
    return `<tr><td>${escapeHtml(row.source_row)}</td>${keys.map((key) =>
      `<td>${escapeHtml(row[key] ?? "—")}</td>`).join("")}<td><span class="import-status ${row.status}">${status}</span>${row.error ? `<small>${escapeHtml(row.error)}</small>` : ""}</td></tr>`;
  }).join("");
  $("#data-import-preview").innerHTML =
    `<p class="import-summary">${preview.ready_count} ligne(s) prête(s), ${preview.duplicate_count} doublon(s), ${preview.invalid_count} ligne(s) à corriger.</p><div class="table-wrap"><table><thead><tr>${header.map((label) => `<th>${escapeHtml(label)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
  $("#confirm-data-import").disabled = preview.invalid_count > 0 || preview.ready_count === 0;
}

$("#open-data-import").addEventListener("click", async () => {
  $("#data-import-preview").innerHTML = "";
  $("#confirm-data-import").disabled = true;
  $("#migration-file").value = "";
  dataImportFile = null;
  dataImportPreviewId = null;
  $("#migration-target").value = "product";
  $("#adjust-import-stock").checked = false;
  try {
    referenceFiles = await api("/import/references");
    updateReferenceOptions();
    $("#data-import-dialog").showModal();
  } catch (error) { notify(error.message); }
});
$("#migration-target").addEventListener("change", updateReferenceOptions);
$("#migration-file").addEventListener("change", () => {
  dataImportFile = $("#migration-file").files[0] || null;
  dataImportPreviewId = null;
  if (dataImportFile) $("#reference-file").value = "";
  $("#data-import-preview").innerHTML = "";
  $("#confirm-data-import").disabled = true;
});
$("#reference-file").addEventListener("change", () => {
  dataImportPreviewId = null;
  if ($("#reference-file").value) {
    $("#migration-file").value = "";
    dataImportFile = null;
  }
  $("#data-import-preview").innerHTML = "";
  $("#confirm-data-import").disabled = true;
});
$("#adjust-import-stock").addEventListener("change", () => {
  dataImportPreviewId = null;
  $("#data-import-preview").innerHTML = "";
  $("#confirm-data-import").disabled = true;
});
$("#preview-data-import").addEventListener("click", async () => {
  dataImportPreviewId = null;
  if (!dataImportFile && !$("#reference-file").value) {
    notify("Choisissez un classeur de référence ou un fichier à téléverser.");
    return;
  }
  try {
    const preview = await api("/import/preview", { method: "POST", body: migrationFormData() });
    dataImportPreviewId = preview.preview_id;
    renderImportPreview(preview);
  } catch (error) {
    $("#data-import-preview").innerHTML = `<p class="import-error">${escapeHtml(error.message)}</p>`;
    $("#confirm-data-import").disabled = true;
  }
});
$("#confirm-data-import").addEventListener("click", async () => {
  if (!dataImportPreviewId) return;
  const button = $("#confirm-data-import");
  button.disabled = true;
  try {
    const form = new FormData();
    form.append("preview_id", dataImportPreviewId);
    const result = await api("/import/confirm", { method: "POST", body: form });
    dataImportPreviewId = null;
    $("#data-import-dialog").close();
    await refresh();
    notify(`${result.created_count} ligne(s) ajoutée(s), ${result.duplicate_count} doublon(s) ignoré(s).`);
  } catch (error) {
    notify(error.message);
    dataImportPreviewId = null;
    button.disabled = true;
  }
});
$("#close-data-import").addEventListener("click", () => $("#data-import-dialog").close());

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
  $("#page-title").textContent = { dashboard: "Tableau de bord", stock: "Produits & stock", mouvements: "Entrées & sorties", commandes: "Commandes fournisseurs", imports: "Import & migration", veille: "Veille & alertes" }[view];
}));

document.querySelectorAll("[data-open-chat]").forEach((button) => button.addEventListener("click", () => $("#chat-dialog").showModal()));
$("#close-chat").addEventListener("click", () => $("#chat-dialog").close());

function showAgentProposal(proposal, box) {
  const labels = { product: "Produit", command: "Commande fournisseur", movement: "Mouvement de stock" };
  const endpoints = { product: "/products", command: "/commands", movement: "/movements" };
  const card = document.createElement("section");
  card.className = "agent-proposal";
  if (!endpoints[proposal.type]) {
    card.textContent = "Type de proposition inconnu; aucune action n’est disponible.";
    box.append(card);
    return;
  }
  const title = document.createElement("strong");
  title.textContent = `Proposition — ${labels[proposal.type] || "action inconnue"}`;
  const details = document.createElement("pre");
  details.textContent = JSON.stringify(proposal.data, null, 2);
  const confirm = document.createElement("button");
  confirm.className = "button button-secondary";
  confirm.type = "button";
  confirm.textContent = "Confirmer l’ajout";
  confirm.addEventListener("click", async () => {
    confirm.disabled = true;
    try {
      await api(endpoints[proposal.type], {
        method: "POST",
        body: JSON.stringify(proposal.data),
      });
      confirm.textContent = "Ajout confirmé";
    } catch (error) {
      confirm.disabled = false;
      const failure = document.createElement("p");
      failure.className = "proposal-error";
      failure.textContent = error.message;
      card.append(failure);
      return;
    }
    refresh().catch((error) => notify(`Ajout effectué, mais actualisation impossible : ${error.message}`));
  });
  card.append(title, details, confirm);
  box.append(card);
}

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
    const answer = await api("/chat", { method: "POST", body: JSON.stringify({ message }) });
    waiting.textContent = answer.reply;
    const sources = document.createElement("small");
    sources.className = "chat-sources";
    sources.textContent = answer.sharepoint_configured
      ? `Documents SharePoint consultés : ${answer.sharepoint_sources.join(", ")}`
      : "SharePoint n’est pas configuré sur le serveur.";
    box.append(sources);
    (answer.proposals || []).forEach((proposal) => showAgentProposal(proposal, box));
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
