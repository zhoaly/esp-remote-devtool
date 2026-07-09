const OTA_VERSION_RE = /^\d+\.\d+\.\d+$/;
const OTA_SHORT_VERSION_RE = /^\d+\.\d+$/;

let otaJobs = [];
let otaReleases = [];
let currentManifestDirectUrl = null;
let currentFirmwareUrl = null;

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function isOtaPage() {
    return Boolean(document.getElementById("otaJobsList"));
}

function getOtaChannel() {
    const channel = document.getElementById("otaChannel")?.value || "test";
    if (channel !== "custom") return channel;
    return document.getElementById("otaCustomChannel")?.value.trim() || "";
}

function handleOtaChannelChange() {
    const channel = document.getElementById("otaChannel")?.value;
    const customField = document.getElementById("otaCustomChannelField");
    if (customField) customField.style.display = channel === "custom" ? "grid" : "none";
}

function normalizeOtaVersionForInput(version) {
    const normalized = String(version || "").trim();
    if (OTA_SHORT_VERSION_RE.test(normalized)) return `${normalized}.0`;
    return normalized;
}

function sortReleasesNewestFirst(releases) {
    return [...releases].sort((a, b) => {
        const left = String(a.created_at || a.release_id || "");
        const right = String(b.created_at || b.release_id || "");
        return right.localeCompare(left);
    });
}

function releasesForJob(jobId) {
    if (!jobId) return [];
    return sortReleasesNewestFirst(otaReleases.filter((release) => release.job_id === jobId));
}

function latestReleaseForJob(jobId) {
    return releasesForJob(jobId)[0] || null;
}

function releaseForJob(job) {
    if (!job) return null;
    if (job.ota_release_id) {
        const exact = otaReleases.find((release) => release.release_id === job.ota_release_id);
        if (exact) return exact;
    }
    return latestReleaseForJob(job.job_id);
}

function applyReleaseUrls(release, job) {
    currentManifestUrl = release?.manifest_url || job?.ota_manifest_url || null;
    currentManifestDirectUrl = release?.manifest_direct_url || null;
    currentFirmwareUrl = release?.firmware_url || job?.ota_firmware_url || null;
}

function validateOtaForm() {
    if (!currentJobId || !currentJob) {
        return "请选择可发布的构建任务。";
    }
    if (currentJob.status !== "success") {
        return "只有成功构建任务可以发布。";
    }
    if (!currentJob.ota_publishable) {
        return "当前构建不可发布 OTA，请检查 app.bin 大小和构建产物。";
    }

    const channel = getOtaChannel();
    if (!/^[A-Za-z0-9_.-]+$/.test(channel)) {
        return "Channel 只能包含字母、数字、下划线、点和短横线。";
    }

    const version = normalizeOtaVersionForInput(document.getElementById("otaVersion")?.value);
    if (!OTA_VERSION_RE.test(version)) {
        return "Version 必须是 x.y.z 格式，例如 0.1.1。";
    }

    const minVersion = normalizeOtaVersionForInput(document.getElementById("otaMinVersion")?.value);
    if (minVersion && !OTA_VERSION_RE.test(minVersion)) {
        return "Min Version 必须为空或 x.y.z 格式。";
    }

    return "";
}

function buildOtaPayload() {
    return {
        channel: getOtaChannel(),
        version: normalizeOtaVersionForInput(document.getElementById("otaVersion").value),
        min_version: normalizeOtaVersionForInput(document.getElementById("otaMinVersion").value),
        force: document.getElementById("otaForce").value === "true",
        release_notes: document.getElementById("otaReleaseNotes").value.trim(),
    };
}

function updateSelectedJobChrome() {
    setText("otaSelectedJobCard", currentJobId || "未选择");
    setText("otaManifestCard", currentManifestUrl || "未发布");
}

