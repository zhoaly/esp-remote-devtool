"use strict";

const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

const apiSource = fs.readFileSync(process.argv[2], "utf8");
const buildSource = fs.readFileSync(process.argv[3], "utf8");
const jobsSource = fs.readFileSync(process.argv[4], "utf8");
const lvglJobsSource = fs.readFileSync(process.argv[5], "utf8");
const requested = [];
const context = {
    REMOTE_BASE: "https://build.example",
    fetch: async function(url) {
        requested.push(url);
        return {
            ok: true,
            json: async function() {
                return {content: "next", next_offset: 16, complete: false};
            }
        };
    }
};

vm.createContext(context);
vm.runInContext(apiSource, context, {filename: process.argv[2]});

(async function() {
    const chunk = await context.apiGetLogChunk("job id", 12, 4);
    assert.deepStrictEqual(
        requested,
        ["https://build.example/api/v2/jobs/job%20id/logs?offset=12&limit=4"]
    );
    assert.strictEqual(chunk.content, "next");
    assert.strictEqual(chunk.next_offset, 16);
    assert.strictEqual(chunk.complete, false);

    assert(buildSource.includes('job.status === "succeeded"'));
    assert(buildSource.includes("apiGetLogChunk(currentJobId, buildLogOffset)"));
    assert(!buildSource.includes("job.job_id"));
    assert(jobsSource.includes("cell.textContent"));
    assert(!jobsSource.includes("innerHTML"));
    assert(lvglJobsSource.includes("cell.textContent"));
    assert(!lvglJobsSource.includes("innerHTML"));
})().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});
