let lvglWorkspaces = [];
let currentLvglPreviewUrl = null;

function lvglSetStatus(text, type = "") {
    setStatus("lvglStatusBox", text, type);
}

function lvglDimension(id, fallback) {
    const value = parseInt(document.getElementById(id)?.value || String(fallback), 10);
    if (!Number.isFinite(value) || value < 120 || value > 4096) {
        throw new Error("预览尺寸必须在 120 到 4096 之间。");
    }
    return value;
}

function selectedLvglWorkspace() {
    const workspaceId = document.getElementById("lvglRemoteWorkspace")?.value;
    return lvglWorkspaces.find((workspace) => workspace.workspace_id === workspaceId) || null;
}

function handleLvglSourceModeChange() {
    const sourceMode = document.getElementById("lvglSourceMode").value;
    const isRemoteWorkspace = sourceMode === "remote_workspace";
    document.getElementById("lvglRemoteWorkspaceField").style.display = isRemoteWorkspace ? "grid" : "none";
    document.querySelectorAll(".lvgl-local-field").forEach((field) => {
        field.style.display = isRemoteWorkspace ? "none" : "grid";
    });

    const workspace = selectedLvglWorkspace();
    if (isRemoteWorkspace && workspace) {
        applyLvglWorkspaceDefaults(workspace);
    }
}

function applyLvglWorkspaceDefaults(workspace) {
    if (!workspace) return;
    document.getElementById("lvglProjectName").value = workspace.project_name || workspace.workspace_id || "lvgl_project";
    document.getElementById("lvglWidth").value = workspace.width || 480;
    document.getElementById("lvglHeight").value = workspace.height || 480;
    document.getElementById("lvglVersion").value = workspace.lvgl_version || "9.x";
    updateLvglPreviewSize();
}

function updateLvglPreviewSize() {
    const width = document.getElementById("lvglWidth")?.value || "480";
    const height = document.getElementById("lvglHeight")?.value || "480";
    setText("lvglPreviewSize", `${width} x ${height}`);
}

