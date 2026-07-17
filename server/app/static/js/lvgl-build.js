let lvglWorkspaces = [];

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
    handleLvglLocalBuildModeChange();

    const workspace = selectedLvglWorkspace();
    if (isRemoteWorkspace && workspace) {
        applyLvglWorkspaceDefaults(workspace);
    }
}

function handleLvglLocalBuildModeChange() {
    const sourceMode = document.getElementById("lvglSourceMode")?.value || "local_path";
    const localMode = document.getElementById("lvglLocalBuildMode")?.value || "full_project";
    const showUiFields = sourceMode !== "remote_workspace" && localMode === "ui_package";
    document.querySelectorAll(".lvgl-ui-field").forEach((field) => {
        field.style.display = showUiFields ? "grid" : "none";
    });
}

function splitCsv(value) {
    return String(value || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

function applyLvglWorkspaceDefaults(workspace) {
    if (!workspace) return;
    document.getElementById("lvglProjectName").value = workspace.project_name || workspace.workspace_id || "lvgl_project";
    document.getElementById("lvglWidth").value = workspace.width || 128;
    document.getElementById("lvglHeight").value = workspace.height || 296;
    document.getElementById("lvglVersion").value = workspace.lvgl_version || "9.x";
}

function renderLvglWorkspaces(workspaces) {
    const select = document.getElementById("lvglRemoteWorkspace");
    const hint = document.getElementById("lvglRemoteWorkspaceHint");
    select.innerHTML = "";

    if (!workspaces.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "尚未配置 LVGL 工作区";
        select.appendChild(opt);
        hint.textContent = "请在 server/config/workspaces.json 中添加 project_type 为 lvgl 或 lvgl_simulator 的条目。";
        if (typeof refreshCustomSelect === "function") refreshCustomSelect(select);
        return;
    }

    workspaces.forEach((workspace) => {
        const opt = document.createElement("option");
        opt.value = workspace.workspace_id;
        opt.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.width || 128}x${workspace.height || 296})`;
        select.appendChild(opt);
    });

    select.onchange = () => applyLvglWorkspaceDefaults(selectedLvglWorkspace());
    hint.textContent = "远端工作区构建只能使用服务器白名单中的路径。";
    if (document.getElementById("lvglSourceMode")?.value === "remote_workspace") {
        applyLvglWorkspaceDefaults(workspaces[0]);
    }
    if (typeof refreshCustomSelect === "function") refreshCustomSelect(select);
}

async function loadLvglWorkspaces() {
    try {
        const data = await apiGet("/api/lvgl/workspaces");
        lvglWorkspaces = data.workspaces || [];
        const widthInput = document.getElementById("lvglWidth");
        const heightInput = document.getElementById("lvglHeight");
        const versionInput = document.getElementById("lvglVersion");
        if (!widthInput.value) widthInput.value = data.default_width || 128;
        if (!heightInput.value) heightInput.value = data.default_height || 296;
        if (!versionInput.value) versionInput.value = data.default_lvgl_version || "9.x";
        renderLvglWorkspaces(lvglWorkspaces);
    } catch (err) {
        lvglWorkspaces = [];
        renderLvglWorkspaces([]);
        document.getElementById("lvglRemoteWorkspaceHint").textContent = `加载 LVGL 工作区失败：${err.message}`;
    }
}

function setLvglLinks(job) {
    const area = document.getElementById("lvglLinkArea");
    if (!area) return;
    area.innerHTML = "";

    if (job?.preview_url) {
        const preview = document.createElement("a");
        preview.href = lvglPreviewPageUrl(job.job_id);
        preview.textContent = "在预览页面打开";
        area.appendChild(preview);
    }

    if (job?.artifact_url || job?.download_url) {
        const artifact = document.createElement("a");
        artifact.href = REMOTE_BASE + (job.artifact_url || job.download_url);
        artifact.target = "_blank";
        artifact.textContent = "下载预览产物包";
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

async function startLvglBuild() {
    const startBtn = document.getElementById("lvglStartBtn");
    const sourceMode = document.getElementById("lvglSourceMode").value;

    startBtn.disabled = true;
    stopPolling();
    currentJobId = null;
    currentJob = null;
    setLvglLinks(null);
    setText("lvglJobIdCard", "启动中");

    try {
        const width = lvglDimension("lvglWidth", 128);
        const height = lvglDimension("lvglHeight", 296);

        let data;
        if (sourceMode === "remote_workspace") {
            const workspaceId = document.getElementById("lvglRemoteWorkspace").value;
            if (!workspaceId) throw new Error("请选择一个可用的 LVGL 远端工作区。");
            lvglSetStatus("正在请求远端工作区构建...");
            data = await apiPostJson("/api/lvgl/build/workspace", {
                workspace_id: workspaceId,
                project_name: document.getElementById("lvglProjectName").value.trim(),
                width,
                height,
            });
        } else {
            const projectPath = document.getElementById("lvglProjectPath").value.trim();
            if (!projectPath) throw new Error("请输入 Windows 本地 LVGL 工程路径。");
            const localMode = document.getElementById("lvglLocalBuildMode").value;
            const projectName = document.getElementById("lvglProjectName").value.trim() || "lvgl_project";
            let agentResp;

            if (localMode === "ui_package") {
                lvglSetStatus("正在请求 Local Agent 上传 LVGL UI 源码...");
                agentResp = await localAgentPostJson("/api/lvgl/build_ui_from_path", {
                    project_path: projectPath,
                    project_name: projectName,
                    width,
                    height,
                    ui_roots: splitCsv(document.getElementById("lvglUiRoots").value),
                    include_dirs: splitCsv(document.getElementById("lvglIncludeDirs").value),
                    entry_header: document.getElementById("lvglEntryHeader").value.trim(),
                    entry_call: document.getElementById("lvglEntryCall").value.trim() || "ui_init",
                });
            } else {
                lvglSetStatus("正在请求 Local Agent 上传完整 LVGL Web 工程...");
                agentResp = await localAgentPostJson("/api/lvgl/build_from_path", {
                    project_path: projectPath,
                    project_name: projectName,
                    width,
                    height,
                });
            }
            data = agentResp.remote_response || {};
        }

        currentJobId = data.job_id;
        if (!currentJobId) throw new Error("远端构建 API 未返回 job_id。");

        setText("lvglJobIdCard", currentJobId);
        lvglSetStatus(`LVGL 构建已启动\nJob ID: ${currentJobId}`);
        await pollLvglJob();
        pollTimer = setInterval(pollLvglJob, 3000);
    } catch (err) {
        lvglSetStatus(`启动 LVGL 构建失败\n${err.message}`, "failed");
        setText("lvglJobIdCard", "错误");
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
            `工程: ${job.project_name || "-"}`,
            `尺寸: ${job.width || "-"} x ${job.height || "-"}`,
            `来源: ${job.source_mode || "-"}`
        ].join("\n"), job.status === "success" ? "success" : job.status === "failed" ? "failed" : "");

        await refreshLvglLog();
        setLvglLinks(job);

        if (job.status === "success" || job.status === "failed") {
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
    handleLvglLocalBuildModeChange();
});
