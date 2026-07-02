async function loadSettings() {
    setText("serverUrl", REMOTE_BASE);
    setText("agentUrl", LOCAL_AGENT);
    try {
        const data = await apiGet("/");
        setText("defaultProject", data.default_project || "-");
        setText("defaultTarget", data.default_target || "-");
        setText("defaultIdfImage", data.default_idf_image || "-");
    } catch (err) { setText("settingsError", err.message); }
    try {
        const data = await apiGet("/api/workspaces");
        const list = document.getElementById("workspaceList");
        list.textContent = JSON.stringify(data.workspaces || [], null, 2);
    } catch (err) { setText("workspaceList", "加载工作区失败：" + err.message); }
}
document.addEventListener("DOMContentLoaded", loadSettings);
