"use strict";

const assert = require("assert");
const fs = require("fs");

const html = fs.readFileSync(process.argv[2], "utf8");
const css = fs.readFileSync(process.argv[3], "utf8");

assert.strictEqual(
    (html.match(/class="lvgl-workbench-column /g) || []).length,
    2
);

const primaryStart = html.indexOf("lvgl-workbench-primary");
const secondaryStart = html.indexOf("lvgl-workbench-secondary");
const preview = html.indexOf("<h2>2. Preview</h2>");
const encoder = html.indexOf("<h2>3. Encoder Input</h2>");
const mock = html.indexOf("<h2>4. Mock Data</h2>");
const actions = html.indexOf("<h2>5. Actions</h2>");

assert(primaryStart >= 0);
assert(secondaryStart > primaryStart);
assert(preview > primaryStart && preview < encoder);
assert(encoder < secondaryStart);
assert(mock > secondaryStart && mock < actions);
assert(html.includes('id="lvglPreviewGate"'));
assert(html.includes('id="lvglPreviewFrame" title="LVGL UI Preview" scrolling="no"'));
assert(html.includes('id="lvglMockContent" aria-hidden="true" inert'));
assert(html.includes('id="lvglEncoderContent" aria-hidden="true" inert'));

assert(css.includes(".lvgl-workbench-column"));
assert(css.includes("grid-template-columns: minmax(0, 1.15fr)"));
assert(css.includes("@media (max-width: 860px)"));
assert(css.includes(".preview-frame-wrap iframe::-webkit-scrollbar"));
