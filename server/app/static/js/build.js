let remoteWorkspaces = [];
let idfImageConfig = {
    default_idf_image: "espressif/idf:v6.0.1",
    allowed_idf_images: ["espressif/idf:v6.0.1"],
    allow_custom: true,
};

function uniqueValues(values) {
    const seen = new Set();
    return values.filter((value) => {
        const item = String(value || "").trim();
        if (!item || seen.has(item)) return false;
        seen.add(item);
        return true;
    });
}

function selectedWorkspace() {
    const workspaceId = document.getElementById("remoteWorkspace")?.value;
    return remoteWorkspaces.find((workspace) => workspace.workspace_id === workspaceId) || null;
}

function currentIdfImageOptions() {
    const sourceMode = document.getElementById("sourceMode").value;
    const workspace = sourceMode === "remote_workspace" ? selectedWorkspace() : null;
    const workspaceImages = Array.isArray(workspace?.idf_images) ? workspace.idf_images : [];
    const values = workspaceImages.length
        ? workspaceImages
        : idfImageConfig.allowed_idf_images;
    return uniqueValues(values);
}

function handleSourceModeChange() {
    const sourceMode = document.getElementById("sourceMode").value;
    const isRemoteWorkspace = sourceMode === "remote_workspace";
    document.getElementById("remoteWorkspaceField").style.display = isRemoteWorkspace ? "grid" : "none";
    document.querySelectorAll(".local-upload-field").forEach((field) => {
        field.style.display = isRemoteWorkspace ? "none" : "grid";
    });
    renderIdfImageOptions();
}

function handleIdfImageChange() {
    const select = document.getElementById("idfImageSelect");
    const custom = document.getElementById("idfImageCustom");
    const isCustom = select.value === "__custom__";
    custom.style.display = isCustom ? "block" : "none";
    if (isCustom && !custom.value.trim()) {
        custom.value = idfImageConfig.default_idf_image || "espressif/idf:v6.0.1";
    }
}

function getSelectedIdfImage() {
    const select = document.getElementById("idfImageSelect");
    if (select.value === "__custom__") {
        const custom = document.getElementById("idfImageCustom").value.trim();
        if (!custom) throw new Error("请输入 ESP-IDF Docker 镜像");
        return custom;
    }
    return select.value;
}

function renderIdfImageOptions(preferredValue = "") {
    const select = document.getElementById("idfImageSelect");
    const custom = document.getElementById("idfImageCustom");
    const hint = document.getElementById("idfImageHint");
    const previousValue = preferredValue || getSelectedIdfImageSafe();
    const images = currentIdfImageOptions();

    select.innerHTML = "";
    images.forEach((image) => {
        const opt = document.createElement("option");
        opt.value = image;
        opt.textContent = image.replace("espressif/idf:", "ESP-IDF ");
        select.appendChild(opt);
    });

    if (idfImageConfig.allow_custom) {
        const opt = document.createElement("option");
        opt.value = "__custom__";
        opt.textContent = "自定义 Docker 镜像";
        select.appendChild(opt);
    }

    const defaultValue = images.includes(idfImageConfig.default_idf_image)
        ? idfImageConfig.default_idf_image
        : images[0];

    if (images.includes(previousValue)) {
        select.value = previousValue;
    } else if (idfImageConfig.allow_custom && previousValue) {
        select.value = "__custom__";
        custom.value = previousValue;
    } else if (defaultValue) {
        select.value = defaultValue;
    }

    hint.textContent = idfImageConfig.allow_custom
        ? "可选择预设版本，也可输入完整 Docker 镜像名。"
        : "只能选择服务器允许的 ESP-IDF Docker 镜像。";
    handleIdfImageChange();
    if (typeof refreshCustomSelect === "function") {
        refreshCustomSelect(select);
    }
}

function getSelectedIdfImageSafe() {
    try {
        return getSelectedIdfImage();
    } catch {
        return idfImageConfig.default_idf_image || "espressif/idf:v6.0.1";
    }
}