function renderSelectedJobStatus() {
    if (!currentJob) {
        setOtaStatus("请选择可发布的成功构建。");
        return;
    }

    const publishable = Boolean(currentJob.ota_publishable);
    const limit = currentJob.ota_partition_limit || 0;
    const release = releaseForJob(currentJob);
    const lines = [
        `Job ID: ${currentJob.job_id}`,
        `项目: ${currentJob.project_name || "-"}`,
        `Target: ${currentJob.target || "-"}`,
        `Version: ${normalizeOtaVersionForInput(currentJob.project_version) || "-"}`,
        `App Bin: ${currentJob.ota_app_bin_name || "未识别"}`,
        `App Size: ${currentJob.ota_app_size || 0} / ${limit} bytes`,
        `App SHA256: ${currentJob.ota_app_sha256 || "-"}`,
        release ? `已发布 Release: ${release.release_id || "-"}` : "已发布 Release: -",
        release ? `已发布 Channel/Version: ${release.channel || "-"} / ${release.version || "-"}` : "已发布 Channel/Version: -",
        publishable ? "状态: 可发布 OTA" : "状态: 不可发布 OTA",
    ];
    setOtaStatus(lines.join("\n"), publishable ? "success" : "failed");
}

function selectOtaJob(jobId) {
    const job = otaJobs.find((item) => item.job_id === jobId);
    if (!job) return;

    currentJobId = job.job_id;
    currentJob = job;
    const release = releaseForJob(job);
    applyReleaseUrls(release, job);

    const versionInput = document.getElementById("otaVersion");
    if (versionInput && !versionInput.value.trim()) {
        versionInput.value = normalizeOtaVersionForInput(job.project_version);
    }
    const minVersionInput = document.getElementById("otaMinVersion");
    if (minVersionInput && !minVersionInput.value.trim()) {
        minVersionInput.value = "0.0.0";
    }

    const publishBtn = document.getElementById("otaPublishBtn");
    if (publishBtn) publishBtn.disabled = !job.ota_publishable;

    updateSelectedJobChrome();
    renderSelectedJobStatus();
    renderOtaJobs();
    renderReleaseResult(release);
}

function syncCurrentOtaSelection() {
    if (!currentJob) return;

    const release = releaseForJob(currentJob);
    applyReleaseUrls(release, currentJob);
    updateSelectedJobChrome();
    renderSelectedJobStatus();
    renderOtaJobs();
    renderReleaseResult(release);
}

function jobStatusBadge(job) {
    if (job.status !== "success") return '<span class="tag failed">构建失败</span>';
    if (!job.ota_publishable) return '<span class="tag failed">不可发布</span>';
    if (releaseForJob(job)) return '<span class="tag success">已发布</span>';
    return '<span class="tag success">可发布</span>';
}

function renderOtaJobs() {
    const list = document.getElementById("otaJobsList");
    if (!list) return;

    const successJobs = otaJobs.filter((job) => job.status === "success");
    if (!successJobs.length) {
        list.innerHTML = '<div class="empty-state">暂无成功构建。请先在“远端编译”页面完成一次构建。</div>';
        return;
    }

    list.innerHTML = successJobs.map((job) => {
        const selected = job.job_id === currentJobId ? " selected" : "";
        const size = `${job.ota_app_size || 0} bytes`;
        const version = normalizeOtaVersionForInput(job.project_version) || "-";
        const project = job.project_name || "-";
        const target = job.target || "-";
        return `
            <button class="list-row${selected}" type="button" onclick="selectOtaJob('${escapeHtml(job.job_id)}')">
                <span>
                    <strong>${escapeHtml(project)}</strong>
                    <small>${escapeHtml(job.job_id)} · ${escapeHtml(target)} · ${escapeHtml(job.created_at || "")}</small>
                </span>
                <span class="row-meta">
                    <span>v${escapeHtml(version)}</span>
                    <span>${escapeHtml(size)}</span>
                    ${jobStatusBadge(job)}
                </span>
            </button>
        `;
    }).join("");
}

async function loadOtaJobs() {
    const list = document.getElementById("otaJobsList");
    if (list) list.innerHTML = '<div class="empty-state">加载构建记录...</div>';

    try {
        otaJobs = (await apiGet("/api/jobs")).filter(isEspFirmwareJob);
        renderOtaJobs();

        if (!currentJobId) {
            const defaultJob = otaJobs.find((job) => job.status === "success" && job.ota_publishable);
            if (defaultJob) {
                selectOtaJob(defaultJob.job_id);
                return;
            }
        }

        if (currentJobId) {
            const refreshed = otaJobs.find((job) => job.job_id === currentJobId);
            if (refreshed) {
                currentJob = refreshed;
                const release = releaseForJob(refreshed);
                applyReleaseUrls(release, refreshed);
                updateSelectedJobChrome();
                renderSelectedJobStatus();
                renderOtaJobs();
                renderReleaseResult(release);
            }
        }
    } catch (err) {
        if (list) list.innerHTML = `<div class="empty-state failed">加载构建记录失败：${escapeHtml(err.message)}</div>`;
        setOtaStatus(`加载构建记录失败\n${err.message}`, "failed");
    }
}

