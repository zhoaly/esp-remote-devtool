let settingsIdfConfig = {
    default_idf_image: ESP_FACTORY_DEFAULTS.build.idf_image,
    allowed_idf_images: [ESP_FACTORY_DEFAULTS.build.idf_image],
    allow_custom: true,
};
let settingsWorkspaces = [];

function handleSettingsSourceModeChange() {
    const mode = document.getElementById("settingBuildSourceMode")?.value;
    const field = document.getElementById("settingRemoteWorkspaceField");
    if (field) field.style.display = mode === "remote_workspace" ? "grid" : "none";
}

function handleSettingsIdfImageChange() {
    const isCustom = document.getElementById("settingIdfImage")?.value === "__custom__";
    const custom = document.getElementById("settingIdfImageCustom");
    if (custom) custom.style.display = isCustom ? "block" : "none";
}

function handleSettingsOtaChannelChange() {
    const isCustom = document.getElementById("settingOtaChannel")?.value === "custom";
    const field = document.getElementById("settingOtaCustomChannelField");
    if (field) field.style.display = isCustom ? "grid" : "none";
}

function renderSettingsWorkspaces(preferredValue = "") {
    const select = document.getElementById("settingRemoteWorkspace");
    if (!select) return;

    select.innerHTML = '<option value="">自动选择第一个可用工作区</option>';
    settingsWorkspaces.forEach((workspace) => {
        const option = document.createElement("option");
        option.value = workspace.workspace_id;
        option.textContent = `${workspace.display_name || workspace.workspace_id} (${workspace.target || "unknown"})`;
        select.appendChild(option);
    });
    if (preferredValue && settingsWorkspaces.some((workspace) => workspace.workspace_id === preferredValue)) {
        select.value = preferredValue;
    }
    refreshCustomSelect(select);
}

function renderSettingsIdfImages(preferredValue = "") {
    const select = document.getElementById("settingIdfImage");
    const custom = document.getElementById("settingIdfImageCustom");
    if (!select || !custom) return;

    const images = [];
    const seen = new Set();
    [settingsIdfConfig.default_idf_image, ...(settingsIdfConfig.allowed_idf_images || [])].forEach((image) => {
        const value = String(image || "").trim();
        if (value && !seen.has(value)) {
            seen.add(value);
            images.push(value);
        }
    });

    select.innerHTML = "";
    images.forEach((image) => {
        const option = document.createElement("option");
        option.value = image;
        option.textContent = image.replace("espressif/idf:", "ESP-IDF ");
        select.appendChild(option);
    });
    if (settingsIdfConfig.allow_custom) {
        const option = document.createElement("option");
        option.value = "__custom__";
        option.textContent = "自定义 Docker 镜像";
        select.appendChild(option);
    }

    if (images.includes(preferredValue)) {
        select.value = preferredValue;
    } else if (preferredValue && settingsIdfConfig.allow_custom) {
        select.value = "__custom__";
        custom.value = preferredValue;
    } else {
        select.value = settingsIdfConfig.default_idf_image || images[0] || "";
    }
    refreshCustomSelect(select);
    handleSettingsIdfImageChange();
}

function populateSettingsForm(settings) {
    setFormValue("settingBuildSourceMode", settings.build.source_mode);
    setFormValue("settingProjectPath", settings.build.project_path);
    setFormValue("settingProjectName", settings.build.project_name);
    setFormValue("settingTarget", settings.build.target);
    setFormValue("settingIdfImageCustom", settings.build.idf_image);
    renderSettingsWorkspaces(settings.build.remote_workspace);
    renderSettingsIdfImages(settings.build.idf_image);

    setFormValue("settingSerialPort", settings.flash.serial_port);
    setFormValue("settingFlashBaud", settings.flash.baud);
    setFormValue("settingFlashChip", settings.flash.chip);

    setFormValue("settingOtaChannel", settings.ota.channel);
    setFormValue("settingOtaCustomChannel", settings.ota.custom_channel);
    setFormValue("settingOtaVersion", settings.ota.version);
    setFormValue("settingOtaMinVersion", settings.ota.min_version);
    setFormValue("settingOtaForce", settings.ota.force);
    setFormValue("settingOtaReleaseNotes", settings.ota.release_notes);

    handleSettingsSourceModeChange();
    handleSettingsIdfImageChange();
    handleSettingsOtaChannelChange();
}

