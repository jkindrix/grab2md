const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const os = require('node:os');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const extensionRoot = path.resolve(__dirname, '..');

class CdpClient {
  constructor(url) {
    this.url = url;
    this.nextId = 0;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    this.socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(message.error.message));
        else resolve(message.result);
        return;
      }

      for (const listener of this.listeners.get(message.method) || []) {
        listener(message.params);
      }
    };
    await new Promise((resolve, reject) => {
      this.socket.onopen = resolve;
      this.socket.onerror = reject;
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) || [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this.nextId;
      this.pending.set(id, { resolve, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket?.close();
  }
}

function findBrowser() {
  const candidates = [
    process.env.CHROME_BIN,
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable'
  ].filter(Boolean);
  const browser = candidates.find(candidate => fs.existsSync(candidate));
  if (!browser) throw new Error('No supported Chromium executable found');
  return browser;
}

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

async function resourceProbe() {
  const requests = [];
  const pages = new Map();
  const server = http.createServer((request, response) => {
    requests.push(request.url);
    if (pages.has(request.url)) {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      response.end(pages.get(request.url));
      return;
    }
    response.writeHead(204, { 'Content-Type': 'image/png' });
    response.end();
  });
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return {
    requests,
    origin: `http://127.0.0.1:${server.address().port}`,
    setPage: (url, html) => pages.set(url, html),
    close: () => new Promise(resolve => server.close(resolve))
  };
}

async function waitFor(callback, description, timeout = 15000) {
  const deadline = Date.now() + timeout;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await callback();
      if (value) return value;
    } catch (error) {
      lastError = error;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${description}${lastError ? `: ${lastError.message}` : ''}`);
}

async function createTarget(port, url) {
  const response = await fetch(
    `http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`,
    { method: 'PUT' }
  );
  if (!response.ok) throw new Error(`Could not create Chromium target: ${response.status}`);
  return response.json();
}

async function evaluate(client, expression, options = {}) {
  let result;
  try {
    result = await client.send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      ...options
    });
  } catch (error) {
    throw new Error(`${error.message} while evaluating ${expression.slice(0, 120)}`);
  }
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  }
  return result.result.value;
}

async function pressKey(client, key, code, virtualKeyCode) {
  const params = { key, code, windowsVirtualKeyCode: virtualKeyCode };
  await client.send('Input.dispatchKeyEvent', { type: 'keyDown', ...params });
  await client.send('Input.dispatchKeyEvent', { type: 'keyUp', ...params });
}

async function tabSequence(client, count) {
  const focused = [];
  for (let index = 0; index < count; index += 1) {
    await pressKey(client, 'Tab', 'Tab', 9);
    focused.push(await evaluate(client, 'document.activeElement.id'));
  }
  return focused;
}

async function main() {
  const xvfb = spawnSync('which', ['xvfb-run'], { encoding: 'utf8' }).stdout.trim();
  if (!xvfb) throw new Error('xvfb-run is required for unpacked-extension tests');

  const browser = findBrowser();
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'grab2md-chromium-'));
  const downloads = path.join(profile, 'downloads');
  fs.mkdirSync(downloads);
  const port = await unusedPort();
  const probe = await resourceProbe();
  const loadedExtensionRoot = path.join(profile, 'extension-under-test');
  fs.cpSync(extensionRoot, loadedExtensionRoot, { recursive: true });
  const testManifestPath = path.join(loadedExtensionRoot, 'manifest.json');
  const testManifest = JSON.parse(fs.readFileSync(testManifestPath, 'utf8'));
  testManifest.host_permissions = [`${probe.origin}/*`];
  fs.writeFileSync(testManifestPath, `${JSON.stringify(testManifest, null, 2)}\n`);
  const child = spawn(
    xvfb,
    [
      '-a',
      browser,
      '--no-sandbox',
      '--disable-gpu',
      '--disable-dev-shm-usage',
      '--no-first-run',
      '--disable-default-apps',
      `--user-data-dir=${profile}`,
      `--remote-debugging-port=${port}`,
      `--disable-extensions-except=${loadedExtensionRoot}`,
      `--load-extension=${loadedExtensionRoot}`,
      'about:blank'
    ],
    { detached: true, stdio: ['ignore', 'ignore', 'pipe'], env: { ...process.env, HOME: profile } }
  );

  let browserClient;
  let popupClient;
  let semanticClient;
  let fixtureClient;
  let deniedClient;
  try {
    const version = await waitFor(async () => {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      return response.ok ? response.json() : null;
    }, 'Chromium DevTools');

    const preferencesPath = path.join(profile, 'Default', 'Preferences');
    const extensionId = await waitFor(() => {
      if (!fs.existsSync(preferencesPath)) return null;
      const preferences = JSON.parse(fs.readFileSync(preferencesPath, 'utf8'));
      const settings = preferences.extensions?.settings || {};
      return Object.entries(settings).find(([_id, value]) => {
        return value.path && path.resolve(value.path) === loadedExtensionRoot;
      })?.[0];
    }, 'the unpacked extension registration');

    browserClient = new CdpClient(version.webSocketDebuggerUrl);
    await browserClient.connect();
    await browserClient.send('Browser.setDownloadBehavior', {
      behavior: 'allow',
      downloadPath: downloads,
      eventsEnabled: true
    });

    const popupTarget = await createTarget(
      port,
      `chrome-extension://${extensionId}/popup.html`
    );
    popupClient = new CdpClient(popupTarget.webSocketDebuggerUrl);
    await popupClient.connect();

    const exceptions = [];
    const consoleErrors = [];
    popupClient.on('Runtime.exceptionThrown', event => exceptions.push(event));
    popupClient.on('Runtime.consoleAPICalled', event => {
      if (event.type === 'error' || event.type === 'assert') consoleErrors.push(event);
    });
    await popupClient.send('Runtime.enable');
    await popupClient.send('Page.enable');
    await popupClient.send('Page.reload');
    await waitFor(
      () => evaluate(popupClient, 'document.readyState === "complete"'),
      'popup reload'
    );
    await new Promise(resolve => setTimeout(resolve, 250));
    assert.equal(exceptions.length, 0, 'popup raised a runtime exception at startup');

    assert.equal(await evaluate(popupClient, 'typeof TurndownService'), 'function');
    assert.equal(await evaluate(popupClient, 'typeof Grab2MdLogger'), 'object');
    assert.equal(
      await evaluate(popupClient, 'new Set([...document.querySelectorAll("[id]")].map(node => node.id)).size === document.querySelectorAll("[id]").length'),
      true
    );
    assert.deepEqual(
      await evaluate(
        popupClient,
        `({
          statusRole: statusMessage.getAttribute('role'),
          statusLive: statusMessage.getAttribute('aria-live'),
          statusAtomic: statusMessage.getAttribute('aria-atomic'),
          previewTabIndex: markdownResult.tabIndex,
          previewLabel: markdownResult.getAttribute('aria-label'),
          copyLabel: copyBtn.getAttribute('aria-label'),
          downloadLabel: downloadBtn.getAttribute('aria-label'),
          settingsTabIndex: document.getElementById('settings-tab').tabIndex
        })`
      ),
      {
        statusRole: 'status',
        statusLive: 'polite',
        statusAtomic: 'true',
        previewTabIndex: 0,
        previewLabel: 'Markdown conversion result',
        copyLabel: 'Copy conversion result to clipboard',
        downloadLabel: 'Download conversion result as a file',
        settingsTabIndex: -1
      }
    );
    await evaluate(
      popupClient,
      `document.body.tabIndex = -1; document.body.focus(); document.body.classList.remove('dark-theme')`
    );
    await pressKey(popupClient, 'Tab', 'Tab', 9);
    assert.equal(await evaluate(popupClient, 'document.activeElement.id'), 'theme-toggle-btn');
    assert.deepEqual(
      await evaluate(
        popupClient,
        `({
          style: getComputedStyle(document.activeElement).outlineStyle,
          width: getComputedStyle(document.activeElement).outlineWidth
        })`
      ),
      { style: 'solid', width: '2px' }
    );
    await evaluate(popupClient, `document.body.classList.add('dark-theme')`);
    assert.equal(
      await evaluate(popupClient, `getComputedStyle(document.activeElement).outlineStyle`),
      'solid'
    );
    await evaluate(popupClient, `document.body.classList.remove('dark-theme')`);
    await pressKey(popupClient, 'Tab', 'Tab', 9);
    assert.equal(await evaluate(popupClient, 'document.activeElement.id'), 'convert-tab');
    await pressKey(popupClient, 'ArrowRight', 'ArrowRight', 39);
    assert.deepEqual(
      await evaluate(
        popupClient,
        `({
          focus: document.activeElement.id,
          selected: document.getElementById('settings-tab').getAttribute('aria-selected'),
          panel: document.getElementById('settings').classList.contains('active')
        })`
      ),
      { focus: 'settings-tab', selected: 'true', panel: true }
    );
    await pressKey(popupClient, 'ArrowLeft', 'ArrowLeft', 37);
    assert.equal(await evaluate(popupClient, 'document.activeElement.id'), 'convert-tab');
    assert.deepEqual(
      await tabSequence(popupClient, 5),
      ['convert', 'conversion-mode', 'output-action', 'convert-btn', 'settings-btn']
    );

    await evaluate(popupClient, `settingsBtn.click()`);
    assert.equal(
      await evaluate(popupClient, `document.getElementById('settings').classList.contains('active')`),
      true
    );
    assert.equal(await evaluate(popupClient, 'document.activeElement.id'), 'settings');
    assert.deepEqual(
      await tabSequence(popupClient, 6),
      [
        'heading-style',
        'bullet-marker',
        'preserve-images',
        'code-blocks',
        'save-settings',
        'reset-defaults'
      ]
    );
    await evaluate(
      popupClient,
      `document.getElementById('heading-style').value = 'setext'; saveSettingsBtn.click()`
    );
    await waitFor(async () => {
      const stored = await evaluate(
        popupClient,
        `new Promise(resolve => chrome.storage.sync.get('grab2mdSettings', resolve))`
      );
      return stored.grab2mdSettings?.markdownOptions?.headingStyle === 'setext';
    }, 'saved popup settings');
    await evaluate(popupClient, `themeToggleBtn.click()`);
    assert.equal(await evaluate(popupClient, `document.body.classList.contains('dark-theme')`), true);
    await evaluate(popupClient, `window.confirm = () => true; resetDefaultsBtn.click()`);
    assert.equal(await evaluate(popupClient, `document.getElementById('heading-style').value`), 'atx');

    const markdown = await evaluate(
      popupClient,
      `convertToMarkdown('<h1>Fixture</h1><p>Search indexing uses a model.</p><pre><code class="language-text">model Search API</code></pre>')`
    );
    assert.match(markdown, /^# Fixture/m);
    assert.match(markdown, /Search indexing uses a model\./);
    assert.match(markdown, /```text\nmodel Search API\n```/);

    const highlightedCode = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(
        '<pre><code class="language-rust">' +
        '<span class="line"><span>struct</span> User {</span>' +
        '<span class="line">    id: UserId,</span>' +
        '<span class="line"></span><span class="line"></span>' +
        '<span class="line">}</span></code></pre>'
      )})`
    );
    assert.equal(
      highlightedCode,
      '```rust\nstruct User {\n    id: UserId,\n\n\n}\n```'
    );

    const structuralMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(
        '<div>\n  <section>\n    <div><p>First paragraph.</p></div>\n' +
        '    <div><p>Second paragraph.</p></div>\n  </section>\n</div>'
      )})`
    );
    assert.match(structuralMarkdown, /First paragraph\./);
    assert.match(structuralMarkdown, /Second paragraph\./);
    assert.doesNotMatch(
      structuralMarkdown,
      /(?:\n[ \t]*){3,}/,
      `structural blank lines were inflated: ${JSON.stringify(structuralMarkdown)}`
    );

    const figureMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown('<figure><img src="https://example.com/chart.png" alt="Chart"><figcaption>One caption</figcaption></figure>')`
    );
    assert.equal((figureMarkdown.match(/One caption/g) || []).length, 1, figureMarkdown);
    assert.match(figureMarkdown, /\*One caption\*/);

    const responsiveOnlyImage = await evaluate(
      popupClient,
      `convertToMarkdown('<img srcset="https://example.com/small.png 1x, https://example.com/large.png 2x" alt="Responsive">')`
    );
    assert.equal(responsiveOnlyImage, '![Responsive](https://example.com/small.png)');

    const divCodeMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown('<div class="code-block language-js">const answer = 42;</div>')`
    );
    assert.equal(divCodeMarkdown, '```js\nconst answer = 42;\n```');
    assert.equal(
      await evaluate(
        popupClient,
        `convertToMarkdown(${JSON.stringify(
          '<p><code>alpha `` beta</code> and <code>`tick`</code></p>'
        )})`
      ),
      '`alpha `` beta` and `` `tick` ``'
    );

    const sharedFixture = JSON.parse(fs.readFileSync(
      path.join(extensionRoot, '..', 'tests', 'fixtures', 'generic-conversion.json'),
      'utf8'
    ));
    const sharedMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(sharedFixture.html)})`
    );
    for (const phrase of sharedFixture.required_phrases) {
      assert.ok(sharedMarkdown.includes(phrase), sharedMarkdown);
    }
    for (const fragment of sharedFixture.required_markdown_fragments) {
      assert.ok(sharedMarkdown.includes(fragment), sharedMarkdown);
    }

    probe.setPage(sharedFixture.base_path, sharedFixture.html);
    const sharedFixtureUrl = `${probe.origin}${sharedFixture.base_path}`;
    const semanticTarget = await createTarget(port, sharedFixtureUrl);
    semanticClient = new CdpClient(semanticTarget.webSocketDebuggerUrl);
    await semanticClient.connect();
    await semanticClient.send('Runtime.enable');
    await waitFor(
      () => evaluate(semanticClient, `document.readyState === 'complete'`),
      'the shared semantic fixture'
    );
    const extractionSource = await evaluate(popupClient, 'extractPageContent.toString()');
    const readabilitySource = fs.readFileSync(path.join(extensionRoot, 'readability.js'), 'utf8');
    await evaluate(semanticClient, readabilitySource);
    const semanticFullPage = await evaluate(
      semanticClient,
      `(${extractionSource})('full-page')`
    );
    const semanticArticle = await evaluate(
      semanticClient,
      `(${extractionSource})('article')`
    );
    const semanticFullMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(semanticFullPage)})`
    );
    const semanticArticleMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(semanticArticle)})`
    );
    for (const phrase of sharedFixture.required_phrases) {
      assert.ok(semanticFullMarkdown.includes(phrase), semanticFullMarkdown);
    }
    for (const fragment of sharedFixture.required_markdown_fragments) {
      assert.ok(semanticFullMarkdown.includes(fragment), semanticFullMarkdown);
    }
    assert.match(semanticArticleMarkdown, /^# Architecture Notes/m);
    assert.match(semanticArticleMarkdown, /^## Expanded rationale/m);
    assert.match(semanticArticleMarkdown, /Expanded evidence remains visible\./);
    for (const link of sharedFixture.links) {
      const expected = new URL(link.relative, sharedFixtureUrl).href;
      assert.ok(
        semanticFullMarkdown.includes(`[${link.label}](${expected})`),
        semanticFullMarkdown
      );
    }
    for (const image of sharedFixture.images) {
      const expected = new URL(image.relative, sharedFixtureUrl).href;
      assert.ok(
        semanticFullMarkdown.includes(`![${image.alt}](${expected})`),
        semanticFullMarkdown
      );
    }
    const semanticSrcsets = await evaluate(
      semanticClient,
      `(() => {
        const parsed = new DOMParser().parseFromString(
          ${JSON.stringify(semanticFullPage)},
          'text/html'
        );
        return ${JSON.stringify(sharedFixture.srcsets)}.map(reference => {
          return parsed.querySelector(reference.selector)?.getAttribute('srcset') || null;
        });
      })()`
    );
    sharedFixture.srcsets.forEach((reference, index) => {
      const expected = reference.value.split(',').map(candidate => {
        const [url, descriptor] = candidate.trim().split(/\s+/, 2);
        const resolved = new URL(url, sharedFixtureUrl).href;
        return descriptor ? `${resolved} ${descriptor}` : resolved;
      }).join(', ');
      assert.equal(semanticSrcsets[index], expected);
    });
    semanticClient.close();
    semanticClient = undefined;

    const escapedMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown('<p>*literal* _underscored_ [brackets] and 1. list text</p><pre><code>*code*</code></pre>')`
    );
    assert.match(escapedMarkdown, /\\\*literal\\\*/);
    assert.match(escapedMarkdown, /\\_underscored\\_/);
    assert.match(escapedMarkdown, /\\\[brackets\\\]/);
    assert.match(escapedMarkdown, /```\n\*code\*\n```/);

    const escapedDestinations = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(
        '<p><a href="https://example.com/a b(c)" title=\'say "hello"\'>destination</a></p>' +
        '<img src="https://example.com/image (1).png" alt="*logo*" title=\'say "hello"\'>'
      )})`
    );
    assert.ok(
      escapedDestinations.includes(
        '[destination](<https://example.com/a b\\(c\\)> "say \\"hello\\"")'
      ),
      escapedDestinations
    );
    assert.ok(
      escapedDestinations.includes(
        '![\\*logo\\*](<https://example.com/image \\(1\\).png> "say \\"hello\\"")'
      ),
      escapedDestinations
    );
    const unsafeDestination = await evaluate(
      popupClient,
      `convertToMarkdown('<a href="JaVaScRiPt:alert(1)">safe label</a>')`
    );
    assert.equal(unsafeDestination, 'safe label');
    const orderedContinuation = await evaluate(
      popupClient,
      `convertToMarkdown('<ol start="100"><li>first<br>second</li></ol>')`
    );
    assert.match(orderedContinuation, /^100\. first {2}\n {5}second$/);

    const tableMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown('<table><tr><th>Name</th><th>Value</th></tr><tr><td>one</td><td>**literal** [x](y) _word_ | pipe\\nnext</td></tr></table>')`
    );
    assert.match(tableMarkdown, /\| Name \| Value \|/);
    assert.match(tableMarkdown, /\| --- \| --- \|/);
    assert.match(tableMarkdown, /\\\*\\\*literal\\\*\\\*/);
    assert.match(tableMarkdown, /\\\[x\\\]\(y\)/);
    assert.match(tableMarkdown, /\\_word\\_/);
    assert.match(tableMarkdown, /\\\| pipe<br>next/);
    assert.doesNotMatch(tableMarkdown, /<table|<tr|<td|<th/i);

    await evaluate(
      popupClient,
      `document.getElementById('code-blocks').checked = false; saveSettingsBtn.click()`
    );
    const indentedCode = await evaluate(
      popupClient,
      `convertToMarkdown('<pre><code>alpha\\nbeta</code></pre>')`
    );
    assert.match(indentedCode, /^    alpha\n    beta$/m);
    await evaluate(
      popupClient,
      `document.getElementById('code-blocks').checked = true; saveSettingsBtn.click()`
    );

    await evaluate(
      popupClient,
      `document.getElementById('preserve-images').checked = false; saveSettingsBtn.click()`
    );
    assert.equal(
      await evaluate(
        popupClient,
        `convertToMarkdown('<img src="https://example.com/hidden.png" alt="Hidden">')`
      ),
      ''
    );
    await evaluate(
      popupClient,
      `document.getElementById('preserve-images').checked = true; saveSettingsBtn.click()`
    );
    assert.equal(
      await evaluate(
        popupClient,
        `convertToMarkdown('<img src="https://example.com/tiny.png" alt="Tiny" width="1" height="1">')`
      ),
      '![Tiny](https://example.com/tiny.png)'
    );

    const authoredCode = [
      '',
      'if (ready) {',
      '    call(  one, two  );',
      '\treturn "``````";',
      '',
      '',
      '}',
      ''
    ].join('\n');
    const preservedCode = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(
        '<pre><code class="language-js">' + authoredCode + '</code></pre>'
      )})`
    );
    assert.ok(
      preservedCode.includes(authoredCode),
      `preformatted whitespace changed: ${JSON.stringify(preservedCode)}`
    );
    const fenceLines = preservedCode.split('\n').filter(line => /^`{3,}(?:js)?$/.test(line));
    assert.equal(fenceLines.length, 2);
    assert.equal(fenceLines[0], '```````js');
    assert.equal(fenceLines[1], '```````');
    assert.equal(preservedCode, `\`\`\`\`\`\`\`js\n${authoredCode}\`\`\`\`\`\`\``);

    probe.requests.length = 0;
    await evaluate(
      popupClient,
      `globalThis.grab2mdCustomElementRuns = 0;
       if (!customElements.get('grab2md-probe')) {
         customElements.define('grab2md-probe', class extends HTMLElement {
           constructor() { super(); globalThis.grab2mdCustomElementRuns += 1; }
         });
       }`
    );
    const passiveMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(
        '<p>Passive fixture</p>' +
        '</x-turndown><p>Content after a forged sentinel close</p>' +
        '<img src="${probe.origin}/image.png" alt="Probe" onerror="globalThis.grab2mdCustomElementRuns += 1">' +
        '<iframe src="${probe.origin}/frame"></iframe>' +
        '<audio src="${probe.origin}/audio"></audio>' +
        '<video src="${probe.origin}/video" poster="${probe.origin}/poster.png"></video>' +
        '<source src="${probe.origin}/source" srcset="${probe.origin}/set.png 1x">' +
        '<link rel="stylesheet" href="${probe.origin}/style.css">' +
        '<object data="${probe.origin}/object"></object>' +
        '<style>.private-implementation { color: red; }</style>' +
        '<template>Template implementation text</template>' +
        '<script>globalThis.grab2mdCustomElementRuns += 1<\/script>' +
        '<grab2md-probe></grab2md-probe>' +
        '<meta http-equiv="refresh" content="0;url=${probe.origin}/navigate">'
      )`
    );
    assert.match(passiveMarkdown, /!\[Probe\]/);
    assert.match(passiveMarkdown, /Content after a forged sentinel close/);
    assert.doesNotMatch(passiveMarkdown, /private-implementation|Template implementation text/);
    assert.doesNotMatch(passiveMarkdown, /grab2mdCustomElementRuns/);
    await new Promise(resolve => setTimeout(resolve, 500));
    assert.deepEqual(
      probe.requests,
      [],
      `conversion initiated passive resource requests: ${JSON.stringify(probe.requests)}`
    );
    assert.equal(await evaluate(popupClient, `globalThis.grab2mdCustomElementRuns`), 0);
    assert.match(
      await evaluate(popupClient, `location.href`),
      new RegExp(`^chrome-extension://${extensionId}/popup\\.html`)
    );

    const articleText = 'A substantial article sentence with concrete evidence and punctuation. '.repeat(12);
    const fixtureHtml = `<html><head><title>Injected Article | Fixture Site</title></head><body><header><h1>Fixture Site</h1></header><nav>Full navigation</nav><article><h1>Injected Article</h1><p id="selection">Selected text. ${articleText}</p><figure><button id="disclosure"><h2>Expandable evidence</h2></button></figure><p>${articleText}</p></article><section class="comments">Full comments</section><footer>Full footer</footer><script>document.getElementById('disclosure').addEventListener('click', () => { const paragraph = document.createElement('p'); paragraph.id = 'expanded-live'; paragraph.textContent = 'Expanded live content.'; document.querySelector('figure').appendChild(paragraph); });</script></body></html>`;
    probe.setPage('/fixture.html', fixtureHtml);
    const fixtureTarget = await createTarget(port, `${probe.origin}/fixture.html`);
    fixtureClient = new CdpClient(fixtureTarget.webSocketDebuggerUrl);
    await fixtureClient.connect();
    await fixtureClient.send('Runtime.enable');
    await waitFor(
      () => evaluate(fixtureClient, `Boolean(document.getElementById('disclosure'))`),
      'the disclosure fixture'
    );
    await evaluate(fixtureClient, `document.getElementById('disclosure').click()`);
    assert.equal(
      await evaluate(fixtureClient, `document.getElementById('expanded-live').textContent`),
      'Expanded live content.'
    );
    await evaluate(fixtureClient, readabilitySource);
    assert.equal(await evaluate(fixtureClient, 'typeof Readability'), 'function');
    const fullPage = await evaluate(fixtureClient, `(${extractionSource})('full-page')`);
    const article = await evaluate(fixtureClient, `(${extractionSource})('article')`);
    assert.match(fullPage, /<nav>Full navigation<\/nav>/);
    assert.match(fullPage, /Full comments/);
    assert.match(fullPage, /<footer>Full footer<\/footer>/);
    assert.match(fullPage, /Expanded live content\./);
    assert.doesNotMatch(article, /Fixture Site|Full navigation|Full comments|Full footer/);
    assert.match(article, /<h[12]>Injected Article<\/h[12]>/);
    assert.doesNotMatch(article, /Injected Article \| Fixture Site/);
    assert.match(article, /Expandable evidence/);
    assert.match(article, /Expanded live content\./);

    const fullMarkdown = await evaluate(
      popupClient,
      `convertToMarkdown(${JSON.stringify(fullPage)})`
    );
    assert.match(fullMarkdown, /Full navigation/);
    assert.match(fullMarkdown, /Full comments/);
    assert.match(fullMarkdown, /Full footer/);
    assert.match(fullMarkdown, /Expanded live content\./);

    await evaluate(
      fixtureClient,
      `const range = document.createRange();
       range.selectNodeContents(document.getElementById('selection'));
       const selection = window.getSelection();
       selection.removeAllRanges();
       selection.addRange(range);`
    );
    const selection = await evaluate(fixtureClient, `(${extractionSource})('selection')`);
    assert.match(selection, /Selected text/);
    assert.doesNotMatch(selection, /Injected Article/);

    await fixtureClient.send('Page.bringToFront');
    await evaluate(
      popupClient,
      `conversionModeSelect.value = 'full-page'; outputActionSelect.value = 'show'; convertBtn.click()`
    );
    await waitFor(async () => {
      const state = await evaluate(
        popupClient,
        `({ markdown: markdownResult.textContent, status: statusMessage.textContent, error: statusMessage.classList.contains('error') })`
      );
      if (state.error) throw new Error(state.status);
      return state.markdown.includes('Injected Article');
    }, 'real popup conversion through chrome.scripting.executeScript');
    assert.match(
      await evaluate(popupClient, 'markdownResult.textContent'),
      /Injected Article/
    );
    assert.deepEqual(
      await evaluate(
        popupClient,
        `({ inFlight: conversionInFlight, disabled: convertBtn.disabled })`
      ),
      { inFlight: false, disabled: false }
    );

    await evaluate(
      fixtureClient,
      `const whitespace = document.createElement('span');
       whitespace.id = 'whitespace-selection';
       whitespace.textContent = '   ';
       document.body.appendChild(whitespace);
       const emptyRange = document.createRange();
       emptyRange.selectNodeContents(whitespace);
       const emptySelection = window.getSelection();
       emptySelection.removeAllRanges();
       emptySelection.addRange(emptyRange);`
    );
    await fixtureClient.send('Page.bringToFront');
    await evaluate(
      popupClient,
      `conversionModeSelect.value = 'selection'; outputActionSelect.value = 'show'; convertBtn.click()`
    );
    await waitFor(async () => {
      const state = await evaluate(
        popupClient,
        `({ status: statusMessage.textContent, error: statusMessage.classList.contains('error'), spinner: spinner.style.display })`
      );
      return state.error && state.spinner === 'none';
    }, 'whitespace selection terminal error');
    assert.match(
      await evaluate(popupClient, 'statusMessage.textContent'),
      /non-empty string/
    );
    assert.deepEqual(
      await evaluate(
        popupClient,
        `({ inFlight: conversionInFlight, disabled: convertBtn.disabled })`
      ),
      { inFlight: false, disabled: false }
    );

    const turndownSource = fs.readFileSync(path.join(extensionRoot, 'turndown.js'), 'utf8');
    await evaluate(fixtureClient, turndownSource);
    const injectedMarkdown = await evaluate(
      fixtureClient,
      `new TurndownService().turndown(${JSON.stringify(article)})`
    );
    assert.match(injectedMarkdown, /Injected/);

    await evaluate(
      popupClient,
      `document.getElementById('convert-tab').click();
       handleOutput('# Preview result', 'show', 'Fixture')`
    );
    assert.deepEqual(
      await evaluate(popupClient, `({ text: markdownResult.textContent, visible: resultContainer.style.display })`),
      { text: '# Preview result', visible: 'block' }
    );
    await evaluate(
      popupClient,
      `markdownResult.textContent = Array.from({ length: 80 }, (_, index) => 'Preview line ' + index).join('\\n');
       downloadBtn.focus()`
    );
    await pressKey(popupClient, 'Tab', 'Tab', 9);
    assert.deepEqual(
      await evaluate(
        popupClient,
        `markdownResult.scrollTop = markdownResult.scrollHeight;
         ({
           focused: document.activeElement === markdownResult,
           scrollable: markdownResult.scrollHeight > markdownResult.clientHeight,
           scrolled: markdownResult.scrollTop > 0,
           outline: getComputedStyle(markdownResult).outlineStyle
         })`
      ),
      { focused: true, scrollable: true, scrolled: true, outline: 'solid' }
    );
    await evaluate(popupClient, `handleOutput('# Preview result', 'show', 'Fixture')`);

    assert.deepEqual(
      await evaluate(
        popupClient,
        `showStatus('Still converting', 'processing');
         ({ status: statusMessage.textContent, timer: window.statusTimer || null })`
      ),
      { status: 'Still converting', timer: null }
    );
    assert.deepEqual(
      await evaluate(
        popupClient,
        `showStatus('Temporary success', 'success');
         const transientTimer = window.statusTimer;
         showStatus('Terminal failure', 'error');
         ({
           status: statusMessage.textContent,
           error: statusMessage.classList.contains('error'),
           hadTransientTimer: Boolean(transientTimer),
           activeTimer: window.statusTimer || null
         })`
      ),
      {
        status: 'Terminal failure',
        error: true,
        hadTransientTimer: true,
        activeTimer: null
      }
    );

    const emptyDownload = await evaluate(
      popupClient,
      `markdownResult.textContent = '# Stale preview';
       let capturedUrl;
       downloadMarkdown(
         '',
         'Empty Fixture',
         { download: (options, callback) => { capturedUrl = options.url; callback(71); } },
         () => null
       ).then(async result => ({
         downloadId: result.downloadId,
         body: await (await fetch(capturedUrl)).text()
       }))`
    );
    assert.deepEqual(emptyDownload, { downloadId: 71, body: '' });

    await popupClient.send('Page.bringToFront');
    await evaluate(
      popupClient,
      `handleOutput('# Copy result', 'copy', 'Fixture')`,
      { userGesture: true }
    );
    assert.equal(await evaluate(popupClient, `statusMessage.textContent`), 'Copied to clipboard');

    await evaluate(
      popupClient,
      `Object.defineProperty(navigator, 'clipboard', {
         configurable: true,
         value: { writeText: () => Promise.reject(new Error('fixture clipboard denial')) }
       });
       handleOutput('# Copy failure', 'copy', 'Fixture').catch(() => {});`
    );
    await waitFor(
      () => evaluate(popupClient, `statusMessage.textContent.includes('fixture clipboard denial')`),
      'clipboard failure status'
    );
    assert.equal(
      await evaluate(popupClient, `statusMessage.classList.contains('error')`),
      true
    );

    const deniedDownload = await evaluate(
      popupClient,
      `downloadMarkdown(
         '# Download failure',
         'Fixture',
         { download: (_options, callback) => callback() },
         () => 'fixture download denial'
       ).then(
         () => ({ resolved: true, status: statusMessage.textContent }),
         error => ({ resolved: false, status: statusMessage.textContent, error: error.message })
       )`
    );
    assert.deepEqual(deniedDownload, {
      resolved: false,
      status: 'Error saving file: fixture download denial',
      error: 'fixture download denial'
    });

    const permissions = await evaluate(
      popupClient,
      'new Promise(resolve => chrome.permissions.getAll(resolve))'
    );
    assert.deepEqual(permissions.origins, [`${probe.origin}/*`]);
    assert.deepEqual(
      [...permissions.permissions].sort(),
      ['activeTab', 'clipboardWrite', 'downloads', 'scripting', 'storage'].sort()
    );

    const deniedOrigin = probe.origin.replace('127.0.0.1', 'localhost');
    const deniedTarget = await createTarget(port, `${deniedOrigin}/fixture.html`);
    deniedClient = new CdpClient(deniedTarget.webSocketDebuggerUrl);
    await deniedClient.connect();
    await deniedClient.send('Page.bringToFront');
    const deniedTabId = await waitFor(
      () => evaluate(
        popupClient,
        `new Promise(resolve => chrome.tabs.query({ active: true, currentWindow: true }, tabs => resolve(tabs[0]?.id || null)))`
      ),
      'the ungranted-origin fixture tab'
    );
    const denied = await evaluate(
      popupClient,
      `new Promise(resolve => chrome.scripting.executeScript(
        { target: { tabId: ${deniedTabId} }, func: () => document.title },
        result => resolve({ result, error: chrome.runtime.lastError?.message || null })
      ))`
    );
    assert.match(denied.error, /Cannot access contents|respective host/);

    await evaluate(popupClient, `handleOutput('# Download result', 'show', 'Fixture')`);
    const downloadResult = await evaluate(
      popupClient,
      `downloadMarkdown(null, 'Fixture Page')`,
      { userGesture: true }
    );
    assert.equal(downloadResult.error, null);
    assert.equal(typeof downloadResult.downloadId, 'number');
    await new Promise(resolve => setTimeout(resolve, 1000));
    const downloadItems = await evaluate(
      popupClient,
      `new Promise(resolve => chrome.downloads.search({}, resolve))`
    );
    const downloaded = downloadItems.find(item => {
      return item.byExtensionId === extensionId && item.mime === 'text/markdown';
    });
    assert.ok(downloaded, `download was not recorded: ${JSON.stringify(downloadItems)}`);
    assert.equal(downloaded.state, 'complete', JSON.stringify(downloaded));
    assert.match(fs.readFileSync(downloaded.filename, 'utf8'), /Download result/);

    await new Promise(resolve => setTimeout(resolve, 250));
    assert.equal(exceptions.length, 0, 'popup raised a runtime exception after reload');
    assert.equal(consoleErrors.length, 0, 'popup emitted a console error');
    process.stdout.write('Chromium extension smoke: popup controls, extraction, conversion, output, and permissions passed\n');
  } finally {
    deniedClient?.close();
    popupClient?.close();
    semanticClient?.close();
    fixtureClient?.close();
    browserClient?.close();
    try {
      process.kill(-child.pid, 'SIGTERM');
    } catch (_error) {
      child.kill('SIGTERM');
    }
    await new Promise(resolve => setTimeout(resolve, 250));
    await probe.close();
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch(error => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exitCode = 1;
});
