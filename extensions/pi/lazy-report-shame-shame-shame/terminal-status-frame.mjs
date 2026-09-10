const STATUS_SCHEMA = 'pi.agent_status.v1';

function lineBody(line) {
  return String(line || '').replace('\r', '').replace('\n', '');
}

function fenceOpen(line) {
  const s = lineBody(line).trim();
  if (s === '```json') return { marker: '```' };
  if (s === '~~~json') return { marker: '~~~' };
  return null;
}

function fenceClose(line, marker) {
  return lineBody(line).trim() === marker;
}

function parseFrame(body) {
  try {
    return { parsed: JSON.parse(body), parse_error: null };
  } catch (error) {
    return { parsed: null, parse_error: error instanceof Error ? error.message : String(error) };
  }
}

function statusLikeFrame(frame) {
  return Boolean(frame?.parsed && frame.parsed.schema === STATUS_SCHEMA)
    || String(frame?.body || '').includes(STATUS_SCHEMA);
}

function spanFor(frame) {
  return {
    start: frame.start,
    end: frame.end,
    body_start: frame.bodyStart,
    body_end: frame.bodyEnd,
    marker: frame.marker,
  };
}

export function findJsonControlFrames(input) {
  const source = String(input || '');
  const frames = [];
  let offset = 0;
  let active = null;
  while (offset < source.length) {
    const newlineAt = source.indexOf('\n', offset);
    const lineEnd = newlineAt === -1 ? source.length : newlineAt + 1;
    const line = source.slice(offset, lineEnd);
    const start = offset;
    if (active) {
      if (fenceClose(line, active.marker)) {
        const body = source.slice(active.bodyStart, start);
        const parsed = parseFrame(body);
        frames.push({
          body,
          start: active.start,
          end: lineEnd,
          bodyStart: active.bodyStart,
          bodyEnd: start,
          marker: active.marker,
          parsed: parsed.parsed,
          parse_error: parsed.parse_error,
          span: {
            start: active.start,
            end: lineEnd,
            body_start: active.bodyStart,
            body_end: start,
            marker: active.marker,
          },
        });
        active = null;
      }
      offset = lineEnd;
      continue;
    }
    const open = fenceOpen(line);
    if (open) active = { marker: open.marker, start, bodyStart: lineEnd };
    offset = lineEnd;
  }
  return frames;
}

export function selectTerminalStatusFrame(input) {
  const frames = findJsonControlFrames(input);
  const statusFrames = frames.filter(statusLikeFrame);
  if (!statusFrames.length) {
    return {
      ok: false,
      reason_code: 'missing_agent_status_json',
      json_fence_count: frames.length,
      status_frame_count: 0,
      status_frame_spans: [],
      statusFrame: null,
      status: null,
    };
  }

  const invalidStatus = statusFrames.find((frame) => !frame.parsed);
  if (invalidStatus) {
    return {
      ok: false,
      reason_code: 'invalid_agent_status_json',
      json_fence_count: frames.length,
      status_frame_count: statusFrames.length,
      status_frame_spans: statusFrames.map(spanFor),
      statusFrame: invalidStatus,
      status: null,
      parse_error: invalidStatus.parse_error || 'invalid JSON',
    };
  }

  if (statusFrames.length !== 1) {
    return {
      ok: false,
      reason_code: 'ambiguous_agent_status_json',
      json_fence_count: frames.length,
      status_frame_count: statusFrames.length,
      status_frame_spans: statusFrames.map(spanFor),
      statusFrame: null,
      status: null,
    };
  }

  const statusFrame = statusFrames[0];
  return {
    ok: true,
    reason_code: 'valid_agent_status_json',
    json_fence_count: frames.length,
    status_frame_count: 1,
    status_frame_spans: [spanFor(statusFrame)],
    statusFrame,
    status: statusFrame.parsed,
  };
}

export function stripTerminalStatusFrame(input) {
  const source = String(input || '');
  const selection = selectTerminalStatusFrame(source);
  if (!selection.ok || !selection.statusFrame) return source;
  const beforeJson = source.slice(0, selection.statusFrame.start).trimEnd();
  const reportAt = Math.max(
    beforeJson.lastIndexOf('\nStatus Report'),
    beforeJson.startsWith('Status Report') ? 0 : -1,
  );
  const beforeReport = reportAt >= 0 ? beforeJson.slice(0, reportAt).trimEnd() : beforeJson;
  return beforeReport.trimEnd();
}
