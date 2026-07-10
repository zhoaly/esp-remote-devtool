let lvglPreviewJobs = [];
let currentLvglPreviewUrl = null;

function setLvglPreviewStatus(text, type = "") {
    setStatus("lvglPreviewStatusBox", text, type);
}

function previewJobFromQuery() {
    return new URLSearchParams(window.location.search).get("job_id") || "";
}

function setLvglPreview(previewUrl) {
    currentLvglPreviewUrl = previewUrl ? REMOTE_BASE + previewUrl : null;
    const frame = document.getElementById("lvglPreviewFrame");
    const wrap = document.getElementById("lvglPreviewWrap");
    const empty = document.getElementById("lvglPreviewEmpty");
    const liveBadge = document.getElementById("lvglPreviewLiveBadge");

    if (!currentLvglPreviewUrl) {
        frame.removeAttribute("src");
        empty.style.display = "grid";
        wrap.classList.remove("loading");
        if (liveBadge) liveBadge.style.display = "none";
        return;
    }

    wrap.classList.add("loading");
    empty.style.display = "none";
    if (liveBadge) liveBadge.style.display = "none";
    frame.src = `${currentLvglPreviewUrl}?t=${Date.now()}`;

    frame.onload = function onPreviewLoad() {
        stripEmscriptenChrome(frame);
        wrap.classList.remove("loading");
        if (liveBadge) liveBadge.style.display = "inline-flex";
        frame.onload = null;
    };
}

function reloadLvglPreview() {
    if (!currentLvglPreviewUrl) {
        setLvglPreviewStatus("Select a successful build before refreshing preview.", "failed");
        return;
    }
    setLvglPreview(currentLvglPreviewUrl.replace(REMOTE_BASE, ""));
}

function selectLvglPreviewJob(jobId) {
    const job = lvglPreviewJobs.find((item) => item.job_id === jobId);
    if (!job || !job.preview_url) return;

    currentJobId = job.job_id;
    currentJob = job;
    setLvglPreview(job.preview_url);
    renderLvglPreviewJobs();

    setText("lvglPreviewJobCard", job.job_id);
    setText("lvglPreviewSize", lvglJobDimensions(job));
    setLvglPreviewStatus([
        `Selected build: ${job.job_id}`,
        `Project: ${job.project_name || "-"}`,
        `Size: ${lvglJobDimensions(job)}`,
        `Created: ${job.created_at || "-"}`
    ].join("\n"), "success");

    const openLink = document.getElementById("lvglOpenPreviewLink");
    const logLink = document.getElementById("lvglOpenLogLink");
    const downloadLink = document.getElementById("lvglDownloadLink");
    if (openLink) {
        openLink.href = REMOTE_BASE + job.preview_url;
        openLink.classList.remove("disabled");
    }
    if (logLink) {
        logLink.href = job.log_url ? REMOTE_BASE + job.log_url : "#";
        logLink.classList.toggle("disabled", !job.log_url);
    }
    if (downloadLink) {
        const downloadUrl = job.artifact_url || job.download_url;
        downloadLink.href = downloadUrl ? REMOTE_BASE + downloadUrl : "#";
        downloadLink.classList.toggle("disabled", !downloadUrl);
    }
}

function renderLvglPreviewJobs() {
    const list = document.getElementById("lvglPreviewJobsList");
    if (!list) return;

    if (!lvglPreviewJobs.length) {
        currentJobId = null;
        currentJob = null;
        currentLvglPreviewUrl = null;
        setLvglPreview(null);
        list.innerHTML = '<div class="empty-state">No successful LVGL preview builds yet.</div>';
        return;
    }

    list.innerHTML = lvglPreviewJobs.map((job) => {
        const selected = job.job_id === currentJobId ? " selected" : "";
        const downloadName = job.artifact_name || "lvgl_preview.zip";
        return `
            <button class="list-row${selected}" type="button" onclick="selectLvglPreviewJob('${lvglEscapeHtml(job.job_id)}')">
                <span>
                    <strong>${lvglEscapeHtml(job.project_name || "-")}</strong>
                    <small>${lvglEscapeHtml(job.job_id)} · ${lvglEscapeHtml(lvglJobDimensions(job))} · ${lvglEscapeHtml(job.created_at || "")}</small>
                </span>
                <span class="row-meta">
                    <span>${lvglEscapeHtml(downloadName)}</span>
                    <span class="tag success">Preview ready</span>
                </span>
            </button>
        `;
    }).join("");
}

async function loadLvglPreviewJobs() {
    const list = document.getElementById("lvglPreviewJobsList");
    if (list) list.innerHTML = '<div class="empty-state">Loading LVGL preview builds...</div>';

    try {
        lvglPreviewJobs = (await apiGet("/api/lvgl/jobs")).filter(isLvglPreviewJob);
        renderLvglPreviewJobs();

        const requestedJobId = previewJobFromQuery();
        const requested = requestedJobId ? lvglPreviewJobs.find((job) => job.job_id === requestedJobId) : null;
        const defaultJob = requested || lvglPreviewJobs[0];
        if (defaultJob) {
            selectLvglPreviewJob(defaultJob.job_id);
        }
    } catch (err) {
        if (list) list.innerHTML = `<div class="empty-state failed">Failed to load LVGL builds: ${lvglEscapeHtml(err.message)}</div>`;
        setLvglPreviewStatus(`Failed to load LVGL builds\n${err.message}`, "failed");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("lvglPreviewJobsList")) return;
    loadLvglPreviewJobs();
});