function selectedSettingsIdfImage() {
    const selected = document.getElementById("settingIdfImage").value;
    return selected === "__custom__"
        ? document.getElementById("settingIdfImageCustom").value.trim()
        : selected;
}

function collectSettingsForm() {
    return {
        build: {
            source_mode: document.getElementById("settingBuildSourceMode").value,
            remote_workspace: document.getElementById("settingRemoteWorkspace").value,
            project_path: document.getElementById("settingProjectPath").value.trim(),
            project_name: document.getElementById("settingProjectName").value.trim(),
            target: document.getElementById("settingTarget").value,
            idf_image: selectedSettingsIdfImage(),
        },
        flash: {
            serial_port: document.getElementById("settingSerialPort").value.trim(),
            baud: document.getElementById("settingFlashBaud").value.trim(),
            chip: document.getElementById("settingFlashChip").value.trim(),
        },
        ota: {
            channel: document.getElementById("settingOtaChannel").value,
            custom_channel: document.getElementById("settingOtaCustomChannel").value.trim(),
            version: document.getElementById("settingOtaVersion").value.trim(),
            min_version: document.getElementById("settingOtaMinVersion").value.trim(),
            force: document.getElementById("settingOtaForce").value,
            release_notes: document.getElementById("settingOtaReleaseNotes").value.trim(),
        },
    };
}

function validateSettings(settings) {
    if (!settings.build.project_name) return "项目名不能为空。";
    if (!settings.build.target) return "目标芯片不能为空。";
    if (!/^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$/.test(settings.build.idf_image)) {
        return "ESP-IDF Docker 镜像格式不正确。";
    }

    const baud = Number(settings.flash.baud);
    if (!Number.isInteger(baud) || baud < 9600 || baud > 3000000) {
        return "烧录波特率必须是 9600 到 3000000 之间的整数。";
    }
    if (!settings.flash.chip) return "烧录芯片型号不能为空。";

    if (settings.ota.channel === "custom" && !/^[A-Za-z0-9_.-]+$/.test(settings.ota.custom_channel)) {
        return "自定义 OTA Channel 只能包含字母、数字、下划线、点和短横线。";
    }
    const versionPattern = /^\d+\.\d+(?:\.\d+)?$/;
    if (settings.ota.version && !versionPattern.test(settings.ota.version)) {
        return "OTA 默认 Version 必须留空或使用 x.y / x.y.z 格式。";
    }
    if (settings.ota.min_version && !versionPattern.test(settings.ota.min_version)) {
        return "OTA 默认 Min Version 必须留空或使用 x.y / x.y.z 格式。";
    }
    return "";
}

function saveSettings() {
    const settings = collectSettingsForm();
    const validationError = validateSettings(settings);
    if (validationError) {
        setStatus("settingsStatus", validationError, "failed");
        return;
    }

    try {
        saveEspSettings(settings);
        setStatus("settingsStatus", "默认值已保存。重新打开对应 ESP 页面后生效。", "success");
    } catch (err) {
        setStatus("settingsStatus", `保存失败：${err.message}`, "failed");
    }
}

function restoreFactoryDefaults() {
    if (!window.confirm("确认恢复所有 ESP 页面的初始默认值？")) return;
    const defaults = resetEspSettings();
    populateSettingsForm(defaults);
    setStatus("settingsStatus", "已恢复初始默认值。", "success");
}

async function loadSettings() {
    setText("serverUrl", REMOTE_BASE);
    setText("agentUrl", LOCAL_AGENT);
    const settings = getEspSettings();
    populateSettingsForm(settings);

    const requests = await Promise.allSettled([
        apiGet("/config/esp"),
        apiGet("/workspaces?kind=esp"),
    ]);

    const errors = [];
    if (requests[0].status === "fulfilled") {
        settingsIdfConfig = requests[0].value;
        renderSettingsIdfImages(settings.build.idf_image);
    } else {
        errors.push(`IDF 版本列表：${requests[0].reason.message}`);
    }

    if (requests[1].status === "fulfilled") {
        settingsWorkspaces = requests[1].value.workspaces || [];
        renderSettingsWorkspaces(settings.build.remote_workspace);
    } else {
        errors.push(`远端工作区：${requests[1].reason.message}`);
    }

    if (errors.length) {
        setStatus("settingsStatus", `设置已加载，但部分服务器配置获取失败：\n${errors.join("\n")}`, "failed");
    } else {
        setStatus("settingsStatus", "设置已加载。修改后请点击“保存默认值”。");
    }
}

document.addEventListener("DOMContentLoaded", loadSettings);