function renderWorkspaces(workspaces) {
    const select = document.getElementById("remoteWorkspace");
    const hint = document.getElementById("remoteWorkspaceHint");
    select.innerHTML = "";

    if (!workspaces.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "未配置可用远端工作区";
        select.appendChild(opt);
        hint.textContent = "远端 Server 当前没有返回可用工作区，请检查 server/config/workspaces.json。";
        renderIdfImageOptions();
        return;
    }

    workspaces.forEach((workspace) => {
        const opt = document.createElement("option");
        opt.value = workspace.workspace_id;
        opt.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.target || "unknown"})`;
        opt.dataset.projectName = workspace.project_name || "";
        opt.dataset.idfImage = workspace.idf_image || "";
        opt.dataset.target = workspace.target || "";
        select.appendChild(opt);
    });

    select.onchange = () => renderIdfImageOptions(select.selectedOptions[0]?.dataset.idfImage || "");
    hint.textContent = "远端固定工作区构建会直接使用服务器白名单路径，不会读取 Windows 本地工程路径。";
    renderIdfImageOptions(select.selectedOptions[0]?.dataset.idfImage || "");
}

async function loadIdfImages() {
    try {
        idfImageConfig = await apiGet("/api/idf-images");
        renderIdfImageOptions(idfImageConfig.default_idf_image);
    } catch (err) {
        document.getElementById("idfImageHint").textContent = `加载 IDF 版本列表失败: ${err.message}`;
        renderIdfImageOptions();
    }
}

async function loadWorkspaces() {
    try {
        const data = await apiGet("/api/workspaces");
        remoteWorkspaces = data.workspaces || [];
        renderWorkspaces(remoteWorkspaces);
    } catch (err) {
        remoteWorkspaces = [];
        renderWorkspaces([]);
        document.getElementById("remoteWorkspaceHint").textContent = `加载远端工作区失败: ${err.message}`;
    }
}

async function startBuild() {
            const startBtn = document.getElementById("startBtn");
            const flashBtn = document.getElementById("flashBtn");
            const sourceMode = document.getElementById("sourceMode").value;

            startBtn.disabled = true;
            if (flashBtn) flashBtn.disabled = true;
            stopPolling();

            currentJobId = null;
            currentDownloadUrl = null;
            currentJob = null;
            currentManifestUrl = null;
            document.getElementById("jobIdCard").textContent = "starting";
            setText("flashLogBox", "暂无烧录日志。");
            setLinks(null, null);

            try {
                let resp;
                let successMessage;

                if (sourceMode === "remote_workspace") {
                    const workspaceId = document.getElementById("remoteWorkspace").value;
                    if (!workspaceId) {
                        throw new Error("请选择可用的远端工作区");
                    }
                    const idfImage = getSelectedIdfImage();

                    document.getElementById("buildLogBox").textContent = "准备调用远端工作区构建接口...";
                    setBuildStatus("正在请求远端 Server 直接从固定工作区构建...");

                    resp = { ok: true, json: async () => await apiPostJson("/api/build/workspace", { workspace_id: workspaceId, idf_image: idfImage }) };
                    successMessage = "远端工作区构建已启动，开始轮询远端构建状态...";
                } else {
                    document.getElementById("buildLogBox").textContent = "准备调用本地 Agent...";
                    setBuildStatus("正在请求本地 Agent 压缩源码并上传到远端服务器...");

                    const payload = {
                        project_path: document.getElementById("projectPath").value.trim(),
                        project_name: document.getElementById("projectName").value.trim(),
                        idf_image: getSelectedIdfImage(),
                        target: document.getElementById("target").value
                    };

                    resp = { ok: true, json: async () => await localAgentPostJson("/api/build_from_path", payload) };
                    successMessage = "源码已上传，开始轮询远端构建状态...";
                }

                if (!resp.ok) {
                    throw new Error(await parseErrorResponse(resp));
                }

                const data = await resp.json();
                currentJobId = sourceMode === "remote_workspace"
                    ? data.job_id
                    : data.remote_response?.job_id;

                if (!currentJobId) {
                    throw new Error(sourceMode === "remote_workspace"
                        ? "远端 Server 返回中缺少 job_id"
                        : "本地 Agent 返回中缺少 remote_response.job_id");
                }

                document.getElementById("jobIdCard").textContent = currentJobId;
                setBuildStatus([
                    successMessage,
                    `Job ID: ${currentJobId}`
                ].join("\n"));

                await pollJob();
                pollTimer = setInterval(pollJob, 3000);
            } catch (err) {
                setBuildStatus(`启动构建失败\n${err.message}`, "failed");
                document.getElementById("jobIdCard").textContent = "error";
                startBtn.disabled = false;
            }
        }

async function pollJob() {
            if (!currentJobId) return;

            try {
                const job = await apiGet("/api/jobs/" + currentJobId);
                currentJob = job;
                document.getElementById("jobIdCard").textContent = job.job_id;
                setBuildStatus([
                    `Job ID: ${job.job_id}`,
                    `状态: ${job.status}`,
                    `消息: ${job.message}`,
                    `项目: ${job.project_name}`,
                    `Target: ${job.target}`,
                    `IDF Image: ${job.idf_image}`
                ].join("\n"), job.status === "success" ? "success" : job.status === "failed" ? "failed" : "");

                refreshBuildLog();

                if (job.status === "success") {
                    stopPolling();
                    currentDownloadUrl = REMOTE_BASE + job.download_url;
                    setLinks(job.download_url, job.log_url);
                    document.getElementById("startBtn").disabled = false;
                    const flashBtnDone = document.getElementById("flashBtn");
                    if (flashBtnDone) flashBtnDone.disabled = false;
                    if (typeof refreshSerialPorts === "function") refreshSerialPorts();
                }

                if (job.status === "failed") {
                    stopPolling();
                    setLinks(null, job.log_url);
                    document.getElementById("startBtn").disabled = false;
                    const flashBtnFailed = document.getElementById("flashBtn");
                    if (flashBtnFailed) flashBtnFailed.disabled = true;
                }
            } catch (err) {
                setBuildStatus(`轮询构建状态失败\n${err.message}`, "failed");
                document.getElementById("startBtn").disabled = false;
            }
        }

async function refreshBuildLog() {
            if (!currentJobId) return;

            try {
                const text = await apiGetText("/api/logs/" + currentJobId);
                const box = document.getElementById("buildLogBox");
                box.textContent = text || "暂无构建日志。";
                box.scrollTop = box.scrollHeight;
            } catch {
            }
        }

document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("sourceMode")) {
        loadIdfImages();
        loadWorkspaces();
        handleSourceModeChange();
    }
});
