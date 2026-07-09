let flashJobs = [];

function flashEscapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function updateFlashButtonState() {
    const flashBtn = document.getElementById("flashBtn");
    if (flashBtn) flashBtn.disabled = !currentDownloadUrl;
}

function renderSelectedFlashJobStatus(job) {
    setFlashStatus([
        `已选择构建: ${job.job_id}`,
        `项目: ${job.project_name || "-"}`,
        `Target: ${job.target || "-"}`,
        `Artifact: ${currentDownloadUrl}`,
        "",
        "请刷新或选择串口后开始烧录。"
    ].join("\n"), "success");
}

function selectFlashJob(jobId) {
    const job = flashJobs.find((item) => item.job_id === jobId);
    if (!job || !job.download_url) return;

    currentJobId = job.job_id;
    currentJob = job;
    currentDownloadUrl = REMOTE_BASE + job.download_url;

    renderFlashJobs();
    renderSelectedFlashJobStatus(job);
    updateFlashButtonState();
}

function flashJobStatusBadge(job) {
    if (job.status !== "success") return '<span class="tag failed">构建失败</span>';
    if (!job.download_url) return '<span class="tag failed">无产物</span>';
    return '<span class="tag success">可烧录</span>';
}

function renderFlashJobs() {
    const list = document.getElementById("flashJobsList");
    if (!list) return;

    const jobs = flashJobs.filter((job) => job.status === "success" && job.download_url);
    if (!jobs.length) {
        currentJobId = null;
        currentJob = null;
        currentDownloadUrl = null;
        list.innerHTML = '<div class="empty-state">暂无可烧录构建。请先在“远端编译”页面完成一次成功构建。</div>';
        updateFlashButtonState();
        return;
    }

    list.innerHTML = jobs.map((job) => {
        const selected = job.job_id === currentJobId ? " selected" : "";
        const project = job.project_name || "-";
        const target = job.target || "-";
        const artifactName = job.artifact_name || "firmware.zip";
        return `
            <button class="list-row${selected}" type="button" onclick="selectFlashJob('${flashEscapeHtml(job.job_id)}')">
                <span>
                    <strong>${flashEscapeHtml(project)}</strong>
                    <small>${flashEscapeHtml(job.job_id)} · ${flashEscapeHtml(target)} · ${flashEscapeHtml(job.created_at || "")}</small>
                </span>
                <span class="row-meta">
                    <span>${flashEscapeHtml(artifactName)}</span>
                    ${flashJobStatusBadge(job)}
                </span>
            </button>
        `;
    }).join("");
}

async function loadFlashJobs() {
    const list = document.getElementById("flashJobsList");
    if (list) list.innerHTML = '<div class="empty-state">加载构建记录...</div>';

    try {
        flashJobs = (await apiGet("/api/jobs")).filter(isEspFirmwareJob);
        renderFlashJobs();

        const refreshed = currentJobId
            ? flashJobs.find((job) => job.job_id === currentJobId && job.status === "success" && job.download_url)
            : null;
        const defaultJob = refreshed || flashJobs.find((job) => job.status === "success" && job.download_url);

        if (defaultJob) {
            selectFlashJob(defaultJob.job_id);
        }
    } catch (err) {
        if (list) list.innerHTML = `<div class="empty-state failed">加载构建记录失败：${flashEscapeHtml(err.message)}</div>`;
        setFlashStatus(`加载构建记录失败\n${err.message}`, "failed");
        updateFlashButtonState();
    }
}

async function refreshSerialPorts() {
    const select = document.getElementById("serialPort");

    try {
        setFlashStatus("正在从本地 Agent 获取串口列表...");
        const data = await localAgentGet("/api/serial_ports");
        select.innerHTML = "";

        if (!data.ports || data.ports.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "未发现可用串口";
            select.appendChild(opt);
            select.dispatchEvent(new Event("change", { bubbles: true }));
            setFlashStatus("未自动发现串口，请确认设备连接后重新刷新串口。", "failed");
            return;
        }

        data.ports.forEach((port) => {
            const opt = document.createElement("option");
            opt.value = port.device;
            opt.textContent = `${port.device} - ${port.description}`;
            select.appendChild(opt);
        });

        const defaultPort = data.default_port || data.ports[0].device;
        select.value = defaultPort;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        setFlashStatus([
            `串口刷新成功，当前选择: ${defaultPort}`,
            currentDownloadUrl ? `已选择固件: ${currentDownloadUrl}` : "请先选择一个构建。"
        ].join("\n"), currentDownloadUrl ? "success" : "");
    } catch (err) {
        setFlashStatus([
            "刷新串口失败",
            err.message,
            "",
            "请确认本地 Agent 正在运行: http://127.0.0.1:8765"
        ].join("\n"), "failed");
    }
}

async function flashFirmware() {
    if (!currentDownloadUrl) {
        setFlashStatus("没有可烧录的固件，请先选择一个成功构建。", "failed");
        return;
    }

    const flashBtn = document.getElementById("flashBtn");
    flashBtn.disabled = true;

    const comPort = document.getElementById("serialPort").value.trim();
    if (!comPort) {
        setFlashStatus("请选择一个可用串口后再烧录。", "failed");
        flashBtn.disabled = false;
        return;
    }
    const baud = parseInt(document.getElementById("flashBaud").value || "460800", 10);
    const chip = document.getElementById("flashChip").value.trim() || "esp32s3";

    setFlashStatus([
        "开始烧录",
        `构建: ${currentJobId || "-"}`,
        `固件: ${currentDownloadUrl}`,
        `串口: ${comPort}`,
        `波特率: ${baud}`,
        `芯片: ${chip}`
    ].join("\n"));
    document.getElementById("flashLogBox").textContent = "正在下载固件并调用 esptool，请稍候...";

    try {
        const data = await localAgentPostJson("/api/flash_from_artifact", { artifact_url: currentDownloadUrl, com_port: comPort, baud, chip });
        setFlashStatus([
            "烧录成功",
            `构建: ${currentJobId || "-"}`,
            `串口: ${data.com_port}`,
            `波特率: ${data.baud}`
        ].join("\n"), "success");
        document.getElementById("flashLogBox").textContent = data.log || "Flash success";
    } catch (err) {
        setFlashStatus(`烧录失败\n${err.message}`, "failed");
        document.getElementById("flashLogBox").textContent = err.message;
    } finally {
        updateFlashButtonState();
    }
}

document.addEventListener("DOMContentLoaded", () => {
    loadFlashJobs();
});
