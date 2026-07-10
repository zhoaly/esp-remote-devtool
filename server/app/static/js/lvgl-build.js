let lvglWorkspaces = [];

function lvglSetStatus(text, type = "") {
    setStatus("lvglStatusBox", text, type);
}

function lvglDimension(id, fallback) {
    const value = parseInt(document.getElementById(id)?.value || String(fallback), 10);
    if (!Number.isFinite(value) || value < 120 || value > 4096) {
        throw new Error("Preview dimensions must be between 120 and 4096.");
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
    const localMode = document.getElementById("lvglLocalBuildMode")?.value || "ui_package";
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
    document.getElementById("lvglWidth").value = workspace.width || 480;
    document.getElementById("lvglHeight").value = workspace.height || 480;
    document.getElementById("lvglVersion").value = workspace.lvgl_version || "9.x";
}

function renderLvglWorkspaces(workspaces) {
    const select = document.getElementById("lvglRemoteWorkspace");
    const hint = document.getElementById("lvglRemoteWorkspaceHint");
    select.innerHTML = "";

    if (!workspaces.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "No LVGL workspaces configured";
        select.appendChild(opt);
        hint.textContent = "Add project_type lvgl or lvgl_simulator entries in server/config/workspaces.json.";
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
    hint.textContent = "Remote workspace builds use server-side allowlisted paths only.";
    applyLvglWorkspaceDefaults(workspaces[0]);
    if (typeof refreshCustomSelect === "function") refreshCustomSelect(select);
}

async function loadLvglWorkspaces() {
    try {
        const data = await apiGet("/api/lvgl/workspaces");
        lvglWorkspaces = data.workspaces || [];
        const widthInput = document.getElementById("lvglWidth");
        const heightInput = document.getElementById("lvglHeight");
        const versionInput = document.getElementById("lvglVersion");
        if (!widthInput.value) widthInput.value = data.default_width || 480;
        if (!heightInput.value) heightInput.value = data.default_height || 480;
        if (!versionInput.value) versionInput.value = data.default_lvgl_version || "9.x";
        renderLvglWorkspaces(lvglWorkspaces);
    } catch (err) {
        lvglWorkspaces = [];
        renderLvglWorkspaces([]);
        document.getElementById("lvglRemoteWorkspaceHint").textContent = `Failed to load LVGL workspaces: ${err.message}`;
    }
}

function setLvglLinks(job) {
    const area = document.getElementById("lvglLinkArea");
    if (!area) return;
    area.innerHTML = "";

    if (job?.preview_url) {
        const preview = document.createElement("a");
        preview.href = lvglPreviewPageUrl(job.job_id);
        preview.textContent = "Open in preview page";
        area.appendChild(preview);
    }

    if (job?.artifact_url || job?.download_url) {
        const artifact = document.createElement("a");
        artifact.href = REMOTE_BASE + (job.artifact_url || job.download_url);
        artifact.target = "_blank";
        artifact.textContent = "Download preview package";
        area.appendChild(artifact);
    }

    if (job?.log_url) {
        const log = document.createElement("a");
        log.href = REMOTE_BASE + job.log_url;
        log.target = "_blank";
        log.textContent = "Open full log";
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
    setText("lvglJobIdCard", "starting");

    try {
        const width = lvglDimension("lvglWidth", 480);
        const height = lvglDimension("lvglHeight", 480);

        let data;
        if (sourceMode === "remote_workspace") {
            const workspaceId = document.getElementById("lvglRemoteWorkspace").value;
            if (!workspaceId) throw new Error("Select an available LVGL remote workspace.");
            lvglSetStatus("Requesting remote workspace build...");
            data = await apiPostJson("/api/lvgl/build/workspace", {
                workspace_id: workspaceId,
                project_name: document.getElementById("lvglProjectName").value.trim(),
                width,
                height,
            });
        } else {
            const projectPath = document.getElementById("lvglProjectPath").value.trim();
            if (!projectPath) throw new Error("Enter a Windows local LVGL project path.");
            const localMode = document.getElementById("lvglLocalBuildMode").value;
            const projectName = document.getElementById("lvglProjectName").value.trim() || "lvgl_project";
            let agentResp;

            if (localMode === "ui_package") {
                lvglSetStatus("Asking Local Agent to upload LVGL UI sources...");
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
                lvglSetStatus("Asking Local Agent to upload the full LVGL web project...");
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
        if (!currentJobId) throw new Error("Remote build API did not return job_id.");

        setText("lvglJobIdCard", currentJobId);
        lvglSetStatus(`LVGL build started\nJob ID: ${currentJobId}`);
        await pollLvglJob();
        pollTimer = setInterval(pollLvglJob, 3000);
    } catch (err) {
        lvglSetStatus(`Failed to start LVGL build\n${err.message}`, "failed");
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
            `Status: ${job.status}`,
            `Message: ${job.message || "-"}`,
            `Project: ${job.project_name || "-"}`,
            `Size: ${job.width || "-"} x ${job.height || "-"}`,
            `Source: ${job.source_mode || "-"}`
        ].join("\n"), job.status === "success" ? "success" : job.status === "failed" ? "failed" : "");

        await refreshLvglLog();
        setLvglLinks(job);

        if (job.status === "success" || job.status === "failed") {
            stopPolling();
            document.getElementById("lvglStartBtn").disabled = false;
        }
    } catch (err) {
        lvglSetStatus(`Failed to poll LVGL build status\n${err.message}`, "failed");
        document.getElementById("lvglStartBtn").disabled = false;
    }
}

async function refreshLvglLog() {
    if (!currentJobId) return;

    try {
        const text = await apiGetText("/api/lvgl/logs/" + currentJobId);
        const box = document.getElementById("lvglLogBox");
        box.textContent = text || "No build log yet.";
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
