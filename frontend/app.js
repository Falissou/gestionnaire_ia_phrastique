const state = {
  products: [],
  commands: [],
  movements: [],
  alerts: [],
  orderSuggestions: [],
  selectedSuggestionIds: new Set(),
};
const $ = (selector) => document.querySelector(selector);
const SUGGESTION_REFRESH_INTERVAL_MS = 5 * 60 * 60 * 1000;
const SUGGESTION_CACHE_KEY = "pharmastock-order-suggestions";
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));
let toastTimer;
let dataImportFile = null;
let dataImportPreviewId = null;
let referenceFiles = [];
let voiceCapture = null;

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

function currencyText(value) {
  return value === null || value === undefined || value === ""
    ? "—"
    : Number(value).toLocaleString("fr-FR");
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
  const filtered = state.products.filter((item) =>
    `${item.name} ${item.category} ${item.supplier || ""} ${item.comments || ""}`.toLocaleLowerCase("fr").includes(query));
  $("#product-total").textContent = `${filtered.length} produit(s)`;
  $("#products-table").innerHTML = filtered.length ? filtered.map((product) => {
    const [label, cls] = statusFor(product);
    return `<tr><td>${escapeHtml(product.product_code || "—")}</td><td><strong>${escapeHtml(product.name)}</strong></td><td>${escapeHtml(product.category)}</td><td>${escapeHtml(product.supplier || "—")}</td><td><strong>${product.quantity}</strong></td><td>${product.min_quantity}</td><td>${currencyText(product.unit_price)}</td><td>${dateText(product.entry_date)}</td><td>${dateText(product.expiry_date)}</td><td>${escapeHtml(product.source_status || "—")}</td><td>${escapeHtml(product.comments || "—")}</td><td><span class="stock-tag ${cls}">${label}</span></td></tr>`;
  }).join("") : '<tr><td colspan="12" class="empty-state">Aucun produit à afficher.</td></tr>';
}

function renderMovements() {
  const renderRegister = (type, target) => {
    const items = state.movements.filter((item) => item.type === type).slice().reverse();
    $(target).innerHTML = items.length
      ? items.map((item) => `<tr><td>${dateText(item.date)}</td><td><strong>${escapeHtml(item.product_name)}</strong></td><td>${item.quantity}</td><td>${escapeHtml(item.reason)}</td><td>${escapeHtml(item.reference || "—")}</td></tr>`).join("")
      : `<tr><td colspan="5" class="empty-state">Aucune ${type === "entree" ? "entrée" : "sortie"} enregistrée.</td></tr>`;
  };
  renderRegister("entree", "#entries-table");
  renderRegister("sortie", "#exits-table");
}