function renderReleaseResult(release) {
    const box = document.getElementById("otaReleaseResult");
    if (!box) return;

    if (!release) {
        box.innerHTML = '<div class="empty-state">发布成功后这里会显示 manifest、firmware 和升级命令。</div>';
        return;
    }

    box.innerHTML = `
        <div class="result-grid">
            <div><span>Release ID</span><strong>${escapeHtml(release.release_id || "-")}</strong></div>
            <div><span>Channel</span><strong>${escapeHtml(release.channel || "-")}</strong></div>
            <div><span>Version</span><strong>${escapeHtml(release.version || "-")}</strong></div>
            <div><span>Firmware Size</span><strong>${escapeHtml(release.size || 0)} bytes</strong></div>
        </div>
        <div class="copy-list">
            <button class="copy-row" type="button" onclick="copyTextValue('${escapeHtml(release.manifest_url || "")}', 'Latest Manifest URL')">
                <span>Latest Manifest URL</span><code>${escapeHtml(release.manifest_url || "-")}</code>
            </button>
            <button class="copy-row" type="button" onclick="copyTextValue('${escapeHtml(release.manifest_direct_url || "")}', 'Direct Manifest URL')">
                <span>Direct Manifest URL</span><code>${escapeHtml(release.manifest_direct_url || "-")}</code>
            </button>
            <button class="copy-row" type="button" onclick="copyTextValue('${escapeHtml(release.firmware_url || "")}', 'Firmware URL')">
                <span>Firmware URL</span><code>${escapeHtml(release.firmware_url || "-")}</code>
            </button>
            <button class="copy-row" type="button" onclick="copyTextValue('ota check ${escapeHtml(release.manifest_url || "")}', 'ota check 命令')">
                <span>ota check</span><code>ota check ${escapeHtml(release.manifest_url || "-")}</code>
            </button>
            <button class="copy-row" type="button" onclick="copyTextValue('ota upgrade_manifest ${escapeHtml(release.manifest_url || "")}', 'ota upgrade_manifest 命令')">
                <span>ota upgrade_manifest</span><code>ota upgrade_manifest ${escapeHtml(release.manifest_url || "-")}</code>
            </button>
        </div>
    `;
}

async function publishOtaRelease() {
    const validationError = validateOtaForm();
    if (validationError) {
        setOtaStatus(validationError, "failed");
        return;
    }

    const btn = document.getElementById("otaPublishBtn");
    if (btn) btn.disabled = true;

    try {
        const data = await apiPostJson("/api/ota/publish/" + currentJobId, buildOtaPayload());
        currentManifestUrl = data.manifest_url;
        currentManifestDirectUrl = data.manifest_direct_url;
        currentFirmwareUrl = data.firmware_url;

        setOtaStatus([
            "OTA 发布成功",
            `Release ID: ${data.release_id}`,
            `Latest Manifest URL: ${data.manifest_url}`,
            `Direct Manifest URL: ${data.manifest_direct_url}`,
            `Firmware URL: ${data.firmware_url}`,
            "",
            `ota check ${data.manifest_url}`,
            `ota upgrade_manifest ${data.manifest_url}`,
        ].join("\n"), "success");

        updateSelectedJobChrome();
        renderReleaseResult(data);

        if (isOtaPage()) {
            await loadOtaReleases();
            await loadOtaJobs();
        }
    } catch (err) {
        setOtaStatus(`OTA 发布失败\n${err.message}`, "failed");
    } finally {
        if (btn) btn.disabled = currentJob ? !currentJob.ota_publishable : true;
    }
}

function copyTextWithTextarea(value) {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.top = "0";
    textarea.style.left = "0";
    textarea.style.width = "1px";
    textarea.style.height = "1px";
    textarea.style.opacity = "0";
    textarea.style.pointerEvents = "none";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);

    let copied = false;
    try {
        copied = document.execCommand("copy");
    } finally {
        document.body.removeChild(textarea);
    }
    return copied;
}

