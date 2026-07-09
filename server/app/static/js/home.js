function createTag(text, className = "") {
    const tag = document.createElement("span");
    tag.className = className ? `tag ${className}` : "tag";
    tag.textContent = text;
    return tag;
}

function createToolAction(action) {
    const href = String(action.href || "");
    const label = String(action.label || href || "打开");
    const link = document.createElement("a");
    link.className = action.primary ? "tool-action primary-action" : "tool-action";
    link.textContent = label;

    if (href) {
        link.href = href;
    } else {
        link.href = "#";
        link.classList.add("disabled");
        link.setAttribute("aria-disabled", "true");
        link.addEventListener("click", (event) => event.preventDefault());
    }

    return link;
}

function createToolCard(tool) {
    const href = String(tool.href || "");
    const card = document.createElement("div");
    card.className = "tool-card";
    if (href) {
        card.tabIndex = 0;
        card.setAttribute("role", "link");
        card.addEventListener("click", (event) => {
            if (event.target instanceof Element && event.target.closest("a")) return;
            window.location.href = href;
        });
        card.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                window.location.href = href;
            }
        });
    } else {
        card.classList.add("disabled");
    }

    const head = document.createElement("div");
    head.className = "tool-card-head";

    const title = document.createElement("strong");
    title.textContent = String(tool.title || tool.id || "未命名工具");
    head.appendChild(title);

    const status = String(tool.status || "available");
    const statusLabel = String(tool.status_label || status);
    head.appendChild(createTag(statusLabel, status === "available" ? "success" : ""));

    const description = document.createElement("p");
    description.textContent = String(tool.description || "");

    const features = document.createElement("div");
    features.className = "tool-features";
    const featureValues = Array.isArray(tool.features) ? tool.features : [];
    featureValues.forEach((feature) => {
        features.appendChild(createTag(String(feature)));
    });

    const actions = document.createElement("div");
    actions.className = "tool-actions";
    const actionValues = Array.isArray(tool.actions) ? tool.actions : [];
    actionValues.forEach((action) => {
        if (action && typeof action === "object") actions.appendChild(createToolAction(action));
    });

    card.append(head, description);
    if (featureValues.length) card.appendChild(features);
    if (actionValues.length) card.appendChild(actions);
    return card;
}

function renderHomeRegistry(registry) {
    setText("homeTitle", registry.title || "ZLYHUB开发工具集");
    setText("homeSubtitle", registry.subtitle || "");
    setText("homeRegistryState", "loaded");

    const root = document.getElementById("homeSections");
    if (!root) return;
    root.innerHTML = "";

    const sections = Array.isArray(registry.sections) ? registry.sections : [];
    const tools = Array.isArray(registry.tools) ? registry.tools : [];

    if (!sections.length) {
        const empty = document.createElement("section");
        empty.className = "panel";
        empty.innerHTML = '<div class="empty-state">工具注册表暂无可显示分组。</div>';
        root.appendChild(empty);
        return;
    }

    sections.forEach((section) => {
        const sectionId = String(section.id || "");
        const sectionTools = tools.filter((tool) => String(tool.section_id || "") === sectionId);
        if (!sectionTools.length) return;

        const panel = document.createElement("section");
        panel.className = "panel tool-section";

        const heading = document.createElement("div");
        heading.className = "panel-heading";

        const headingText = document.createElement("div");
        const title = document.createElement("h2");
        title.textContent = String(section.title || sectionId || "工具分组");
        const copy = document.createElement("div");
        copy.className = "section-copy";
        copy.textContent = String(section.description || "");
        headingText.append(title, copy);
        heading.appendChild(headingText);

        const grid = document.createElement("div");
        grid.className = "page-cards tool-grid";
        sectionTools.forEach((tool) => grid.appendChild(createToolCard(tool)));

        panel.append(heading, grid);
        root.appendChild(panel);
    });
}

async function loadHomeRegistry() {
    try {
        const registry = await apiGet("/api/home/tools");
        renderHomeRegistry(registry);
    } catch (err) {
        setText("homeRegistryState", "failed");
        const root = document.getElementById("homeSections");
        if (root) {
            root.innerHTML = "";
            const panel = document.createElement("section");
            panel.className = "panel";
            const empty = document.createElement("div");
            empty.className = "empty-state failed";
            empty.textContent = `工具注册表加载失败：${err.message}`;
            panel.appendChild(empty);
            root.appendChild(panel);
        }
    }
}

document.addEventListener("DOMContentLoaded", loadHomeRegistry);
