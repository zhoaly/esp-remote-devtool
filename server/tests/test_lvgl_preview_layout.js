"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function makeClassList() {
    const values = new Set();
    return {
        toggle: function(name, enabled) {
            if(enabled) values.add(name);
            else values.delete(name);
        },
        contains: function(name) {
            return values.has(name);
        }
    };
}

const workbench = {classList: makeClassList()};
const wrap = {
    classList: makeClassList(),
    closest: function() {
        return workbench;
    }
};
let strippedFrames = 0;
const context = {
    console: console,
    URLSearchParams: URLSearchParams,
    REMOTE_BASE: "http://example.test",
    document: {
        addEventListener: function() {},
        getElementById: function(id) {
            return id === "lvglPreviewWrap" ? wrap : null;
        }
    },
    window: {
        location: {search: "", origin: "http://example.test"},
        addEventListener: function() {}
    },
    stripEmscriptenChrome: function() {
        strippedFrames++;
    }
};

vm.createContext(context);
vm.runInContext(
    fs.readFileSync(process.argv[2], "utf8"),
    context,
    {filename: process.argv[2]}
);

const declaredWorkspaceFrame = {
    contentDocument: {
        documentElement: {dataset: {lvglPreviewLayout: "workspace"}},
        querySelector: function() { return null; }
    }
};
assert.strictEqual(
    context.detectLvglPreviewFrameMode(declaredWorkspaceFrame),
    "workspace"
);

const discoveredWorkspaceFrame = {
    contentDocument: {
        documentElement: {dataset: {}},
        querySelector: function() { return {}; }
    }
};
assert.strictEqual(
    context.detectLvglPreviewFrameMode(discoveredWorkspaceFrame),
    "workspace"
);

const declaredDeviceFrame = {
    contentDocument: {
        documentElement: {dataset: {lvglPreviewLayout: "device"}},
        querySelector: function() { return {}; }
    }
};
assert.strictEqual(
    context.detectLvglPreviewFrameMode(declaredDeviceFrame),
    "device"
);

const legacyFrame = {
    contentDocument: {
        documentElement: {dataset: {}},
        querySelector: function() { return null; }
    }
};
assert.strictEqual(context.detectLvglPreviewFrameMode(legacyFrame), "device");
assert.strictEqual(context.detectLvglPreviewProtocol(legacyFrame), false);
assert.strictEqual(
    context.detectLvglPreviewProtocol(declaredDeviceFrame),
    false
);

assert.strictEqual(
    context.configureLvglPreviewFrame(declaredWorkspaceFrame),
    "workspace"
);
assert(wrap.classList.contains("workspace-preview"));
assert(workbench.classList.contains("workspace-preview-active"));
assert.strictEqual(strippedFrames, 0);

assert.strictEqual(context.configureLvglPreviewFrame(legacyFrame), "device");
assert(!wrap.classList.contains("workspace-preview"));
assert(!workbench.classList.contains("workspace-preview-active"));
assert.strictEqual(strippedFrames, 1);

assert.strictEqual(
    context.configureLvglPreviewFrame(declaredDeviceFrame),
    "device"
);
assert.strictEqual(strippedFrames, 2);
