const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const extensionRoot = path.resolve(__dirname, '..');
const { normalizeExtractedHtml } = require('../conversion-utils.js');
const { Grab2MdConverter } = require('../converter.js');
const { Grab2MdSettingsStore } = require('../settings-store.js');

test('normalizes short and malformed extracted HTML without reassigning inputs', () => {
  const complete = '<html><body>' + 'content '.repeat(20) + '</body></html>';
  assert.equal(normalizeExtractedHtml(complete), complete);
  const shortUppercaseComplete = '<HTML><BODY>short</BODY></HTML>';
  assert.equal(normalizeExtractedHtml(shortUppercaseComplete), shortUppercaseComplete);

  for (const fragment of ['<p>short</p>', 'plain malformed content']) {
    const normalized = normalizeExtractedHtml(fragment);
    assert.match(normalized, /^<!DOCTYPE html>/);
    assert.ok(normalized.includes(fragment));
  }

  for (const empty of ['', '   ', null]) {
    assert.throws(() => normalizeExtractedHtml(empty), /non-empty string/);
  }
});

test('popup loads only the generic conversion stack', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const scripts = [...popup.matchAll(/<script src="([^"]+)"><\/script>/g)]
    .map(match => match[1]);

  assert.deepEqual(scripts, [
    'logger.js',
    'turndown.js',
    'conversion-utils.js',
    'converter.js',
    'settings-store.js',
    'popup.js'
  ]);
});

test('conversion and settings persistence are isolated controllers', () => {
  class FakeTurndown {
    constructor(options) {
      this.options = options;
      this.rules = [];
    }
    remove() {}
    keep() {}
    addRule(name) { this.rules.push(name); }
    turndown(html) { return `converted:${html}`; }
  }
  const converter = new Grab2MdConverter(FakeTurndown);
  converter.configure({
    markdownOptions: { headingStyle: 'atx', bulletMarker: '-' },
    contentOptions: { codeBlocks: true, preserveImages: true }
  });
  assert.equal(converter.convert('<h1>Title</h1>'), 'converted:<h1>Title</h1>');
  assert.deepEqual(converter.service.rules, ['codeBlock']);

  const storage = {
    get(_key, callback) {
      callback({ grab2mdSettings: { markdownOptions: { headingStyle: 'setext' } } });
    },
    set(value, callback) { this.saved = value; callback(); }
  };
  const store = new Grab2MdSettingsStore(storage);
  const defaults = {
    theme: 'light',
    markdownOptions: { headingStyle: 'atx', bulletMarker: '-' },
    contentOptions: { preserveImages: true }
  };
  store.load(defaults, loaded => {
    assert.equal(loaded.markdownOptions.headingStyle, 'setext');
    assert.equal(loaded.markdownOptions.bulletMarker, '-');
    store.save(loaded, () => {});
  });
  assert.equal(storage.saved.grab2mdSettings.markdownOptions.headingStyle, 'setext');
});

test('settings persistence rejects corrupt values and reports Chrome API failures', () => {
  const defaults = {
    theme: 'light',
    markdownOptions: { headingStyle: 'atx', bulletMarker: '-' },
    contentOptions: { preserveImages: true, codeBlocks: true }
  };
  const corruptStorage = {
    get(_key, callback) {
      callback({
        grab2mdSettings: {
          theme: 'system',
          markdownOptions: { headingStyle: 'html', bulletMarker: '?' },
          contentOptions: { preserveImages: 'yes', codeBlocks: null }
        }
      });
    }
  };
  new Grab2MdSettingsStore(corruptStorage).load(defaults, (loaded, error) => {
    assert.equal(error, undefined);
    assert.deepEqual(loaded, defaults);
    assert.notEqual(loaded.markdownOptions, defaults.markdownOptions);
    assert.notEqual(loaded.contentOptions, defaults.contentOptions);
  });

  const failedStorage = {
    get(_key, callback) { callback(undefined); },
    set(_value, callback) { callback(); }
  };
  const failedStore = new Grab2MdSettingsStore(
    failedStorage,
    'grab2mdSettings',
    () => 'sync storage unavailable'
  );
  failedStore.load(defaults, (loaded, error) => {
    assert.deepEqual(loaded, defaults);
    assert.equal(error, 'sync storage unavailable');
  });
  failedStore.save(defaults, error => {
    assert.equal(error, 'sync storage unavailable');
  });
});

