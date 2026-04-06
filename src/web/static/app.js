/**
 * Creative Automation Pipeline — Frontend Application
 *
 * Handles brief validation, creative generation, job polling,
 * versioned results display, download, delete, and regeneration.
 */

const API = {
    validate: "/api/validate",
    generate: "/api/generate",
    jobs: "/api/jobs",
};

const POLL_INTERVAL_MS = 2000;

let currentJobId = null;
let currentVersion = null;

// ── DOM References ────────────────────────────────────────────────────

let validatedProducts = [];  // Product list from validated brief

const elements = {
    generateForm: document.getElementById("generate-form"),
    briefFile: document.getElementById("brief-file"),
    productAssetsSection: document.getElementById("product-assets-section"),
    productAssetFields: document.getElementById("product-asset-fields"),
    generateSection: document.getElementById("generate-section"),
    validateBtn: document.getElementById("validate-btn"),
    skipGenai: document.getElementById("skip-genai"),
    generateBtn: document.getElementById("generate-btn"),
    statusArea: document.getElementById("status-area"),
    resultsCard: document.getElementById("results-card"),
    summaryBody: document.getElementById("summary-body"),
    resultsGrid: document.getElementById("results-grid"),
    sampleBrief: document.getElementById("sample-brief"),
    downloadBtn: document.getElementById("download-btn"),
    regenerateBtn: document.getElementById("regenerate-btn"),
    deleteBtn: document.getElementById("delete-btn"),
    versionSelect: document.getElementById("version-select"),
    versionBar: document.getElementById("version-bar"),
};

// ── Sample Brief Toggle ───────────────────────────────────────────────

function toggleSampleBrief() {
    const el = elements.sampleBrief;
    const bsCollapse = new bootstrap.Collapse(el, { toggle: true });
}

// ── Status Rendering ──────────────────────────────────────────────────

function showStatus(html) {
    elements.statusArea.innerHTML = html;
}

function showError(message) {
    showStatus(
        `<div class="alert alert-danger mt-3" role="alert">
            <strong>Error:</strong> ${escapeHtml(message)}
        </div>`
    );
}

function showSuccess(html) {
    showStatus(`<div class="alert alert-success mt-3">${html}</div>`);
}

