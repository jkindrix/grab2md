// DOM Elements
const convertBtn = document.getElementById('convert-btn');
const settingsBtn = document.getElementById('settings-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const conversionModeSelect = document.getElementById('conversion-mode');
const outputActionSelect = document.getElementById('output-action');
const resultContainer = document.getElementById('result-container');
const markdownResult = document.getElementById('markdown-result');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');
const statusMessage = document.getElementById('status-message');
const spinner = document.getElementById('spinner');
const saveSettingsBtn = document.getElementById('save-settings');
const resetDefaultsBtn = document.getElementById('reset-defaults');

// Default settings
const defaultSettings = {
  theme: 'light',
  markdownOptions: {
    headingStyle: 'atx',
    bulletMarker: '-',
  },
  contentOptions: {
    preserveImages: true,
    codeBlocks: true
  }
};

// Current settings - will be loaded from storage
function freshDefaultSettings() {
  return {
    ...defaultSettings,
    markdownOptions: { ...defaultSettings.markdownOptions },
    contentOptions: { ...defaultSettings.contentOptions }
  };
}

let settings = freshDefaultSettings();
let conversionInFlight = false;

const converter = new Grab2MdConverter();
const settingsStore = new Grab2MdSettingsStore(chrome.storage.sync);

// Initialize the extension
document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadSettings();

  // Set up event listeners
  setupEventListeners();
});

// Load saved settings from Chrome storage
function loadSettings() {
  settingsStore.load(defaultSettings, (loaded, error) => {
    settings = loaded;
    applySettings();
    if (error) showStatus('Failed to load settings: ' + error, 'error');
  });
}

// Save settings to Chrome storage
function saveSettings(successMessage = 'Settings saved') {
  settingsStore.save(settings, error => {
    if (error) {
      showStatus('Failed to save settings: ' + error, 'error');
      return;
    }
    showStatus(successMessage, 'success');
  });
}

// Apply current settings to the UI
function applySettings() {
  // Apply theme
  if (settings.theme === 'dark') {
    document.body.classList.add('dark-theme');
    document.getElementById('light-icon').style.display = 'none';
    document.getElementById('dark-icon').style.display = 'block';
  } else {
    document.body.classList.remove('dark-theme');
    document.getElementById('light-icon').style.display = 'block';
    document.getElementById('dark-icon').style.display = 'none';
  }

  // Set form values based on settings
  document.getElementById('heading-style').value = settings.markdownOptions.headingStyle;
  document.getElementById('bullet-marker').value = settings.markdownOptions.bulletMarker;

  document.getElementById('preserve-images').checked = settings.contentOptions.preserveImages;
  document.getElementById('code-blocks').checked = settings.contentOptions.codeBlocks;

  converter.configure(settings);
}

// Set up all event listeners
function setupEventListeners() {
  // Main convert button
  convertBtn.addEventListener('click', handleConversion);

  // Settings button opens the packaged settings tab.
  settingsBtn.addEventListener('click', () => {
    document.getElementById('settings-tab').click();
  });

  // Save settings button
  saveSettingsBtn.addEventListener('click', () => {
    updateSettingsFromForm();
    saveSettings();
  });

  // Reset defaults button
  resetDefaultsBtn.addEventListener('click', () => {
    if (confirm('Are you sure you want to reset all settings to default values?')) {
      settings = freshDefaultSettings();
      applySettings();
      saveSettings('Settings reset to defaults');
    }
  });

  // Theme toggle
  themeToggleBtn.addEventListener('click', () => {
    settings.theme = settings.theme === 'light' ? 'dark' : 'light';
    applySettings();
    saveSettings();
  });

  // Copy button
  copyBtn.addEventListener('click', () => {
    const markdownText = markdownResult.textContent;
    navigator.clipboard.writeText(markdownText).then(() => {
      showStatus('Copied to clipboard', 'success');
    }).catch(err => {
      showStatus('Failed to copy: ' + err, 'error');
    });
  });

  // Download button
  downloadBtn.addEventListener('click', () => {
    // downloadMarkdown reports its own user-facing failure before rejecting.
    downloadMarkdown().catch(() => {});
  });

  // Tab navigation with accessibility support
  const tabButtons = document.querySelectorAll('.tab-button');
  tabButtons.forEach(button => {
    button.addEventListener('click', () => {
      // Get the tab ID
      const tabId = button.getAttribute('data-tab');

      // Update all tab buttons (remove active state and aria-selected)
      document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        btn.setAttribute('aria-selected', 'false');
        btn.tabIndex = -1;
      });

      // Update all tab panels (remove active state)
      document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
        pane.tabIndex = -1;
      });

      // Activate the selected tab button
      button.classList.add('active');
      button.setAttribute('aria-selected', 'true');
      button.tabIndex = 0;

      // Activate the corresponding tab panel
      const panel = document.getElementById(tabId);
      panel.classList.add('active');
      panel.tabIndex = 0;

      // Set focus to the panel if using keyboard
      if (window.keyboardNavigation) {
        panel.focus();
      }
    });

    // Handle keyboard navigation
    button.addEventListener('keydown', (e) => {
      // Set a flag to indicate keyboard navigation
      window.keyboardNavigation = true;

      // Left/right keys to navigate between tabs
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();

        const buttons = Array.from(tabButtons);
        const currentIndex = buttons.indexOf(button);
        let newIndex;

        if (e.key === 'ArrowRight') {
          newIndex = (currentIndex + 1) % buttons.length;
        } else {
          newIndex = (currentIndex - 1 + buttons.length) % buttons.length;
        }

        buttons[newIndex].click();
        buttons[newIndex].focus();
      }
    });
  });

  // Reset keyboard navigation flag on mouse use
  document.addEventListener('mousedown', () => {
    window.keyboardNavigation = false;
  });
}

