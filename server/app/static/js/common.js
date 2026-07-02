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
    enhanceSelects();
}

function closeCustomSelects(except = null) {
    document.querySelectorAll(".custom-select.open").forEach((select) => {
        if (select !== except) {
            select.classList.remove("open");
            const trigger = select.querySelector(".custom-select-trigger");
            if (trigger) trigger.setAttribute("aria-expanded", "false");
        }
    });
}

function refreshCustomSelect(select) {
    const custom = select.nextElementSibling;
    if (!custom || !custom.classList.contains("custom-select")) return;

    const value = custom.querySelector(".custom-select-value");
    const menu = custom.querySelector(".custom-select-menu");
    const selectedOption = select.options[select.selectedIndex] || select.options[0];

    value.textContent = selectedOption ? selectedOption.textContent : "";
    menu.innerHTML = "";

    Array.from(select.options).forEach((option) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "custom-select-option";
        item.textContent = option.textContent;
        item.dataset.value = option.value;
        item.setAttribute("role", "option");
        item.setAttribute("aria-selected", option.selected ? "true" : "false");
        if (option.selected) item.classList.add("selected");

        item.addEventListener("click", () => {
            select.value = option.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            refreshCustomSelect(select);
            custom.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
        });

        menu.appendChild(item);
    });
}

function enhanceSelect(select) {
    if (select.dataset.enhancedSelect === "true") return;
    select.dataset.enhancedSelect = "true";
    select.classList.add("native-select-hidden");

    const custom = document.createElement("div");
    custom.className = "custom-select";

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "custom-select-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const value = document.createElement("span");
    value.className = "custom-select-value";
    const arrow = document.createElement("span");
    arrow.className = "custom-select-arrow";
    trigger.append(value, arrow);

    const menu = document.createElement("div");
    menu.className = "custom-select-menu";
    menu.setAttribute("role", "listbox");

    custom.append(trigger, menu);
    select.insertAdjacentElement("afterend", custom);

    trigger.addEventListener("click", () => {
        const isOpen = custom.classList.contains("open");
        closeCustomSelects(custom);
        custom.classList.toggle("open", !isOpen);
        trigger.setAttribute("aria-expanded", String(!isOpen));
    });

    trigger.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            custom.classList.remove("open");
            trigger.setAttribute("aria-expanded", "false");
        }
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            trigger.click();
        }
    });

    select.addEventListener("change", () => refreshCustomSelect(select));

    const observer = new MutationObserver(() => refreshCustomSelect(select));
    observer.observe(select, { childList: true, subtree: true, attributes: true });

    refreshCustomSelect(select);
}

function enhanceSelects() {
    document.querySelectorAll("select").forEach(enhanceSelect);
}

document.addEventListener("click", (event) => {
    if (!(event.target instanceof Element) || !event.target.closest(".custom-select")) {
        closeCustomSelects();
    }
});

document.addEventListener("DOMContentLoaded", initCommonChrome);
