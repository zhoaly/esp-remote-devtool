async function apiGet(path) {
    const resp = await fetch(REMOTE_BASE + path);
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function apiPostJson(path, body) {
    const resp = await fetch(REMOTE_BASE + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.json();
}

async function apiGetText(path) {
    const resp = await fetch(REMOTE_BASE + path);
    if (!resp.ok) throw new Error(await parseErrorResponse(resp));
    return await resp.text();
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
