const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const extensionRoot = path.resolve(__dirname, '..');
const { normalizeExtractedHtml } = require('../conversion-utils.js');
const ChatGPTCleaner = require('../chatgpt-cleaner.js');

test('normalizes short and malformed extracted HTML without reassigning inputs', () => {
  const complete = '<html><body>' + 'content '.repeat(20) + '</body></html>';
  assert.equal(normalizeExtractedHtml(complete), complete);

  for (const fragment of ['<p>short</p>', 'plain malformed content']) {
    const normalized = normalizeExtractedHtml(fragment);
    assert.match(normalized, /^<!DOCTYPE html>/);
    assert.ok(normalized.includes(fragment));
  }

  for (const empty of ['', '   ', null]) {
    assert.throws(() => normalizeExtractedHtml(empty), /non-empty string/);
  }
});

test('ChatGPT cleanup preserves ordinary product words and fenced code', () => {
  const code = '```text\nSearch Chat GPT OpenAI model 4o\nCopy code\n```';
  const input = [
    'Search is part of my model design.',
    'Chat, GPT, OpenAI, and 4o are user-authored words.',
    'Open sidebar',
    code
  ].join('\n\n');

  const cleaned = ChatGPTCleaner.clean(input);
  assert.ok(cleaned.includes('Search is part of my model design.'));
  assert.ok(cleaned.includes('Chat, GPT, OpenAI, and 4o are user-authored words.'));
  assert.ok(!cleaned.includes('\nOpen sidebar\n'));
  assert.ok(cleaned.includes(code));

  for (const filename of ['popup.js', 'turndown.js', 'chatgpt-turndown.js', 'transcript-converter.js']) {
    const source = fs.readFileSync(path.join(extensionRoot, filename), 'utf8');
    assert.doesNotMatch(source, /(?:replace|match)\(\/OpenAI\|ChatGPT/);
  }
});

test('unsupported URL and element modes are not exposed', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const background = fs.readFileSync(path.join(extensionRoot, 'background.js'), 'utf8');

  assert.ok(!popup.includes('id="url-capture-tab"'));
  assert.ok(!popup.includes('id="scan-urls-button"'));
  assert.ok(!popup.includes('<option value="element">'));
  assert.ok(!background.includes('CAPTURE_LINKS'));
  assert.match(background, /Direct URL conversion is not supported in this release/);
  assert.match(background, /Batch URL conversion is not supported in this release/);
});

test('content viewer loads packaged JavaScript without inline script', () => {
  const viewer = fs.readFileSync(path.join(extensionRoot, 'content-viewer.html'), 'utf8');
  const scripts = [...viewer.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)];

  assert.equal(scripts.length, 1);
  assert.match(scripts[0][1], /src="content-viewer\.js"/);
  assert.equal(scripts[0][2].trim(), '');
});