async function copyTextValue(value, label) {
    if (!value) {
        setOtaStatus(`${label} 为空，无法复制。`, "failed");
        return;
    }

    try {
        if (window.isSecureContext && navigator.clipboard) {
            await navigator.clipboard.writeText(value);
        } else if (!copyTextWithTextarea(value)) {
            throw new Error("Fallback copy failed");
        }
        setOtaStatus(`已复制 ${label}\n${value}`, "success");
    } catch {
        if (copyTextWithTextarea(value)) {
            setOtaStatus(`已复制 ${label}\n${value}`, "success");
            return;
        }
        setOtaStatus(`无法自动复制 ${label}，请手动复制：\n${value}`, "failed");
    }
}

async function copyManifestUrl() {
    await copyTextValue(currentManifestUrl, "Manifest URL");
}

async function copyFirmwareUrl() {
    await copyTextValue(currentFirmwareUrl, "Firmware URL");
}

function renderOtaReleases() {
    const body = document.getElementById("otaReleasesBody");
    if (!body) return;

    if (!otaReleases.length) {
        body.innerHTML = '<tr><td colspan="8">暂无 OTA 发布记录。</td></tr>';
        return;
    }

    body.innerHTML = otaReleases.map((release) => {
        const releaseId = escapeHtml(release.release_id || "");
        const manifest = release.manifest_url
            ? `<a href="${escapeHtml(release.manifest_url)}" target="_blank">latest</a>`
            : "-";
        const direct = release.manifest_direct_url
            ? `<a href="${escapeHtml(release.manifest_direct_url)}" target="_blank">direct</a>`
            : "-";
        const firmware = release.firmware_url
            ? `<a href="${escapeHtml(release.firmware_url)}" target="_blank">firmware</a>`
            : "-";
        return `
            <tr>
                <td>${escapeHtml(release.channel || "")}</td>
                <td>${escapeHtml(release.project || "")}</td>
                <td>${escapeHtml(release.chip || "")}</td>
                <td>${escapeHtml(release.version || "")}</td>
                <td>${escapeHtml(release.created_at || "")}</td>
                <td>${escapeHtml(release.job_id || "")}</td>
                <td>${manifest} / ${direct} / ${firmware}</td>
                <td>
                    <button class="secondary compact-button danger-button" type="button" onclick="deleteOtaRelease('${releaseId}')">删除</button>
                </td>
            </tr>
        `;
    }).join("");
}

async function deleteOtaRelease(releaseId) {
    const release = otaReleases.find((item) => item.release_id === releaseId);
    const label = release
        ? `${release.channel || "-"} / ${release.project || "-"} / ${release.version || "-"}`
        : releaseId;

    if (!window.confirm(`确认删除 OTA Release ${releaseId}？\n${label}\n\n此操作会删除该 release 的 manifest 和 app.bin。`)) {
        return;
    }

    try {
        const data = await apiDelete("/api/ota/releases/" + encodeURIComponent(releaseId));
        await loadOtaReleases();
        await loadOtaJobs();
        syncCurrentOtaSelection();

        const latest = data.latest || {};
        const jobState = data.job_state || {};
        const latestLine = latest.latest_release_id
            ? `Latest 已回退到: ${latest.latest_release_id}`
            : "Latest 已清空";
        const jobLine = jobState.job_exists === false
            ? "原构建记录不存在，已跳过构建状态同步"
            : jobState.published
                ? `当前构建仍已发布: ${jobState.release_id || "-"}`
                : "当前构建已回到可发布状态";

        setOtaStatus([
            "OTA Release 删除成功",
            `Deleted Release ID: ${data.deleted_release_id}`,
            latestLine,
            jobLine,
        ].join("\n"), "success");
    } catch (err) {
        setOtaStatus(`删除 OTA Release 失败\n${err.message}`, "failed");
    }
}

async function loadOtaReleases() {
    const body = document.getElementById("otaReleasesBody");
    if (body) body.innerHTML = '<tr><td colspan="8">加载中...</td></tr>';

    try {
        const data = await apiGet("/api/ota/releases");
        otaReleases = data.releases || [];
        renderOtaReleases();
        syncCurrentOtaSelection();
    } catch (err) {
        if (body) body.innerHTML = `<tr><td colspan="8">加载失败：${escapeHtml(err.message)}</td></tr>`;
    }
}

async function initOtaPage() {
    if (!isOtaPage()) return;

    handleOtaChannelChange();
    updateSelectedJobChrome();
    await loadOtaReleases();
    await loadOtaJobs();
    syncCurrentOtaSelection();
}

document.addEventListener("DOMContentLoaded", initOtaPage);