function renderCommands() {
  $("#commands-table").innerHTML = state.commands.length ? state.commands.map((item) => `<tr><td>${escapeHtml(item.source_order_number || item.id.slice(0, 8))}</td><td><strong>${escapeHtml(item.product_name)}</strong></td><td>${escapeHtml(item.product_code || "—")}</td><td>${item.quantity}</td><td>${escapeHtml(item.supplier)}</td><td>${currencyText(item.unit_price)}</td><td>${currencyText(item.total_amount)}</td><td>${dateText(item.order_date)}</td><td>${dateText(item.expected_date)}</td><td>${escapeHtml(item.responsible || "—")}</td><td>${escapeHtml(item.comments || "—")}</td><td><span class="stock-tag ${item.status === "Reçue" ? "ok" : "soon"}">${escapeHtml(item.status)}</span><select class="command-status" data-id="${escapeHtml(item.id)}"><option ${item.status === "En attente" ? "selected" : ""}>En attente</option><option ${item.status === "Commandée" ? "selected" : ""}>Commandée</option><option ${item.status === "Reçue" ? "selected" : ""}>Reçue</option><option ${item.status === "Annulée" ? "selected" : ""}>Annulée</option></select>${item.status === "En attente" ? `<button class="button button-secondary validate-command" data-id="${escapeHtml(item.id)}" type="button">Valider comme commandée</button>` : ""}</td></tr>`).join("") : '<tr><td colspan="12" class="empty-state">Aucune commande enregistrée.</td></tr>';
  document.querySelectorAll(".command-status").forEach((select) => select.addEventListener("change", async () => {
    try {
      await api(`/commands/${encodeURIComponent(select.dataset.id)}`, { method: "PATCH", body: JSON.stringify({ status: select.value }) });
      await refresh();
      notify("Statut de commande mis à jour.");
    } catch (error) { notify(error.message); }
  }));
  document.querySelectorAll(".validate-command").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await api(`/commands/${encodeURIComponent(button.dataset.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ status: "Commandée" }),
      });
      await refresh();
      notify("Commande validée comme déjà passée.");
    } catch (error) {
      button.disabled = false;
      notify(error.message);
    }
  }));
}

function renderOrderSuggestions() {
  const availableIds = new Set(state.orderSuggestions.map((item) => item.product_id));
  state.selectedSuggestionIds = new Set(
    [...state.selectedSuggestionIds].filter((id) => availableIds.has(id)),
  );
  $("#suggested-orders").innerHTML = state.orderSuggestions.length
    ? state.orderSuggestions.map((item) => `<tr><td><input class="suggestion-select" type="checkbox" aria-label="Sélectionner ${escapeHtml(item.product_name)}" data-id="${escapeHtml(item.product_id)}" ${state.selectedSuggestionIds.has(item.product_id) ? "checked" : ""}></td><td><strong>${escapeHtml(item.product_name)}</strong></td><td>${escapeHtml(item.supplier || "À renseigner")}</td><td>${item.current_quantity} / ${item.min_quantity}</td><td>${item.quantity}</td><td><span class="stock-tag ${item.priority === "critical" ? "low" : "soon"}">${item.priority === "critical" ? "Critique" : "À surveiller"}</span></td></tr>`).join("")
    : '<tr><td colspan="6" class="empty-state">Aucune suggestion de réapprovisionnement.</td></tr>';
  document.querySelectorAll(".suggestion-select").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedSuggestionIds.add(checkbox.dataset.id);
      else state.selectedSuggestionIds.delete(checkbox.dataset.id);
      updateSuggestionSelection();
    });
  });
  updateSuggestionSelection();
}

function updateSuggestionSelection() {
  const selected = state.orderSuggestions.filter((item) =>
    state.selectedSuggestionIds.has(item.product_id));
  const suppliers = new Set(selected.map((item) =>
    String(item.supplier || "").trim().toLocaleLowerCase("fr")));
  const sameSupplier = suppliers.size <= 1;
  $("#selected-suggestion-count").textContent = selected.length
    ? `${selected.length} suggestion(s) sélectionnée(s).`
    : "Aucune suggestion sélectionnée.";
  $("#suggestion-selection-help").textContent = sameSupplier
    ? ""
    : "Un bon de commande concerne un seul fournisseur. Sélectionnez les articles d'un même fournisseur.";
  $("#place-order").disabled = selected.length === 0 || !sameSupplier;
}

function openPurchaseOrder() {
  const selected = state.orderSuggestions.filter((item) =>
    state.selectedSuggestionIds.has(item.product_id));
  if (!selected.length) return;
  const supplierNames = new Set(selected.map((item) => String(item.supplier || "").trim()));
  if (supplierNames.size !== 1) {
    notify("Sélectionnez les suggestions d'un même fournisseur.");
    return;
  }
  $("#purchase-order-supplier").value = [...supplierNames][0];
  $("#purchase-order-date").value = "";
  $("#purchase-order-responsible").value = "";
  $("#purchase-order-comments").value = "";
  $("#purchase-order-error").textContent = "";
  $("#purchase-order-lines").innerHTML = selected.map((item) => `
    <tr data-id="${escapeHtml(item.product_id)}">
      <td>${escapeHtml(item.product_code || "—")}</td>
      <td><strong>${escapeHtml(item.product_name)}</strong></td>
      <td>${item.current_quantity} / ${item.min_quantity}</td>
      <td><input class="po-quantity" type="number" min="1" step="1" required value="${item.quantity}" aria-label="Quantité ${escapeHtml(item.product_name)}"></td>
      <td><input class="po-unit-price" type="number" min="0" step="0.01" required value="${Number(item.unit_price || 0)}" aria-label="Prix unitaire ${escapeHtml(item.product_name)}"></td>
      <td class="po-line-total">0 FCFA</td>
      <td><button class="icon-button remove-order-line" type="button" aria-label="Retirer ${escapeHtml(item.product_name)}">×</button></td>
    </tr>`).join("");
  $("#purchase-order-dialog").showModal();
  updatePurchaseOrderTotal();
}

function updatePurchaseOrderTotal() {
  let total = 0;
  document.querySelectorAll("#purchase-order-lines tr").forEach((row) => {
    const quantity = Number(row.querySelector(".po-quantity").value) || 0;
    const price = Number(row.querySelector(".po-unit-price").value) || 0;
    const lineTotal = quantity * price;
    total += lineTotal;
    row.querySelector(".po-line-total").textContent = `${currencyText(lineTotal)} FCFA`;
  });
  $("#purchase-order-total").textContent = `${currencyText(total)} FCFA`;
}

async function refreshOrderSuggestions(force = false) {
  if (!force) {
    const cached = localStorage.getItem(SUGGESTION_CACHE_KEY);
    if (cached) {
      try {
        const saved = JSON.parse(cached);
        if (
          Array.isArray(saved.orders)
          && Number.isFinite(saved.updatedAt)
          && Date.now() - saved.updatedAt < SUGGESTION_REFRESH_INTERVAL_MS
        ) {
          state.orderSuggestions = saved.orders;
          renderOrderSuggestions();
          return;
        }
      } catch {
        localStorage.removeItem(SUGGESTION_CACHE_KEY);
      }
    }
  }
  const recommendations = await api("/recommendations");
  state.orderSuggestions = recommendations.orders || [];
  localStorage.setItem(SUGGESTION_CACHE_KEY, JSON.stringify({
    orders: state.orderSuggestions,
    updatedAt: Date.now(),
  }));
  renderOrderSuggestions();
}

function renderAlerts() {
  $("#all-alerts").innerHTML = state.alerts.length ? state.alerts.map((item) => `<article class="alert-card ${escapeHtml(item.severity)}"><strong>${escapeHtml(item.product)}</strong><p>${escapeHtml(item.message)}</p></article>`).join("") : '<div class="panel empty-state">Aucune alerte de stock ou d’expiration.</div>';
}

async function refresh() {
  const suggestionsRefresh = refreshOrderSuggestions();
  const [dashboard, products, commands, movements, alerts] = await Promise.all([
    api("/dashboard"), api("/products"), api("/commands"), api("/movements"), api("/alerts"),
  ]);
  await suggestionsRefresh;
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

document.querySelectorAll("#form-dialog [data-dialog-close]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#form-dialog").close();
    $("#data-form").reset();
  });
});

$("#add-product").addEventListener("click", () => openForm("Ajouter un produit", [
  field("product_code", "Code produit", "text", { required: false }),
  field("name", "Nom du produit", "text", { full: true }),
  field("category", "Catégorie", "text", { value: "Médicament" }),
  field("quantity", "Quantité", "number", { min: 0 }),
  field("min_quantity", "Seuil minimum", "number", { min: 0, value: "5" }),
  field("unit_price", "Prix unitaire (FCFA)", "number", { min: 0, step: "0.01", value: "0" }),
  field("expiry_date", "Date d'expiration", "date", { required: false }),
  field("supplier", "Fournisseur", "text", { required: false }),
  field("entry_date", "Date d'entrée", "date", { required: false }),
  field("source_status", "Statut source", "text", { required: false }),
  field("comments", "Commentaires", "text", { full: true, required: false }),
], (data) => api("/products", {
  method: "POST",
  body: JSON.stringify({
    ...data,
    product_code: data.product_code || null,
    quantity: Number(data.quantity),
    min_quantity: Number(data.min_quantity),
    unit_price: Number(data.unit_price),
    expiry_date: data.expiry_date || null,
    entry_date: data.entry_date || null,
  }),
})));

$("#add-command").addEventListener("click", () => openForm("Nouvelle commande", [
  field("source_order_number", "N° de commande", "text", { required: false }),
  field("product_name", "Produit", "text", { full: true }),
  field("quantity", "Quantité", "number", { min: 1 }),
  field("supplier", "Fournisseur", "text"),
  field("product_code", "Code produit", "text", { required: false }),
  field("unit_price", "Prix unitaire (FCFA)", "number", { min: 0, step: "0.01", required: false }),
  field("total_amount", "Montant total (FCFA)", "number", { min: 0, step: "0.01", required: false }),
  field("expected_date", "Date de livraison prévue", "date", { required: false }),
  field("responsible", "Responsable", "text", { required: false }),
  field("comments", "Commentaires", "text", { full: true, required: false }),
], submitCommandForm));

function submitCommandForm(data) {
  return api("/commands", {
    method: "POST",
    body: JSON.stringify({
      ...data,
      quantity: Number(data.quantity),
      source_order_number: data.source_order_number || null,
      product_code: data.product_code || null,
      unit_price: data.unit_price ? Number(data.unit_price) : null,
      total_amount: data.total_amount ? Number(data.total_amount) : null,
      expected_date: data.expected_date || null,
    }),
  });
}

$("#place-order").addEventListener("click", openPurchaseOrder);
$("#close-purchase-order").addEventListener("click", () => $("#purchase-order-dialog").close());
$("#cancel-purchase-order").addEventListener("click", () => $("#purchase-order-dialog").close());
$("#purchase-order-lines").addEventListener("input", updatePurchaseOrderTotal);
$("#purchase-order-lines").addEventListener("click", (event) => {
  const button = event.target.closest(".remove-order-line");
  if (!button) return;
  const row = button.closest("tr");
  state.selectedSuggestionIds.delete(row.dataset.id);
  row.remove();
  updatePurchaseOrderTotal();
  updateSuggestionSelection();
  $("#confirm-purchase-order").disabled = !$("#purchase-order-lines tr").length;
});
$("#purchase-order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#confirm-purchase-order");
  const lines = [...document.querySelectorAll("#purchase-order-lines tr")].map((row) => ({
    product_id: row.dataset.id,
    quantity: Number(row.querySelector(".po-quantity").value),
    unit_price: Number(row.querySelector(".po-unit-price").value),
  }));
  if (!lines.length) {
    $("#purchase-order-error").textContent = "Ajoutez au moins un produit au bon de commande.";
    return;
  }
  button.disabled = true;
  $("#purchase-order-error").textContent = "";
  try {
    const token = localStorage.getItem("pharmastock-token");
    const headers = {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const response = await fetch("/api/commands/place-order", {
      method: "POST",
      headers,
      body: JSON.stringify({
        supplier: $("#purchase-order-supplier").value.trim(),
        expected_date: $("#purchase-order-date").value || null,
        responsible: $("#purchase-order-responsible").value.trim() || null,
        comments: $("#purchase-order-comments").value.trim() || null,
        lines,
      }),
    });
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      throw new Error(result.detail || `Erreur API (${response.status})`);
    }
    const filename = response.headers.get("Content-Disposition")
      ?.match(/filename="?([^";]+)"?/i)?.[1] || "bon_commande.xlsx";
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    $("#purchase-order-dialog").close();
    state.selectedSuggestionIds.clear();
    localStorage.removeItem(SUGGESTION_CACHE_KEY);
    try {
      await refresh();
      notify("Commande enregistrée et bon Excel téléchargé.");
    } catch (error) {
      notify(`Commande enregistrée et bon téléchargé, mais actualisation impossible : ${error.message}`);
    }
  } catch (error) {
    $("#purchase-order-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

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

function openMovementForm(type) {
  const entering = type === "entree";
  const productChoices = state.products.map((item) => [
    item.id,
    `${item.name} (${item.quantity} en stock)`,
  ]);
  if (entering) productChoices.push(["__new__", "＋ Créer un nouveau produit"]);
  const newProductFields = entering
    ? `<div class="form-grid new-product-fields" data-new-product-fields hidden>
        ${field("product_name", "Nom du nouveau produit", "text", { full: true, required: false })}
        ${field("product_code", "Code produit (facultatif)", "text", { required: false })}
        ${field("category", "Catégorie", "text", { value: "Médicament" })}
        ${field("min_quantity", "Seuil minimum", "number", { min: 0, value: "5" })}
        ${field("unit_price", "Prix unitaire (FCFA)", "number", { min: 0, step: "0.01", value: "0" })}
        ${field("expiry_date", "Date d'expiration", "date", { required: false })}
        ${field("supplier", "Fournisseur", "text", { required: false })}
        ${field("entry_date", "Date d'entrée", "date", { required: false })}
        ${field("source_status", "Statut source", "text", { required: false })}
        ${field("comments", "Commentaires", "text", { full: true, required: false })}
      </div>`
    : "";
  openForm(entering ? "Enregistrer une entrée" : "Enregistrer une sortie", [
    field("product_id", entering ? "Produit existant ou nouveau" : "Produit", "text", {
      choices: productChoices,
      full: true,
    }),
    newProductFields,
    field("quantity", "Quantité", "number", { min: 1 }),
    field("reason", "Motif", "text", { full: true }),
    field("reference", "Référence (facultatif)", "text", { required: false }),
  ], (data) => {
    const isNewProduct = entering && data.product_id === "__new__";
    const payload = {
      product_id: isNewProduct ? null : data.product_id,
      type,
      quantity: Number(data.quantity),
      reason: data.reason,
      reference: data.reference || null,
    };
    if (isNewProduct) {
      Object.assign(payload, {
        product_name: data.product_name,
        product_code: data.product_code || null,
        category: data.category,
        min_quantity: Number(data.min_quantity),
        unit_price: Number(data.unit_price),
        expiry_date: data.expiry_date || null,
        supplier: data.supplier || null,
        entry_date: data.entry_date || null,
        source_status: data.source_status || null,
        comments: data.comments || null,
      });
    }
    return api("/movements", { method: "POST", body: JSON.stringify(payload) });
  });
  if (entering) {
    const selection = $("#data-form [name=product_id]");
    const details = $("#data-form [data-new-product-fields]");
    const name = $("#data-form [name=product_name]");
    const syncNewProductFields = () => {
      const isNewProduct = selection.value === "__new__";
      details.hidden = !isNewProduct;
      name.required = isNewProduct;
    };
    selection.addEventListener("change", syncNewProductFields);
    syncNewProductFields();
  }
}

$("#add-entry").addEventListener("click", () => openMovementForm("entree"));
$("#add-exit").addEventListener("click", () => openMovementForm("sortie"));

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

function createVoiceWav(frames, sourceRate) {
  const frameCount = frames.reduce((total, frame) => total + frame.length, 0);
  const source = new Float32Array(frameCount);
  let offset = 0;
  frames.forEach((frame) => {
    source.set(frame, offset);
    offset += frame.length;
  });
  const sampleRate = 24000;
  const outputCount = Math.floor(source.length * sampleRate / sourceRate);
  if (!outputCount) throw new Error("Aucun son n’a été capté.");
  const buffer = new ArrayBuffer(44 + outputCount * 2);
  const view = new DataView(buffer);
  const writeText = (position, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(position + index, text.charCodeAt(index));
    }
  };
  writeText(0, "RIFF");
  view.setUint32(4, 36 + outputCount * 2, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, outputCount * 2, true);
  const ratio = sourceRate / sampleRate;
  for (let index = 0; index < outputCount; index += 1) {
    const position = index * ratio;
    const start = Math.floor(position);
    const fraction = position - start;
    const first = source[start] || 0;
    const second = source[Math.min(start + 1, source.length - 1)] || 0;
    const sample = Math.max(-1, Math.min(1, first + (second - first) * fraction));
    view.setInt16(44 + index * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

function appendVoiceReplyAudio(box, audioBase64) {
  if (!audioBase64) return;
  const player = document.createElement("audio");
  player.controls = true;
  player.preload = "none";
  player.src = `data:audio/wav;base64,${audioBase64}`;
  box.append(player);
}

async function sendVoiceMessage(frames, sourceRate) {
  const box = $("#chat-messages");
  const userMessage = document.createElement("div");
  userMessage.className = "chat-bubble user";
  userMessage.textContent = "Message vocal en cours d’envoi…";
  box.append(userMessage);
  const waiting = document.createElement("div");
  waiting.className = "chat-bubble assistant";
  waiting.textContent = "GestionAgent écoute votre message…";
  box.append(waiting);
  box.scrollTop = box.scrollHeight;
  try {
    const form = new FormData();
    form.append("file", createVoiceWav(frames, sourceRate), "message-vocal.wav");
    const answer = await api("/chat/voice", { method: "POST", body: form });
    userMessage.textContent = answer.input_transcript || "Message vocal";
    waiting.textContent = answer.reply || "GestionAgent n’a pas fourni de réponse transcrite.";
    appendVoiceReplyAudio(waiting, answer.audio_reply);
    (answer.proposals || []).forEach((proposal) => showAgentProposal(proposal, waiting));
  } catch (error) {
    userMessage.textContent = "Message vocal";
    waiting.textContent = error.message;
  }
  box.scrollTop = box.scrollHeight;
}

async function startVoiceCapture() {
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    throw new Error("L’enregistrement vocal nécessite un navigateur compatible et un accès HTTPS.");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  const frames = [];
  processor.onaudioprocess = (event) => {
    frames.push(new Float32Array(event.inputBuffer.getChannelData(0)));
    event.outputBuffer.getChannelData(0).fill(0);
  };
  source.connect(processor);
  processor.connect(context.destination);
  voiceCapture = { stream, context, source, processor, frames, sourceRate: context.sampleRate };
  $("#record-voice").textContent = "Terminer et envoyer";
  $("#record-voice").setAttribute("aria-pressed", "true");
  $("#voice-status").textContent = "Enregistrement… (60 secondes maximum)";
  voiceCapture.timeout = window.setTimeout(stopVoiceCapture, 60_000);
}

async function stopVoiceCapture() {
  if (!voiceCapture) return;
  const capture = voiceCapture;
  voiceCapture = null;
  window.clearTimeout(capture.timeout);
  capture.processor.disconnect();
  capture.source.disconnect();
  capture.stream.getTracks().forEach((track) => track.stop());
  await capture.context.close();
  $("#record-voice").textContent = "🎙 Message vocal";
  $("#record-voice").setAttribute("aria-pressed", "false");
  $("#voice-status").textContent = "Envoi du message vocal à GestionAgent…";
  try {
    await sendVoiceMessage(capture.frames, capture.sourceRate);
  } finally {
    $("#voice-status").textContent = "";
  }
}

$("#record-voice").addEventListener("click", async () => {
  const button = $("#record-voice");
  button.disabled = true;
  try {
    if (voiceCapture) await stopVoiceCapture();
    else await startVoiceCapture();
  } catch (error) {
    notify(error.message);
    $("#voice-status").textContent = "";
  } finally {
    button.disabled = false;
  }
});

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
    appendVoiceReplyAudio(waiting, answer.audio_reply);
    const reports = answer.agent_reports || [];
    if (reports.length) {
      const details = document.createElement("details");
      details.className = "agent-reports";
      const summary = document.createElement("summary");
      summary.textContent = `Comptes rendus des ${reports.length} agents spécialisés`;
      details.append(summary);
      reports.forEach((report) => {
        const section = document.createElement("section");
        const heading = document.createElement("strong");
        heading.textContent = report.agent;
        const content = document.createElement("p");
        content.textContent = report.reply;
        section.append(heading, content);
        if (report.sharepoint_sources?.length) {
          const documentSources = document.createElement("small");
          documentSources.className = "chat-sources";
          documentSources.textContent = `Documents de référence : ${report.sharepoint_sources.join(", ")}`;
          section.append(documentSources);
        }
        (report.web_sources || []).forEach((source) => {
          if (!/^https?:\/\//i.test(source.url || "")) return;
          const link = document.createElement("a");
          link.href = source.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.textContent = source.title || source.url;
          section.append(link);
        });
        details.append(section);
      });
      box.append(details);
    }
    const sources = document.createElement("small");
    sources.className = "chat-sources";
    if (answer.sharepoint_sources.length) {
      sources.textContent = `Documents SharePoint consultés : ${answer.sharepoint_sources.join(", ")}`;
      box.append(sources);
    } else if (answer.sharepoint_configured) {
      sources.textContent = "Aucun document SharePoint consulté pour cette question.";
      box.append(sources);
    }
    const webSources = answer.web_sources || [];
    if (webSources.length) {
      const sourceList = document.createElement("small");
      sourceList.className = "chat-sources";
      sourceList.textContent = "Sources web : ";
      webSources.forEach((source, index) => {
        if (!/^https?:\/\//i.test(source.url || "")) return;
        if (index) sourceList.append(document.createTextNode(", "));
        const link = document.createElement("a");
        link.href = source.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = source.title || source.url;
        sourceList.append(link);
      });
      box.append(sourceList);
    }
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
window.setInterval(() => {
  refresh().catch((error) => notify(`Actualisation impossible : ${error.message}`));
}, 60_000);
window.setInterval(() => {
  refreshOrderSuggestions(true).catch((error) => notify(`Actualisation des suggestions impossible : ${error.message}`));
}, SUGGESTION_REFRESH_INTERVAL_MS);
