const REMOTE_BASE = window.location.origin;
const LOCAL_AGENT = "http://127.0.0.1:8765";

let currentJobId = null;
let currentDownloadUrl = null;
let currentJob = null;
let currentManifestUrl = null;
let pollTimer = null;

function setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
}

function setStatus(id, text, type = "") {
    const box = document.getElementById(id);
    if (!box) return;
    box.className = "status";
    if (type) box.classList.add(type);
    box.textContent = text;
}

function setBuildStatus(text, type = "") { setStatus("buildStatusBox", text, type); }
function setFlashStatus(text, type = "") { setStatus("flashStatusBox", text, type); }
function setOtaStatus(text, type = "") { setStatus("otaStatusBox", text, type); }

function setLinks(downloadUrl, logUrl) {
    const area = document.getElementById("linkArea");
    if (!area) return;
    area.innerHTML = "";
    if (downloadUrl) {
        const download = document.createElement("a");
        download.href = REMOTE_BASE + downloadUrl;
        download.target = "_blank";
        download.textContent = "下载固件包";
        area.appendChild(download);
    }
    if (logUrl) {
        const log = document.createElement("a");
        log.href = REMOTE_BASE + logUrl;
        log.target = "_blank";
        log.textContent = "打开完整构建日志";
        area.appendChild(log);
    }
}

async function parseErrorResponse(resp) {
    const text = await resp.text();
    try {
        const data = JSON.parse(text);
        return typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data, null, 2);
    } catch {
        return text || `HTTP ${resp.status}`;
    }
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

function initCommonChrome() {
    setText("remoteBaseText", REMOTE_BASE + "/ui");
    setText("remoteHostCard", REMOTE_BASE);
    setText("localAgentCard", LOCAL_AGENT);
}

document.addEventListener("DOMContentLoaded", initCommonChrome);