// Update settings object from form values
function updateSettingsFromForm() {
  settings.markdownOptions = {
    headingStyle: document.getElementById('heading-style').value,
    bulletMarker: document.getElementById('bullet-marker').value
  };

  settings.contentOptions = {
    preserveImages: document.getElementById('preserve-images').checked,
    codeBlocks: document.getElementById('code-blocks').checked
  };

  converter.configure(settings);
}

// Handle the conversion process
function handleConversion() {
  if (conversionInFlight) return;
  conversionInFlight = true;
  const conversionMode = conversionModeSelect.value;
  const outputAction = outputActionSelect.value;

  showStatus('Converting...', 'processing');
  showSpinner(true);

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];
    if (chrome.runtime.lastError || !tab) {
      const message = chrome.runtime.lastError?.message || 'No active tab available';
      showStatus('Error: ' + message, 'error');
      finishConversion();
      return;
    }

    const extract = () => chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPageContent,
      args: [conversionMode]
    }, async (results) => {
      if (chrome.runtime.lastError) {
        showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
        finishConversion();
        return;
      }

      const extractedContent = results?.[0]?.result;

      if (!extractedContent) {
        showStatus('Error: Could not extract content', 'error');
        finishConversion();
        return;
      }
      
      try {
        const htmlContent = Grab2MdConversionUtils.normalizeExtractedHtml(extractedContent);

        // Convert HTML to Markdown
        const markdown = convertToMarkdown(htmlContent);

        // Await output so an asynchronous clipboard/download error remains the
        // terminal status instead of being overwritten by generic success.
        await handleOutput(markdown, outputAction, tab.title);
        if (outputAction === 'show') {
          showStatus('Conversion complete', 'success');
        }
      } catch (err) {
        if (!statusMessage.classList.contains('error')) {
          showStatus('Conversion failed: ' + err, 'error');
        }
      } finally {
        finishConversion();
      }
    });

    if (conversionMode === 'article') {
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        files: ['readability.js']
      }, () => {
        if (chrome.runtime.lastError) {
          showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
          finishConversion();
          return;
        }
        extract();
      });
    } else {
      extract();
    }
  });
}

function finishConversion() {
  conversionInFlight = false;
  showSpinner(false);
}