function showSpinner(message) {
    showStatus(
        `<div class="mt-3">
            <span class="cap-spinner"></span>
            <span class="status-running">${escapeHtml(message)}</span>
        </div>`
    );
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ── Validate Brief & Show Product Upload Fields ──────────────────────

async function validateAndShowProducts() {
    if (!elements.briefFile.files.length) {
        showError("Please select a campaign brief file.");
        return;
    }

    const formData = new FormData();
    formData.append("brief_file", elements.briefFile.files[0]);

    showSpinner("Validating brief...");

    try {
        const resp = await fetch(API.validate, { method: "POST", body: formData });
        const data = await resp.json();

        if (!data.valid) {
            showError(data.error);
            elements.productAssetsSection.classList.add("d-none");
            elements.generateSection.classList.add("d-none");
            return;
        }

        validatedProducts = data.products;

        showSuccess(`
            <strong>Brief is valid!</strong> ${escapeHtml(data.campaign_name)} —
            ${data.products.length} products, ${data.total_creatives} creatives to generate.
        `);

        // Build per-product upload fields
        elements.productAssetFields.innerHTML = "";
        for (const product of data.products) {
            const slug = product.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
            const fieldHtml = `
                <div class="input-group mb-2">
                    <span class="input-group-text" style="min-width: 140px;">
                        <i class="bi bi-image me-1"></i>${escapeHtml(product)}
                    </span>
                    <input type="file" class="form-control product-asset-input"
                           data-product-slug="${slug}"
                           data-product-name="${escapeHtml(product)}"
                           accept="image/*">
                    <span class="input-group-text text-muted small">optional</span>
                </div>
            `;
            elements.productAssetFields.innerHTML += fieldHtml;
        }

        elements.productAssetsSection.classList.remove("d-none");
        elements.generateSection.classList.remove("d-none");

    } catch (err) {
        showError(`Validation failed: ${err.message}`);
    }
}

// ── Generate Creatives ────────────────────────────────────────────────

async function handleGenerate(event) {
    event.preventDefault();

    if (!elements.briefFile.files.length) {
        showError("Please select a campaign brief file.");
        return;
    }

    if (validatedProducts.length === 0) {
        showError("Please validate the brief first.");
        return;
    }

    const formData = new FormData();
    formData.append("brief_file", elements.briefFile.files[0]);

    // Collect per-product asset files
    const productInputs = document.querySelectorAll(".product-asset-input");
    for (const input of productInputs) {
        if (input.files && input.files.length > 0) {
            const slug = input.getAttribute("data-product-slug");
            formData.append(`product_asset_${slug}`, input.files[0]);
        }
    }

    formData.append("skip_genai", elements.skipGenai.checked ? "true" : "false");

    setGenerating(true);
    showSpinner("Starting pipeline...");
    hideResults();

    try {
        const resp = await fetch(API.generate, { method: "POST", body: formData });

        if (!resp.ok) {
            const err = await resp.json();
            showError(err.detail || "Generation failed");
            setGenerating(false);
            return;
        }

        const data = await resp.json();
        currentJobId = data.job_id;
        showSpinner(`Job ${data.job_id} running — generating creatives and post messages...`);
        pollJob(data.job_id);
    } catch (err) {
        showError(`Request failed: ${err.message}`);
        setGenerating(false);
    }
}

// ── Regenerate ────────────────────────────────────────────────────────

async function handleRegenerate() {
    if (!currentJobId) {
        // Campaign loaded from browser — no active job.
        // User needs to upload the brief again to regenerate.
        showError("To regenerate, please upload the campaign brief and generate first. " +
                  "Regeneration requires the original brief which is only available during an active session.");
        return;
    }

    setGenerating(true);
    showSpinner("Regenerating as new version with fresh AI content...");

    try {
        const resp = await fetch(`${API.jobs}/${currentJobId}/regenerate`, { method: "POST" });
        if (!resp.ok) {
            const err = await resp.json();
            showError(err.detail || "Regeneration failed");
            setGenerating(false);
            return;
        }

        const data = await resp.json();
        currentJobId = data.job_id;
        showSpinner(`Regeneration job ${data.job_id} running (new version)...`);
        pollJob(data.job_id);
    } catch (err) {
        showError(`Regeneration failed: ${err.message}`);
        setGenerating(false);
    }
}

// ── Download ──────────────────────────────────────────────────────────

function handleDownload() {
    if (!currentVersion) return;
    // Use campaign-based endpoint if we have a slug, otherwise job-based
    if (currentCampaignSlug) {
        window.location.href = `/api/campaigns/${currentCampaignSlug}/versions/${currentVersion}/download`;
    } else if (currentJobId) {
        window.location.href = `${API.jobs}/${currentJobId}/versions/${currentVersion}/download`;
    }
}

// ── Delete Version ────────────────────────────────────────────────────

async function handleDelete() {
    if (!currentVersion) return;

    if (!confirm(`Delete version v${currentVersion}? This cannot be undone.`)) return;

    try {
        // Use campaign-based endpoint if available, otherwise job-based
        let url;
        if (currentCampaignSlug) {
            url = `/api/campaigns/${currentCampaignSlug}/versions/${currentVersion}`;
        } else if (currentJobId) {
            url = `${API.jobs}/${currentJobId}/versions/${currentVersion}`;
        } else {
            return;
        }

        const resp = await fetch(url, { method: "DELETE" });
        if (resp.ok) {
            showStatus(`<div class="alert alert-info mt-3">Version v${currentVersion} deleted.</div>`);
            hideResults();
            loadCampaigns();
            if (currentCampaignSlug) {
                await loadCampaignVersions(currentCampaignSlug);
            }
        } else {
            const err = await resp.json();
            showError(err.detail || "Delete failed");
        }
    } catch (err) {
        showError(`Delete failed: ${err.message}`);
    }
}

// ── Version Switching ─────────────────────────────────────────────────

async function loadVersions(jobId) {
    try {
        const resp = await fetch(`${API.jobs}/${jobId}/versions`);
        const data = await resp.json();
        const versions = data.versions || [];

        if (versions.length === 0) {
            hideResults();
            return;
        }

        // Populate dropdown
        elements.versionSelect.innerHTML = "";
        for (const v of versions) {
            const opt = document.createElement("option");
            opt.value = v.version;
            opt.textContent = `Version ${v.version}`;
            elements.versionSelect.appendChild(opt);
        }

        // Select the latest
        const latest = versions[versions.length - 1].version;
        elements.versionSelect.value = latest;
        currentVersion = latest;

        elements.versionBar.classList.remove("d-none");
    } catch (_err) {
        // Versions not available yet
    }
}

async function handleVersionChange() {
    const val = elements.versionSelect.value;

    // Value may be "slug:version" (campaign-based) or plain "version" (job-based)
    if (val.includes(":")) {
        const [slug, vStr] = val.split(":");
        const version = parseInt(vStr, 10);
        if (version) {
            await loadCampaignVersion(slug, version);
        }
        return;
    }

    const selectedVersion = parseInt(val, 10);
    if (!selectedVersion) return;
    currentVersion = selectedVersion;

    try {
        // Try campaign-based load first
        if (currentCampaignSlug) {
            await loadCampaignVersion(currentCampaignSlug, selectedVersion);
            return;
        }
        // Fall back to job-based
        const job = _findJobWithVersion(selectedVersion);
        if (job) {
            displayResults(job);
        } else {
            await loadVersionFromDisk(selectedVersion);
        }
    } catch (_err) {
        showError("Could not load version data");
    }
}

function _findJobWithVersion(version) {
    // Search all jobs for one with matching version
    for (const [, job] of Object.entries(_jobResults)) {
        if (job && job.version === version) return job;
    }
    return null;
}

// Store results by version for switching
const _jobResults = {};

async function loadVersionFromDisk(version) {
    // Try loading report.json from the version directory via the output static mount
    try {
        const jobResp = await fetch(`${API.jobs}/${currentJobId}`);
        const jobData = await jobResp.json();
        if (jobData.result && jobData.result.campaign_name) {
            const slug = jobData.result.campaign_name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
            const reportResp = await fetch(`/output/${slug}/v${version}/report.json`);
            if (reportResp.ok) {
                const report = await reportResp.json();
                // Convert report to display format
                const displayResult = {
                    campaign_name: report.campaign_name,
                    version: report.version || version,
                    total_generated: report.total_assets_generated,
                    total_reused: report.total_assets_reused,
                    total_placeholders: report.total_assets_placeholder,
                    total_time_seconds: report.total_time_seconds,
                    products: report.products.map(pr => ({
                        name: pr.product_name,
                        assets: pr.assets.map(a => {
                            let rel = a.output_path;
                            if (rel.startsWith("data/output/")) rel = rel.substring("data/output/".length);
                            const asset = {
                                ratio: a.aspect_ratio,
                                language: a.language,
                                source: a.source,
                                url: `/output/${rel}`,
                            };
                            if (a.post_message) {
                                asset.post_message = {
                                    text: a.post_message.text,
                                    hashtags: a.post_message.hashtags,
                                    platform: a.post_message.platform_hint,
                                };
                            }
                            return asset;
                        }),
                        errors: pr.errors,
                    })),
                };
                displayResults(displayResult);
            }
        }
    } catch (_err) {
        // Silently fail — version data not accessible
    }
}

// ── Job Polling ───────────────────────────────────────────────────────

function pollJob(jobId) {
    const interval = setInterval(async () => {
        try {
            const resp = await fetch(`${API.jobs}/${jobId}`);
            const job = await resp.json();

            if (job.status === "complete") {
                clearInterval(interval);
                showStatus(
                    `<div class="mt-3 status-complete">
                        <strong>Generation complete!</strong> Creatives and post messages are ready.
                    </div>`
                );
                currentVersion = job.result.version;
                _jobResults[job.result.version] = job.result;
                // Extract campaign slug from result for campaign-based operations
                if (job.result.campaign_name) {
                    currentCampaignSlug = job.result.campaign_name
                        .toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");
                }
                displayResults(job.result);
                await loadVersions(jobId);
                loadCampaigns();  // Refresh campaign browser
                setGenerating(false);
            } else if (job.status === "failed") {
                clearInterval(interval);
                showError(`Pipeline failed: ${job.error}`);
                setGenerating(false);
            }
        } catch (_err) {
            // Network error — keep polling
        }
    }, POLL_INTERVAL_MS);
}

// ── Results Display ───────────────────────────────────────────────────

function hideResults() {
    elements.resultsCard.classList.add("d-none");
    elements.resultsGrid.innerHTML = "";
}

function displayResults(result) {
    elements.resultsCard.classList.remove("d-none");
    elements.downloadBtn.classList.remove("d-none");
    elements.regenerateBtn.classList.remove("d-none");
    elements.deleteBtn.classList.remove("d-none");

    const versionLabel = result.version ? ` (v${result.version})` : "";

    // Summary table
    elements.summaryBody.innerHTML = `
        <tr><td>Campaign</td><td>${escapeHtml(result.campaign_name)}${versionLabel}</td></tr>
        <tr><td>AI Generated</td><td>${result.total_generated}</td></tr>
        <tr><td>Reused (existing)</td><td>${result.total_reused}</td></tr>
        <tr><td>Placeholders</td><td>${result.total_placeholders}</td></tr>
        <tr><td>Total Time</td><td>${result.total_time_seconds}s</td></tr>
    `;

    // Creative preview cards
    elements.resultsGrid.innerHTML = "";

    for (const product of result.products) {
        for (const asset of product.assets) {
            const postMsg = asset.post_message;
            const card = document.createElement("div");
            card.className = "col";
            card.innerHTML = `
                <div class="card result-card h-100">
                    <a href="${asset.url}" target="_blank">
                        <img src="${asset.url}" class="card-img-top"
                             alt="${escapeHtml(product.name)} ${asset.ratio} ${asset.language}"
                             loading="lazy">
                    </a>
                    <div class="card-body">
                        <div class="product-name">${escapeHtml(product.name)}</div>
                        <div class="meta mb-2">${asset.ratio} / ${asset.language} — ${asset.source}</div>
                        ${postMsg ? renderPostMessage(postMsg) : ""}
                    </div>
                </div>
            `;
            elements.resultsGrid.appendChild(card);
        }
    }
}

function platformIcons(platformStr) {
    const p = (platformStr || "").toLowerCase();
    const icons = [];
    if (p.includes("instagram"))  icons.push('<i class="bi bi-instagram" title="Instagram"></i>');
    if (p.includes("facebook"))   icons.push('<i class="bi bi-facebook" title="Facebook"></i>');
    if (p.includes("tiktok"))     icons.push('<i class="bi bi-tiktok" title="TikTok"></i>');
    if (p.includes("youtube"))    icons.push('<i class="bi bi-youtube" title="YouTube"></i>');
    if (p.includes("linkedin"))   icons.push('<i class="bi bi-linkedin" title="LinkedIn"></i>');
    if (p.includes("reels"))      icons.push('<i class="bi bi-play-circle" title="Reels"></i>');
    if (p.includes("stories"))    icons.push('<i class="bi bi-phone" title="Stories"></i>');
    return icons.length ? icons.join(" ") : `<i class="bi bi-globe"></i>`;
}

function renderPostMessage(msg) {
    const hashtags = msg.hashtags && msg.hashtags.length
        ? `<div class="post-hashtags">${msg.hashtags.map(escapeHtml).join(" ")}</div>`
        : "";
    return `
        <div class="post-message-preview">
            <div class="post-label">
                <i class="bi bi-chat-square-text"></i> Post Message
                <span class="platform-icons">${platformIcons(msg.platform)}</span>
            </div>
            <div class="post-text">${escapeHtml(msg.text)}</div>
            ${hashtags}
        </div>
    `;
}

// ── Campaign Browser ──────────────────────────────────────────────────

async function loadCampaigns() {
    const body = document.getElementById("campaigns-body");
    body.innerHTML = '<span class="cap-spinner"></span> Loading campaigns...';

    try {
        const resp = await fetch("/api/campaigns");
        const data = await resp.json();
        const campaigns = data.campaigns || [];

        if (campaigns.length === 0) {
            body.innerHTML = '<p class="text-muted small mb-0">No campaigns yet. Upload a brief to get started.</p>';
            return;
        }

        let html = '<div class="list-group list-group-flush">';
        for (const c of campaigns) {
            html += `
                <div class="list-group-item d-flex justify-content-between align-items-center px-0">
                    <div>
                        <strong>${escapeHtml(c.name)}</strong>
                        <span class="text-muted small ms-2">${c.versions} version(s)</span>
                    </div>
                    <div class="d-flex gap-1">
                        ${c.version_list.map(v => `
                            <button class="btn btn-sm btn-outline-secondary"
                                    onclick="loadCampaignVersion('${escapeHtml(c.slug)}', ${v.version})">
                                v${v.version}
                            </button>
                        `).join("")}
                    </div>
                </div>
            `;
        }
        html += "</div>";
        body.innerHTML = html;

    } catch (err) {
        body.innerHTML = `<p class="text-danger small">Failed to load campaigns: ${escapeHtml(err.message)}</p>`;
    }
}

async function loadCampaignVersion(slug, version) {
    showSpinner(`Loading ${slug} v${version}...`);

    try {
        const resp = await fetch(`/api/campaigns/${slug}/versions/${version}`);
        if (!resp.ok) {
            const err = await resp.json();
            showError(err.detail || "Failed to load version");
            return;
        }

        const data = await resp.json();
        currentVersion = version;
        // Store slug for download/delete operations
        currentCampaignSlug = slug;
        displayResults(data.result);

        showStatus(
            `<div class="mt-3 status-complete">
                Viewing <strong>${escapeHtml(data.result.campaign_name)}</strong> — version ${version}
            </div>`
        );

        // Load version list for this campaign
        await loadCampaignVersions(slug);
    } catch (err) {
        showError(`Failed to load version: ${err.message}`);
    }
}

async function loadCampaignVersions(slug) {
    try {
        const resp = await fetch(`/api/campaigns/${slug}`);
        const data = await resp.json();
        const versions = data.versions || [];

        elements.versionSelect.innerHTML = "";
        for (const v of versions) {
            const opt = document.createElement("option");
            opt.value = `${slug}:${v.version}`;
            opt.textContent = `Version ${v.version}`;
            if (v.version === currentVersion) opt.selected = true;
            elements.versionSelect.appendChild(opt);
        }
        elements.versionBar.classList.remove("d-none");
    } catch (_err) {
        // Silently fail
    }
}

// ── UI Helpers ────────────────────────────────────────────────────────

let currentCampaignSlug = null;

function setGenerating(active) {
    elements.generateBtn.disabled = active;
    elements.generateBtn.innerHTML = active
        ? '<span class="cap-spinner"></span> Generating...'
        : '<i class="bi bi-lightning-charge me-1"></i>Generate Creatives';
}

// ── Event Listeners ───────────────────────────────────────────────────

// Bind events safely — check element exists before adding listener
if (elements.validateBtn) elements.validateBtn.addEventListener("click", validateAndShowProducts);
if (elements.generateForm) elements.generateForm.addEventListener("submit", handleGenerate);
if (elements.downloadBtn) elements.downloadBtn.addEventListener("click", handleDownload);
if (elements.regenerateBtn) elements.regenerateBtn.addEventListener("click", handleRegenerate);
if (elements.deleteBtn) elements.deleteBtn.addEventListener("click", handleDelete);
if (elements.versionSelect) elements.versionSelect.addEventListener("change", handleVersionChange);

// Load campaigns on page load
loadCampaigns();
