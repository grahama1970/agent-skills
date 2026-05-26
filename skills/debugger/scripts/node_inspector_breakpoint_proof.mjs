#!/usr/bin/env node
import inspector from 'node:inspector';
import { writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import path from 'node:path';

function parseArgs(argv) {
  const args = { locals: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const item = argv[index];
    if (item === '--file') args.file = argv[++index];
    else if (item === '--line') args.line = Number(argv[++index]);
    else if (item === '--function') args.functionName = argv[++index];
    else if (item === '--arg') args.functionArg = Number(argv[++index]);
    else if (item === '--local') args.locals.push(argv[++index]);
    else if (item === '--out') args.out = argv[++index];
    else throw new Error(`unknown argument: ${item}`);
  }
  for (const required of ['file', 'line', 'functionName', 'out']) {
    if (!args[required]) throw new Error(`missing --${required}`);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const session = new inspector.Session();
session.connect();

const post = (method, params = {}) =>
  new Promise((resolve, reject) => {
    session.post(method, params, (error, result) => {
      if (error) reject(error);
      else resolve(result);
    });
  });

const source = path.resolve(args.file);
const sourceUrl = pathToFileURL(source).href;
const proof = {
  adapter: 'Node inspector',
  breakpoint: { file: source, line: args.line },
  hit_breakpoint: false,
  locals: {},
  proofAssessment: {
    requestedLocals: args.locals,
    capturedLocals: [],
    missingLocals: args.locals,
    variableInspectionValid: false,
    reason: 'runtime state was not captured',
  },
};

try {
  await post('Runtime.enable');
  await post('Debugger.enable');
  const paused = new Promise((resolve) => session.once('Debugger.paused', resolve));
  await post('Debugger.setBreakpointByUrl', {
    url: sourceUrl,
    lineNumber: args.line - 1,
    columnNumber: 0,
  });

  const module = await import(sourceUrl);
  if (typeof module[args.functionName] !== 'function') {
    throw new Error(`exported function not found: ${args.functionName}`);
  }
  const pausedPromise = paused.then(async ({ params }) => {
    const frame = params.callFrames[0];
    proof.top_frame = {
      url: frame.url,
      line: frame.location.lineNumber + 1,
      functionName: frame.functionName,
    };
    proof.hit_breakpoint = proof.top_frame.line === args.line;
    const localScope = frame.scopeChain.find((scope) => scope.type === 'local');
    if (!localScope?.object?.objectId) {
      throw new Error('paused frame did not expose a local scope');
    }
    const properties = await post('Runtime.getProperties', {
      objectId: localScope.object.objectId,
      ownProperties: true,
    });
    for (const property of properties.result ?? []) {
      if (args.locals.includes(property.name)) {
        proof.locals[property.name] = property.value?.value ?? property.value?.description ?? '';
      }
    }
    const captured = args.locals.filter((name) => Object.hasOwn(proof.locals, name));
    const missing = args.locals.filter((name) => !Object.hasOwn(proof.locals, name));
    proof.proofAssessment = {
      requestedLocals: args.locals,
      capturedLocals: captured,
      missingLocals: missing,
      variableInspectionValid: proof.hit_breakpoint && captured.length > 0 && missing.length === 0,
      reason:
        proof.hit_breakpoint && captured.length > 0 && missing.length === 0
          ? 'captured all requested TypeScript runtime state'
          : 'requested TypeScript runtime state was missing',
    };
    try {
      await post('Debugger.resume');
    } catch {
      // Self-inspection may auto-resume after the paused callback; the proof has already been captured.
    }
  });
  proof.result = module[args.functionName](args.functionArg);
  await pausedPromise;
  proof.analysis =
    'TypeScript E2E set a Node inspector breakpoint, stopped in the TypeScript source, and captured selected paused locals.';
} finally {
  session.disconnect();
  await writeFile(args.out, `${JSON.stringify(proof, null, 2)}\n`, 'utf8');
  console.log(args.out);
  console.log(JSON.stringify(proof, null, 2));
}

if (!proof.hit_breakpoint || !proof.proofAssessment.variableInspectionValid) {
  process.exit(1);
}