// Extract content from the page based on mode
function extractPageContent(mode) {
  let content = '';
  const baseUrl = document.baseURI;
  const canonicalizeReferences = root => {
    const resolveWebReference = value => {
      if (!value || value.trim().startsWith('#')) return value;
      try {
        const resolved = new URL(value, baseUrl);
        return resolved.protocol === 'http:' || resolved.protocol === 'https:'
          ? resolved.href
          : value;
      } catch (_error) {
        return value;
      }
    };
    const references = [
      ['a', 'href'],
      ['area', 'href'],
      ['img', 'src'],
      ['source', 'src'],
      ['audio', 'src'],
      ['video', 'src'],
      ['video', 'poster']
    ];
    for (const [tagName, attribute] of references) {
      root.querySelectorAll(`${tagName}[${attribute}]`).forEach(element => {
        const value = element.getAttribute(attribute);
        const resolved = resolveWebReference(value);
        if (resolved !== value) element.setAttribute(attribute, resolved);
      });
    }
    root.querySelectorAll('img[srcset], source[srcset]').forEach(element => {
      const value = element.getAttribute('srcset');
      if (!value || /^data:/i.test(value.trim())) return;
      const candidates = value.split(',').map(candidate => {
        const parts = candidate.trim().split(/\s+/, 2);
        if (!parts[0]) return '';
        const resolved = resolveWebReference(parts[0]);
        return parts[1] ? `${resolved} ${parts[1]}` : resolved;
      });
      element.setAttribute('srcset', candidates.filter(Boolean).join(', '));
    });
  };

  switch(mode) {
    case 'full-page': {
      const clone = document.documentElement.cloneNode(true);
      canonicalizeReferences(clone);
      content = clone.outerHTML;
      break;
    }
    case 'selection': {
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const fragment = range.cloneContents();
        const div = document.createElement('div');
        div.appendChild(fragment);
        canonicalizeReferences(div);
        content = div.innerHTML;
      }
      break;
    }
    case 'article': {
      if (typeof Readability !== 'function') return '';
      const clone = document.cloneNode(true);
      const authoredTitleNode = clone.querySelector('article h1')
        || clone.querySelector('main h1')
        || clone.querySelector('h1');
      const authoredTitle = authoredTitleNode
        ?.textContent.trim().replace(/\s+/g, ' ') || '';
      clone.querySelectorAll('button h1, button h2, button h3, button h4, button h5, button h6')
        .forEach(heading => {
          const button = heading.closest('button');
          if (!button?.parentNode) return;
          const standaloneHeading = heading.cloneNode(true);
          standaloneHeading.removeAttribute('id');
          button.parentNode.insertBefore(standaloneHeading, button);
          heading.remove();
        });
      const article = new Readability(clone).parse();
      if (!article?.content) return '';
      const parsed = new DOMParser().parseFromString(article.content, 'text/html');
      canonicalizeReferences(parsed);
      const title = (authoredTitle || article.title || document.title || '').trim();
      const normalizedTitle = title.replace(/\s+/g, ' ');
      const hasTitleHeading = [...parsed.querySelectorAll('h1, h2')].some(heading => {
        return heading.textContent.trim().replace(/\s+/g, ' ') === normalizedTitle;
      });
      if (normalizedTitle && !hasTitleHeading) {
        const heading = parsed.createElement('h1');
        heading.textContent = normalizedTitle;
        parsed.body.prepend(heading);
      }
      content = parsed.body.innerHTML;
      break;
    }
  }

  return content;
}

// Convert HTML to Markdown using TurndownService
function convertToMarkdown(html) {
  return converter.convert(html);
}

// Handle the output based on selected action
function handleOutput(markdown, action, pageTitle) {
  switch(action) {
    case 'show':
      // Show in popup
      markdownResult.textContent = markdown;
      resultContainer.style.display = 'block';
      return Promise.resolve();
    case 'download':
      // Download as file
      return downloadMarkdown(markdown, pageTitle);
    case 'copy':
      // Copy to clipboard
      return navigator.clipboard.writeText(markdown).then(() => {
        showStatus('Copied to clipboard', 'success');
      }).catch(err => {
        showStatus('Failed to copy: ' + err, 'error');
        throw err;
      });
  }
}

// Download markdown as a file
function downloadMarkdown(
  markdown = null,
  pageTitle = 'page',
  downloadsApi = chrome.downloads,
  runtimeError = () => chrome.runtime.lastError?.message || null
) {
  // If markdown is not provided, use the one from the result container
  if (markdown === null || markdown === undefined) {
    markdown = markdownResult.textContent;
  }

  // Clean the filename
  let filename = pageTitle
    .toLowerCase()
    .replace(/[^\w\s]/gi, '')
    .replace(/\s+/g, '-')
    .substring(0, 50);

  filename = filename || 'converted-page';
  filename += '.md';

  // Create and trigger download
  const blob = new Blob([markdown], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);

  return new Promise((resolve, reject) => {
    downloadsApi.download({
      url: url,
      filename: filename,
      saveAs: false
    }, downloadId => {
      const error = runtimeError();
      if (error) {
        showStatus('Error saving file: ' + error, 'error');
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        reject(new Error(error));
        return;
      } else {
        showStatus('File saved', 'success');
      }

      setTimeout(() => URL.revokeObjectURL(url), 1000);
      resolve({ downloadId, error });
    });
  });
}

/**
 * Show status message to the user
 * @param {string} message - Message to display
 * @param {string} type - Message type (info, success, warning, error)
 */
function showStatus(message, type = 'info') {
  if (window.statusTimer) {
    clearTimeout(window.statusTimer);
    window.statusTimer = null;
  }

  statusMessage.textContent = message;

  // Reset styles
  statusMessage.className = '';
  statusMessage.style.color = '';

  // Add class based on message type
  statusMessage.classList.add(type);

  // Keep processing and error states visible until a later terminal status.
  if (['info', 'success', 'warning'].includes(type)) {
    const clearDelay = type === 'warning' ? 5000 : 3000;

    // Set new timer
    window.statusTimer = setTimeout(() => {
      statusMessage.textContent = '';
      statusMessage.className = '';
      window.statusTimer = null;
    }, clearDelay);
  }
}

// Show or hide the spinner
function showSpinner(show) {
  spinner.style.display = show ? 'block' : 'none';
  convertBtn.disabled = show;
}
