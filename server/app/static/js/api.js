const API_BASE = "/api/v2";

async function apiGet(path) {
    const resp = await fetch(REMOTE_BASE + API_BASE + path);
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function apiPostJson(path, body) {
    const resp = await fetch(REMOTE_BASE + API_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function apiDelete(path) {
    const resp = await fetch(REMOTE_BASE + API_BASE + path, { method: "DELETE" });
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function apiGetText(path) {
    const resp = await fetch(REMOTE_BASE + API_BASE + path);
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.text();
}

async function apiGetLogChunk(jobId, offset = 0, limit = 65536) {
    return await apiGet(`/jobs/${encodeURIComponent(jobId)}/logs?offset=${offset}&limit=${limit}`);
}

async function localAgentGet(path) {
    const resp = await fetch(LOCAL_AGENT + path);
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function localAgentPostJson(path, body) {
    const resp = await fetch(LOCAL_AGENT + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}