test('popup exposes only implemented link and code formatting controls', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  const converter = fs.readFileSync(path.join(extensionRoot, 'converter.js'), 'utf8');

  assert.doesNotMatch(popup, /id="(?:link-style|inline-links)"/);
  assert.doesNotMatch(popupScript, /cliLink|inlineLinks|link-style/);
  assert.match(popup, /Use Fenced Code Blocks/);
  assert.match(converter, /options\.codeBlockStyle !== 'fenced'/);
  assert.match(converter, /function structuredCodeText\(/);
  assert.match(converter, /linkStyle: 'inlined'/);
  assert.match(popupScript, /await handleOutput\(/);
  assert.match(popupScript, /if \(conversionInFlight\) return/);
  assert.match(popupScript, /function finishConversion\(\)[\s\S]*conversionInFlight = false/);
  assert.match(popupScript, /convertBtn\.disabled = show/);
  assert.match(
    popupScript,
    /try\s*{\s*const htmlContent = Grab2MdConversionUtils\.normalizeExtractedHtml\([\s\S]*?const markdown = convertToMarkdown\([\s\S]*?finally\s*{\s*finishConversion\(\)/
  );
  assert.match(popupScript, /func: extractPageContent/);
  assert.doesNotMatch(popupScript, /function: extractPageContent/);
  assert.doesNotMatch(popup, /include-tables|Format Tables/);
  assert.doesNotMatch(popupScript, /includeTables|include-tables/);
  assert.doesNotMatch(converter, /includeTables|\.keep\(/);
  assert.doesNotMatch(
    popupScript,
    /handleOutput\(markdown, outputAction, tab\.title\);\s*showStatus\('Conversion complete'/
  );
});

test('vendored Turndown uses an inert parser for untrusted HTML strings', () => {
  const turndown = fs.readFileSync(path.join(extensionRoot, 'turndown.js'), 'utf8');

  assert.match(turndown, /new DOMParser\(\)/);
  assert.match(turndown, /parseFromString\(input, ['"]text\/html['"]\)/);
  assert.match(turndown, /root = parsed\.body/);
  assert.doesNotMatch(turndown, /function cleanInput|html\.replace\(/);
  assert.doesNotMatch(turndown, /output = output[\s\S]{0,200}replace\(\/\\n\{3,/);
  assert.doesNotMatch(turndown, /document\.createElement\(['"]div['"]\)[\s\S]{0,120}\.innerHTML/);
  assert.doesNotMatch(turndown, /x-turndown|turndown-root/);
});

test('shared generic semantics fixture defines portable output properties', () => {
  const fixture = JSON.parse(fs.readFileSync(
    path.join(extensionRoot, '..', 'tests', 'fixtures', 'generic-conversion.json'),
    'utf8'
  ));
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  const chromiumSmoke = fs.readFileSync(
    path.join(extensionRoot, 'tests', 'chromium-smoke.js'),
    'utf8'
  );
  assert.equal(typeof fixture.html, 'string');
  assert.equal(typeof fixture.base_path, 'string');
  assert.ok(Array.isArray(fixture.required_phrases));
  assert.ok(fixture.required_phrases.length > 0);
  assert.ok(Array.isArray(fixture.required_markdown_fragments));
  assert.ok(fixture.required_markdown_fragments.length > 0);
  assert.ok(Array.isArray(fixture.links));
  assert.ok(Array.isArray(fixture.images));
  assert.ok(Array.isArray(fixture.srcsets));
  assert.doesNotMatch(popupScript, /replace\([^\n]+(?:Copy code|Search API|model)/);
  assert.match(chromiumSmoke, /generic-conversion\.json/);
  assert.match(chromiumSmoke, /sharedFixture\.required_phrases/);
  assert.match(chromiumSmoke, /sharedFixture\.required_markdown_fragments/);
  assert.match(chromiumSmoke, /sharedFixture\.links/);
  assert.match(chromiumSmoke, /sharedFixture\.images/);
  assert.match(chromiumSmoke, /sharedFixture\.srcsets/);
});

test('article mode uses the pinned packaged Mozilla Readability asset', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  const readability = fs.readFileSync(path.join(extensionRoot, 'readability.js'));

  assert.ok(!popup.includes('id="trim-content"'));
  assert.match(popupScript, /files: \['readability\.js'\]/);
  assert.match(popupScript, /const clone = document\.cloneNode\(true\)/);
  assert.match(popupScript, /new Readability\(clone\)\.parse\(\)/);
  assert.match(popupScript, /button h1, button h2, button h3/);
  assert.match(popupScript, /querySelector\('article h1'\)/);
  assert.match(popupScript, /querySelector\('main h1'\)/);
  assert.match(
    popupScript,
    /const title = \(authoredTitle \|\| article\.title \|\| document\.title/
  );
  assert.match(popupScript, /canonicalizeReferences\(parsed\)/);
  assert.doesNotMatch(popupScript, /\.post-content|\.article-content|elementsToRemove/);
  assert.equal(
    crypto.createHash('sha256').update(readability).digest('hex'),
    '34dcab3d0832d0019f02990eed6b6124e029e8c32b9f0c6f2550544ff8dff174'
  );
});

test('unsupported URL and element modes are not exposed', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const styles = fs.readFileSync(path.join(extensionRoot, 'styles.css'), 'utf8');
  const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, 'manifest.json'), 'utf8'));

  assert.ok(!popup.includes('id="url-capture-tab"'));
  assert.ok(!popup.includes('id="scan-urls-button"'));
  assert.ok(!popup.includes('<option value="element">'));
  assert.equal(manifest.background, undefined);
  assert.ok(!fs.existsSync(path.join(extensionRoot, 'background.js')));
  assert.doesNotMatch(styles, /\.url-|#capture-|\.modal|\.toggle-switch|\.progress-bar/);
});

test('supported popup preview uses packaged scripts without inline JavaScript', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const scripts = [...popup.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/gi)];

  assert.ok(popup.includes('id="markdown-result"'));
  assert.ok(popup.includes('<option value="show">Show in Popup</option>'));
  assert.ok(scripts.length > 0);
  for (const script of scripts) {
    assert.match(script[1], /\ssrc="[^"]+"/);
    assert.equal(script[2].trim(), '');
  }
});

test('popup exposes status, preview, and icon controls accessibly', () => {
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const styles = fs.readFileSync(path.join(extensionRoot, 'styles.css'), 'utf8');

  assert.match(popup, /id="status-message"[^>]+role="status"[^>]+aria-live="polite"/);
  assert.match(popup, /id="markdown-result"[^>]+tabindex="0"[^>]+aria-label=/);
  assert.match(popup, /id="copy-btn"[^>]+aria-label=/);
  assert.match(popup, /id="download-btn"[^>]+aria-label=/);
  assert.match(popup, /id="settings-tab"[^>]+tabindex="-1"/);
  assert.match(styles, /#markdown-result:focus-visible/);
  assert.doesNotMatch(styles, /\baria-live\s*:/);
});

test('manifest and controls use the documented least-privilege surface', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(extensionRoot, 'manifest.json'), 'utf8'));
  const popup = fs.readFileSync(path.join(extensionRoot, 'popup.html'), 'utf8');
  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');

  assert.deepEqual(
    [...manifest.permissions].sort(),
    ['activeTab', 'clipboardWrite', 'downloads', 'scripting', 'storage'].sort()
  );
  assert.equal(manifest.host_permissions, undefined);
  assert.equal(manifest.web_accessible_resources, undefined);
  assert.ok(!popup.includes('cli-path'));
  assert.ok(!popupScript.includes('cliPath'));
  assert.ok(!popup.includes('stop-capture'));

  const ids = [...popup.matchAll(/\sid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(new Set(ids).size, ids.length);
});

test('project-authored production scripts contain no direct console logging or duplicate worker conversion', () => {
  for (const filename of fs.readdirSync(extensionRoot).filter(name => {
    return name.endsWith('.js') && name !== 'readability.js';
  })) {
    const source = fs.readFileSync(path.join(extensionRoot, filename), 'utf8');
    assert.doesNotMatch(source, /console\.(?:log|warn|error)/);
    assert.doesNotMatch(source, /Justin(?:'s)? Workspace/i);
  }

  const popupScript = fs.readFileSync(path.join(extensionRoot, 'popup.js'), 'utf8');
  assert.equal((popupScript.match(/function convertToMarkdown\(/g) || []).length, 1);
});