function renderLvglWorkspaces(workspaces) {
    const select = document.getElementById("lvglRemoteWorkspace");
    const hint = document.getElementById("lvglRemoteWorkspaceHint");
    select.innerHTML = "";

    if (!workspaces.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "未配置可用 LVGL 工作区";
        select.appendChild(opt);
        hint.textContent = "请在 server/config/workspaces.json 中添加 project_type 为 lvgl 或 lvgl_simulator 的工作区。";
        if (typeof refreshCustomSelect === "function") refreshCustomSelect(select);
        return;
    }

    workspaces.forEach((workspace) => {
        const opt = document.createElement("option");
        opt.value = workspace.workspace_id;
        opt.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.width || 480}x${workspace.height || 480})`;
        select.appendChild(opt);
    });

    select.onchange = () => applyLvglWorkspaceDefaults(selectedLvglWorkspace());
    hint.textContent = "远端工作区构建会直接使用服务器白名单路径，不读取 Windows 本地路径。";
    applyLvglWorkspaceDefaults(workspaces[0]);
    if (typeof refreshCustomSelect === "function") refreshCustomSelect(select);
}

async function loadLvglWorkspaces() {
    try {
        const data = await apiGet("/api/lvgl/workspaces");
        lvglWorkspaces = data.workspaces || [];
        document.getElementById("lvglWidth").value = data.default_width || 480;
        document.getElementById("lvglHeight").value = data.default_height || 480;
        document.getElementById("lvglVersion").value = data.default_lvgl_version || "9.x";
        renderLvglWorkspaces(lvglWorkspaces);
        updateLvglPreviewSize();
    } catch (err) {
        lvglWorkspaces = [];
        renderLvglWorkspaces([]);
        document.getElementById("lvglRemoteWorkspaceHint").textContent = `加载 LVGL 工作区失败: ${err.message}`;
    }
}

function setLvglLinks(job) {
    const area = document.getElementById("lvglLinkArea");
    if (!area) return;
    area.innerHTML = "";

    if (job?.preview_url) {
        const preview = document.createElement("a");
        preview.href = REMOTE_BASE + job.preview_url;
        preview.target = "_blank";
        preview.textContent = "打开预览";
        area.appendChild(preview);
    }

    if (job?.artifact_url || job?.download_url) {
        const artifact = document.createElement("a");
        artifact.href = REMOTE_BASE + (job.artifact_url || job.download_url);
        artifact.target = "_blank";
        artifact.textContent = "下载预览包";
        area.appendChild(artifact);
    }

    if (job?.log_url) {
        const log = document.createElement("a");
        log.href = REMOTE_BASE + job.log_url;
        log.target = "_blank";
        log.textContent = "打开完整日志";
        area.appendChild(log);
    }
}

function setLvglPreview(previewUrl) {
    currentLvglPreviewUrl = previewUrl ? REMOTE_BASE + previewUrl : null;
    const frame = document.getElementById("lvglPreviewFrame");
    const empty = document.getElementById("lvglPreviewEmpty");

    if (!currentLvglPreviewUrl) {
        frame.removeAttribute("src");
        frame.style.opacity = "0";
        empty.style.display = "grid";
        return;
    }

    frame.src = `${currentLvglPreviewUrl}?t=${Date.now()}`;
    frame.style.opacity = "1";
    empty.style.display = "none";
}

function reloadLvglPreview() {
    if (!currentLvglPreviewUrl) {
        lvglSetStatus("还没有可刷新的预览，请先完成一次成功构建。", "failed");
        return;
    }
    document.getElementById("lvglPreviewFrame").src = `${currentLvglPreviewUrl}?t=${Date.now()}`;
}

async function startLvglBuild() {
    const startBtn = document.getElementById("lvglStartBtn");
    const sourceMode = document.getElementById("lvglSourceMode").value;

    startBtn.disabled = true;
    stopPolling();
    currentJobId = null;
    currentJob = null;
    currentLvglPreviewUrl = null;
    setLvglPreview(null);
    setLvglLinks(null);
    setText("lvglJobIdCard", "starting");

    try {
        const width = lvglDimension("lvglWidth", 480);
        const height = lvglDimension("lvglHeight", 480);
        updateLvglPreviewSize();

        let data;
        if (sourceMode === "remote_workspace") {
            const workspaceId = document.getElementById("lvglRemoteWorkspace").value;
            if (!workspaceId) throw new Error("请选择可用的 LVGL 远端工作区。");
            lvglSetStatus("正在请求远端 Server 从固定工作区构建 LVGL WebAssembly...");
            data = await apiPostJson("/api/lvgl/build/workspace", {
                workspace_id: workspaceId,
                project_name: document.getElementById("lvglProjectName").value.trim(),
                width,
                height,
            });
        } else {
            const projectPath = document.getElementById("lvglProjectPath").value.trim();
            if (!projectPath) throw new Error("请输入 Windows 本地 LVGL 项目路径。");
            lvglSetStatus("正在请求本地 Agent 压缩 LVGL 项目并上传到远端 Server...");
            const agentResp = await localAgentPostJson("/api/lvgl/build_from_path", {
                project_path: projectPath,
                project_name: document.getElementById("lvglProjectName").value.trim() || "lvgl_project",
                width,
                height,
            });
            data = agentResp.remote_response || {};
        }

        currentJobId = data.job_id;
        if (!currentJobId) throw new Error("远端构建接口没有返回 job_id。");

        setText("lvglJobIdCard", currentJobId);
        lvglSetStatus(`LVGL 构建已启动\nJob ID: ${currentJobId}`);
        await pollLvglJob();
        pollTimer = setInterval(pollLvglJob, 3000);
    } catch (err) {
        lvglSetStatus(`启动 LVGL 构建失败\n${err.message}`, "failed");
        setText("lvglJobIdCard", "error");
        startBtn.disabled = false;
    }
}

async function pollLvglJob() {
    if (!currentJobId) return;

    try {
        const job = await apiGet("/api/lvgl/jobs/" + currentJobId);
        currentJob = job;
        setText("lvglJobIdCard", job.job_id);
        lvglSetStatus([
            `Job ID: ${job.job_id}`,
            `状态: ${job.status}`,
            `消息: ${job.message || "-"}`,
            `项目: ${job.project_name || "-"}`,
            `尺寸: ${job.width || "-"} x ${job.height || "-"}`,
            `来源: ${job.source_mode || "-"}`
        ].join("\n"), job.status === "success" ? "success" : job.status === "failed" ? "failed" : "");

        await refreshLvglLog();
        setLvglLinks(job);

        if (job.status === "success") {
            stopPolling();
            setLvglPreview(job.preview_url);
            document.getElementById("lvglStartBtn").disabled = false;
        }

        if (job.status === "failed") {
            stopPolling();
            document.getElementById("lvglStartBtn").disabled = false;
        }
    } catch (err) {
        lvglSetStatus(`轮询 LVGL 构建状态失败\n${err.message}`, "failed");
        document.getElementById("lvglStartBtn").disabled = false;
    }
}

async function refreshLvglLog() {
    if (!currentJobId) return;

    try {
        const text = await apiGetText("/api/lvgl/logs/" + currentJobId);
        const box = document.getElementById("lvglLogBox");
        box.textContent = text || "暂无构建日志。";
        box.scrollTop = box.scrollHeight;
    } catch {
    }
}

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("lvglSourceMode")) return;
    loadLvglWorkspaces();
    handleLvglSourceModeChange();
    updateLvglPreviewSize();
    document.getElementById("lvglWidth").addEventListener("input", updateLvglPreviewSize);
    document.getElementById("lvglHeight").addEventListener("input", updateLvglPreviewSize);
});
