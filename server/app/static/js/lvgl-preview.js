let lvglPreviewJobs = [];
let currentLvglPreviewUrl = null;
const LVGL_ENCODER_CHANNEL = "zlyhub.lvgl.encoder.v1";
const LVGL_ENCODER_PROBE_INTERVAL_MS = 250;
const LVGL_ENCODER_PROBE_LIMIT = 40;
let lvglEncoderReady = false;
let lvglEncoderPressed = false;
let lvglEncoderProbeTimer = null;
let lvglEncoderProbeAttempts = 0;

function lvglEncoderElements() {
    return {
        badge: document.getElementById("lvglEncoderBadge"),
        hint: document.getElementById("lvglEncoderHint"),
        left: document.getElementById("lvglEncoderLeftBtn"),
        press: document.getElementById("lvglEncoderPressBtn"),
        right: document.getElementById("lvglEncoderRightBtn"),
    };
}

function stopLvglEncoderProbe() {
    if (lvglEncoderProbeTimer) {
        clearInterval(lvglEncoderProbeTimer);
        lvglEncoderProbeTimer = null;
    }
    lvglEncoderProbeAttempts = 0;
}

function setLvglEncoderAvailability(state, hint) {
    const elements = lvglEncoderElements();
    const labels = {
        idle: "未加载",
        waiting: "连接中",
        ready: "编码器可用",
        unavailable: "不支持",
    };
    lvglEncoderReady = state === "ready";

    if (elements.badge) {
        elements.badge.textContent = labels[state] || labels.idle;
        elements.badge.className = "tag";
        if (state === "ready") elements.badge.classList.add("success");
        if (state === "unavailable") elements.badge.classList.add("failed");
    }
    if (elements.hint) elements.hint.textContent = hint || "";
    [elements.left, elements.press, elements.right].forEach((button) => {
        if (button) button.disabled = !lvglEncoderReady;
    });

    if (!lvglEncoderReady && elements.press) {
        lvglEncoderPressed = false;
        elements.press.classList.remove("is-pressed");
        elements.press.setAttribute("aria-pressed", "false");
    }
}

function postLvglEncoderMessage(message) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (!frame?.contentWindow || !currentLvglPreviewUrl) return false;
    frame.contentWindow.postMessage(
        { channel: LVGL_ENCODER_CHANNEL, ...message },
        window.location.origin
    );
    return true;
}

function setLvglEncoderPressed(pressed) {
    if (!lvglEncoderReady || lvglEncoderPressed === pressed) return;
    lvglEncoderPressed = pressed;
    const button = document.getElementById("lvglEncoderPressBtn");
    if (button) {
        button.classList.toggle("is-pressed", pressed);
        button.setAttribute("aria-pressed", String(pressed));
    }
    postLvglEncoderMessage({ action: "press", pressed });
}

function releaseLvglEncoder() {
    if (lvglEncoderPressed) setLvglEncoderPressed(false);
}

function rotateLvglEncoder(steps) {
    if (!lvglEncoderReady || !Number.isInteger(steps) || steps === 0) return;
    postLvglEncoderMessage({ action: "rotate", steps });
}

function resetLvglEncoderBridge(state = "idle", hint = "请选择支持编码器桥接的完整工程预览。") {
    releaseLvglEncoder();
    stopLvglEncoderProbe();
    setLvglEncoderAvailability(state, hint);
}

function probeLvglEncoderBridge() {
    if (lvglEncoderReady) {
        stopLvglEncoderProbe();
        return;
    }

    lvglEncoderProbeAttempts += 1;
    postLvglEncoderMessage({ action: "probe" });
    if (lvglEncoderProbeAttempts >= LVGL_ENCODER_PROBE_LIMIT) {
        stopLvglEncoderProbe();
        setLvglEncoderAvailability(
            "unavailable",
            "该构建未提供编码器桥接；原有鼠标预览仍可正常使用。"
        );
    }
}

function startLvglEncoderProbe() {
    resetLvglEncoderBridge("waiting", "正在连接预览中的编码器桥接…");
    probeLvglEncoderBridge();
    if (!lvglEncoderReady) {
        lvglEncoderProbeTimer = setInterval(
            probeLvglEncoderBridge,
            LVGL_ENCODER_PROBE_INTERVAL_MS
        );
    }
}

function handleLvglEncoderMessage(event) {
    const frame = document.getElementById("lvglPreviewFrame");
    if (
        event.origin !== window.location.origin ||
        event.source !== frame?.contentWindow ||
        event.data?.channel !== LVGL_ENCODER_CHANNEL ||
        event.data?.action !== "ready"
    ) {
        return;
    }

    stopLvglEncoderProbe();
    setLvglEncoderAvailability(
        "ready",
        "滚轮或 ←/→ 旋转，Enter/Space 按下；也可使用下方控件。"
    );
}

function bindLvglEncoderControls() {
    const { left, press, right } = lvglEncoderElements();
    if (!left || !press || !right) return;

    left.addEventListener("click", () => rotateLvglEncoder(-1));
    right.addEventListener("click", () => rotateLvglEncoder(1));

    press.addEventListener("pointerdown", (event) => {
        if (!lvglEncoderReady) return;
        event.preventDefault();
        press.setPointerCapture?.(event.pointerId);
        setLvglEncoderPressed(true);
    });
    press.addEventListener("pointerup", (event) => {
        event.preventDefault();
        setLvglEncoderPressed(false);
    });
    press.addEventListener("pointercancel", () => setLvglEncoderPressed(false));
    press.addEventListener("lostpointercapture", () => setLvglEncoderPressed(false));
    press.addEventListener("keydown", (event) => {
        if ((event.key === "Enter" || event.key === " ") && !event.repeat) {
            event.preventDefault();
            setLvglEncoderPressed(true);
        }
    });
    press.addEventListener("keyup", (event) => {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setLvglEncoderPressed(false);
        }
    });
    press.addEventListener("blur", releaseLvglEncoder);

    window.addEventListener("pointerup", releaseLvglEncoder);
    window.addEventListener("pointercancel", releaseLvglEncoder);
    window.addEventListener("blur", releaseLvglEncoder);
    window.addEventListener("message", handleLvglEncoderMessage);
}

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
        resetLvglEncoderBridge();
        setLvglPreviewDimensions();
        frame.removeAttribute("src");
        empty.style.display = "grid";
        wrap.classList.remove("loading");
        if (liveBadge) liveBadge.style.display = "none";
        return;
    }

    resetLvglEncoderBridge("waiting", "正在加载预览并等待编码器桥接…");
    wrap.classList.add("loading");
    empty.style.display = "none";
    if (liveBadge) liveBadge.style.display = "none";
    frame.src = `${currentLvglPreviewUrl}?t=${Date.now()}`;

    frame.onload = function onPreviewLoad() {
        stripEmscriptenChrome(frame);
        wrap.classList.remove("loading");
        if (liveBadge) liveBadge.style.display = "inline-flex";
        startLvglEncoderProbe();
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
    bindLvglEncoderControls();
    resetLvglEncoderBridge();
    loadLvglPreviewJobs();
});
