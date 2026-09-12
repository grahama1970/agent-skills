#!/usr/bin/env node
// Syntax oracle for pi-subagents workflowScript bodies (top-level await + return).
const fs = require('fs');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const body = fs.readFileSync(process.argv[2], 'utf8');
new AsyncFunction('runs', 'emit', 'console', 'mission', body);
console.log('workflow-syntax-ok');
