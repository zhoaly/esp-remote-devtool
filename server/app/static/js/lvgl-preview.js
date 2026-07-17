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
        setLvglPreviewDimensions();
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

function setLvglPreviewDimensions(job) {
    const wrap = document.getElementById("lvglPreviewWrap");
    if (!wrap) return;

    const width = Number.parseInt(job?.width, 10);
    const height = Number.parseInt(job?.height, 10);
    wrap.style.setProperty("--lvgl-preview-width", String(Number.isFinite(width) && width >= 120 ? width : 128));
    wrap.style.setProperty("--lvgl-preview-height", String(Number.isFinite(height) && height >= 120 ? height : 296));
}

function reloadLvglPreview() {
    if (!currentLvglPreviewUrl) {
        setLvglPreviewStatus("请先选择一个成功的构建，再刷新预览。", "failed");
        return;
    }
    setLvglPreview(currentLvglPreviewUrl.replace(REMOTE_BASE, ""));
}

function selectLvglPreviewJob(jobId) {
    const job = lvglPreviewJobs.find((item) => item.job_id === jobId);
    if (!job || !job.preview_url) return;

    currentJobId = job.job_id;
    currentJob = job;
    setLvglPreviewDimensions(job);
    setLvglPreview(job.preview_url);
    renderLvglPreviewJobs();

    setText("lvglPreviewJobCard", job.job_id);
    setText("lvglPreviewSize", lvglJobDimensions(job));
    setLvglPreviewStatus([
        `已选择构建: ${job.job_id}`,
        `工程: ${job.project_name || "-"}`,
        `尺寸: ${lvglJobDimensions(job)}`,
        `创建时间: ${job.created_at || "-"}`
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
        list.innerHTML = '<div class="empty-state">暂无成功的 LVGL 预览构建。</div>';
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
                    <span class="tag success">可预览</span>
                </span>
            </button>
        `;
    }).join("");
}

async function loadLvglPreviewJobs() {
    const list = document.getElementById("lvglPreviewJobsList");
    if (list) list.innerHTML = '<div class="empty-state">正在加载 LVGL 预览构建...</div>';

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
        if (list) list.innerHTML = `<div class="empty-state failed">加载 LVGL 构建失败：${lvglEscapeHtml(err.message)}</div>`;
        setLvglPreviewStatus(`加载 LVGL 构建失败\n${err.message}`, "failed");
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("lvglPreviewJobsList")) return;
    loadLvglPreviewJobs();
});
