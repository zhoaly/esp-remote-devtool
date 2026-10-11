let lvglSettingsWorkspaces = [];

function handleLvglSettingsSourceModeChange() {
    const sourceMode = document.getElementById("lvglSettingSourceMode")?.value || "local_path";
    const isRemote = sourceMode === "remote_workspace";
    const remoteField = document.getElementById("lvglSettingRemoteWorkspaceField");
    if (remoteField) remoteField.style.display = isRemote ? "grid" : "none";
    document.querySelectorAll(".lvgl-settings-local-field").forEach((field) => {
        field.style.display = isRemote ? "none" : "grid";
    });
    handleLvglSettingsLocalModeChange();
}

function handleLvglSettingsLocalModeChange() {
    const sourceMode = document.getElementById("lvglSettingSourceMode")?.value || "local_path";
    const localMode = document.getElementById("lvglSettingLocalBuildMode")?.value || "full_project";
    const panel = document.querySelector(".lvgl-settings-ui-panel");
    if (panel) panel.style.display = sourceMode !== "remote_workspace" && localMode === "ui_package" ? "block" : "none";
}

function renderLvglSettingsWorkspaces(preferredValue = "") {
    const select = document.getElementById("lvglSettingRemoteWorkspace");
    if (!select) return;

    select.innerHTML = '<option value="">自动选择第一个可用工作区</option>';
    lvglSettingsWorkspaces.forEach((workspace) => {
        const option = document.createElement("option");
        option.value = workspace.workspace_id;
        option.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.width || 128}x${workspace.height || 296})`;
        select.appendChild(option);
    });
    if (preferredValue && lvglSettingsWorkspaces.some((workspace) => workspace.workspace_id === preferredValue)) {
        select.value = preferredValue;
    }
    refreshCustomSelect(select);
}

function populateLvglSettingsForm(settings) {
    const build = settings.build;
    setFormValue("lvglSettingSourceMode", build.source_mode);
    setFormValue("lvglSettingLocalBuildMode", build.local_build_mode);
    setFormValue("lvglSettingProjectPath", build.project_path);
    setFormValue("lvglSettingUiRoots", build.ui_roots);
    setFormValue("lvglSettingIncludeDirs", build.include_dirs);
    setFormValue("lvglSettingEntryHeader", build.entry_header);
    setFormValue("lvglSettingEntryCall", build.entry_call);
    setFormValue("lvglSettingProjectName", build.project_name);
    setFormValue("lvglSettingWidth", build.width);
    setFormValue("lvglSettingHeight", build.height);
    renderLvglSettingsWorkspaces(build.remote_workspace);
    handleLvglSettingsSourceModeChange();
    handleLvglSettingsLocalModeChange();
}

function collectLvglSettingsForm() {
    return {
        build: {
            source_mode: document.getElementById("lvglSettingSourceMode").value,
            remote_workspace: document.getElementById("lvglSettingRemoteWorkspace").value,
            local_build_mode: document.getElementById("lvglSettingLocalBuildMode").value,
            project_path: document.getElementById("lvglSettingProjectPath").value.trim(),
            ui_roots: document.getElementById("lvglSettingUiRoots").value.trim(),
            include_dirs: document.getElementById("lvglSettingIncludeDirs").value.trim(),
            entry_header: document.getElementById("lvglSettingEntryHeader").value.trim(),
            entry_call: document.getElementById("lvglSettingEntryCall").value.trim(),
            project_name: document.getElementById("lvglSettingProjectName").value.trim(),
            width: document.getElementById("lvglSettingWidth").value.trim(),
            height: document.getElementById("lvglSettingHeight").value.trim(),
        },
    };
}

function validateLvglSettings(settings) {
    const build = settings.build;
    if (!build.project_name) return "工程名不能为空。";

    const width = Number(build.width);
    const height = Number(build.height);
    if (!Number.isInteger(width) || width < 120 || width > 4096) {
        return "预览宽度必须是 120 到 4096 之间的整数。";
    }
    if (!Number.isInteger(height) || height < 120 || height > 4096) {
        return "预览高度必须是 120 到 4096 之间的整数。";
    }
    return "";
}

function saveLvglDefaultSettings() {
    const settings = collectLvglSettingsForm();
    const validationError = validateLvglSettings(settings);
    if (validationError) {
        setStatus("lvglSettingsStatus", validationError, "failed");
        return;
    }

    try {
        saveLvglSettings(settings);
        setStatus("lvglSettingsStatus", "LVGL 默认值已保存。重新打开远端编译页面后生效。", "success");
    } catch (err) {
        setStatus("lvglSettingsStatus", `保存失败：${err.message}`, "failed");
    }
}

function restoreLvglFactoryDefaults() {
    if (!window.confirm("确认恢复所有 LVGL 模拟器初始默认值？")) return;
    const defaults = resetLvglSettings();
    populateLvglSettingsForm(defaults);
    setStatus("lvglSettingsStatus", "已恢复 LVGL 初始默认值。", "success");
}

async function loadLvglDefaultSettings() {
    setText("lvglSettingsServerUrl", REMOTE_BASE);
    const settings = getLvglSettings();
    populateLvglSettingsForm(settings);

    try {
        const data = await apiGet("/workspaces?kind=lvgl");
        lvglSettingsWorkspaces = data.workspaces || [];
        renderLvglSettingsWorkspaces(settings.build.remote_workspace);
        setText("lvglSettingsVersion", data.default_lvgl_version || "9.x");
        setStatus("lvglSettingsStatus", "设置已加载。修改后请点击“保存默认值”。");
    } catch (err) {
        setText("lvglSettingsVersion", "-");
        setStatus("lvglSettingsStatus", `设置已加载，但服务器配置获取失败：${err.message}`, "failed");
    }
}

document.addEventListener("DOMContentLoaded", loadLvglDefaultSettings);
