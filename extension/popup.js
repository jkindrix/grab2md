// DOM Elements
const convertBtn = document.getElementById('convert-btn');
const settingsBtn = document.getElementById('settings-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const conversionModeSelect = document.getElementById('conversion-mode');
const trimContentCheckbox = document.getElementById('trim-content');
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
    linkStyle: 'inline',
    bulletMarker: '-',
  },
  contentOptions: {
    preserveImages: true,
    includeTables: true,
    codeBlocks: true,
    inlineLinks: true,
    enableChatGPTMode: true
  }
};

// Current settings - will be loaded from storage
let settings = {...defaultSettings};

// Initialize TurndownService for HTML to Markdown conversion
let turndownService;

// Initialize ChatGPT specialized converter
let chatGPTTurndown;

// Initialize the extension
document.addEventListener('DOMContentLoaded', () => {
  // Load saved settings
  loadSettings();

  // Initialize the UI
  initializeUI();

  // Set up event listeners
  setupEventListeners();
});

// Load saved settings from Chrome storage
function loadSettings() {
  chrome.storage.sync.get('html2mdSettings', (data) => {
    if (data.html2mdSettings) {
      settings = {...defaultSettings, ...data.html2mdSettings};
    }

    // Apply loaded settings to the UI
    applySettings();
  });
}

// Save settings to Chrome storage
function saveSettings() {
  chrome.storage.sync.set({ html2mdSettings: settings }, () => {
    showStatus('Settings saved', 'success');
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
  document.getElementById('link-style').value = settings.markdownOptions.linkStyle;
  document.getElementById('bullet-marker').value = settings.markdownOptions.bulletMarker;

  document.getElementById('preserve-images').checked = settings.contentOptions.preserveImages;
  document.getElementById('include-tables').checked = settings.contentOptions.includeTables;
  document.getElementById('code-blocks').checked = settings.contentOptions.codeBlocks;
  document.getElementById('inline-links').checked = settings.contentOptions.inlineLinks;
  document.getElementById('enable-chatgpt-mode').checked = settings.contentOptions.enableChatGPTMode;

  // Initialize Turndown with current settings
  initializeTurndown();
}

// Initialize the Turndown service with current settings
function initializeTurndown() {
  // Standard TurndownService configuration
  const turndownOptions = {
    headingStyle: settings.markdownOptions.headingStyle,
    bulletListMarker: settings.markdownOptions.bulletMarker,
    linkStyle: settings.markdownOptions.linkStyle,
    codeBlockStyle: settings.contentOptions.codeBlocks ? 'fenced' : 'indented'
  };
  
  // Create the standard TurndownService
  turndownService = new TurndownService(turndownOptions);
  
  // Initialize ChatGPT specialized converter if available
  if (typeof ChatGPTTurndownService !== 'undefined') {
    chatGPTTurndown = new ChatGPTTurndownService(turndownOptions);
  }

  // Configure Turndown based on settings
  if (!settings.contentOptions.preserveImages) {
    turndownService.remove('img');
  }

  if (settings.contentOptions.includeTables) {
    turndownService.keep(['table', 'tr', 'td', 'th', 'thead', 'tbody']);
  }
  
  // Add ChatGPT-specific rules to handle code blocks better
  turndownService.addRule('codeBlock', {
    filter: function(node) {
      // Detect code blocks by structure or class
      return (
        (node.nodeName === 'PRE' && node.firstChild && node.firstChild.nodeName === 'CODE') ||
        (node.nodeName === 'DIV' && node.classList && 
         (node.classList.contains('code-block') || 
          node.classList.contains('whitespace-pre') ||
          node.classList.contains('bg-black')))
      );
    },
    replacement: function(content, node, options) {
      // Try to detect language
      let language = '';
      
      // Check classes for language
      if (node.className && node.className.includes('language-')) {
        const match = node.className.match(/language-(\w+)/);
        if (match) language = match[1];
      }
      
      // Check child classes
      if (!language && node.firstChild && node.firstChild.className) {
        const match = node.firstChild.className.match(/language-(\w+)/);
        if (match) language = match[1];
      }
      
      // Clean up content and return as code block
      content = content.trim();
      
      return '\n\n```' + language + '\n' + content + '\n```\n\n';
    }
  });
}

// Initialize UI elements
function initializeUI() {
  // Set chrome extension version in the CLI link
  chrome.management.getSelf((info) => {
    cliLink.setAttribute('title', `Download HTML2MD CLI Tool v${info.version}`);
  });
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
      settings = {...defaultSettings};
      applySettings();
      saveSettings();
      showStatus('Settings reset to defaults', 'success');
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
    downloadMarkdown();
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
    linkStyle: document.getElementById('link-style').value,
    bulletMarker: document.getElementById('bullet-marker').value
  };

  settings.contentOptions = {
    preserveImages: document.getElementById('preserve-images').checked,
    includeTables: document.getElementById('include-tables').checked,
    codeBlocks: document.getElementById('code-blocks').checked,
    inlineLinks: document.getElementById('inline-links').checked,
    enableChatGPTMode: document.getElementById('enable-chatgpt-mode').checked
  };

  // Reinitialize Turndown with new settings
  initializeTurndown();
}

// Handle the conversion process
function handleConversion() {
  const conversionMode = conversionModeSelect.value;
  const trimContent = trimContentCheckbox.checked;
  const outputAction = outputActionSelect.value;

  showStatus('Converting...', 'processing');
  showSpinner(true);

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    // Inject content script to extract HTML
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: extractPageContent,
      args: [conversionMode, trimContent]
    }, (results) => {
      if (chrome.runtime.lastError) {
        showStatus('Error: ' + chrome.runtime.lastError.message, 'error');
        showSpinner(false);
        return;
      }

      const extractedContent = results[0].result;

      if (!extractedContent) {
        showStatus('Error: Could not extract content', 'error');
        showSpinner(false);
        return;
      }
      
      const htmlContent = Html2MdConversionUtils.normalizeExtractedHtml(extractedContent);

      // Convert HTML to Markdown
      const markdown = convertToMarkdown(htmlContent, trimContent);

      // Handle the output based on user selection
      handleOutput(markdown, outputAction, tab.title);

      showStatus('Conversion complete', 'success');
      showSpinner(false);
    });
  });
}

// Extract content from the page based on mode
function extractPageContent(mode, trim) {
  let content = '';

  switch(mode) {
    case 'full-page':
      content = document.documentElement.outerHTML;
      break;
    case 'selection':
      const selection = window.getSelection();
      if (selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        const fragment = range.cloneContents();
        const div = document.createElement('div');
        div.appendChild(fragment);
        content = div.innerHTML;
      } else {
        content = document.documentElement.outerHTML;
      }
      break;
    case 'article':
      // Try to find the main content
      const article = document.querySelector('article') ||
                      document.querySelector('main') ||
                      document.querySelector('.post-content') ||
                      document.querySelector('.article-content') ||
                      document.querySelector('#content');

      if (article) {
        content = article.outerHTML;
      } else {
        // If no main content container is found, use the full page
        content = document.documentElement.outerHTML;
      }
      break;
  }

  return content;
}

// Convert HTML to Markdown using TurndownService
function convertToMarkdown(html, trim) {
  // Perform any pre-processing if trim is enabled
  if (trim) {
    // Simple trimming: remove scripts, styles, nav, footer, etc.
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;

    // Remove unwanted elements
    const elementsToRemove = [
      'script', 'style', 'iframe', 'noscript',
      'nav:not([role="navigation"])',
      'footer',
      '[role="complementary"]',
      '[role="banner"]',
      '.sidebar', '.widget', '.cookie-notice',
      '#comments', '.comments', '.related-posts',
      'aside', '.ad', '.advertisement', '.social-share',
      '.navigation', '.pagination'
    ];

    elementsToRemove.forEach(selector => {
      try {
        tempDiv.querySelectorAll(selector).forEach(el => {
          el.remove();
        });
      } catch (e) {
        // Ignore errors from invalid selectors
      }
    });

    html = tempDiv.innerHTML;
  }

  // Convert to markdown using the standard converter
  let markdown = turndownService.turndown(html);
  
  // Check if this is content that's already been converted to our transcript format
  if (html.includes('title: "ChatGPT Conversation Transcript"') && 
      html.includes('format: "transcript-v1.0"') &&
      html.includes('# Conversation Transcript')) {
    
    Html2MdLogger.debug('Already in transcript format, skipping conversion');
    
    // Just clean up any extra/duplicate metadata
    if (html.match(/---\s*title.*?---/g)?.length > 1) {
      // If there are multiple frontmatter blocks, keep only the first one
      html = html.replace(/(---\s*title.*?---)([\s\S]*?)(---\s*title.*?---)/s, '$1$2');
    }
    
    // Make sure we only have one main title
    if (html.match(/# Conversation Transcript/g)?.length > 1) {
      html = html.replace(/# Conversation Transcript/, '').trim();
      html = html.replace(/---\s*title.*?---\s*/s, match => match + '\n# Conversation Transcript\n\n');
    }
    
    return html;
  }
  
  // Check if this is a ChatGPT conversation and we should use the transcript converter
  if (settings.contentOptions.enableChatGPTMode && 
      (TranscriptConverter.isChatGPT(html) || 
       (typeof window !== 'undefined' && 
        (window.location.href.includes('chatgpt.com') || 
         window.location.href.includes('chat.openai.com'))))) {
    
    Html2MdLogger.debug('ChatGPT conversation detected, using transcript converter');
    
    try {
      // We need to do some pre-cleaning before handing off to the transcript converter
      // This helps with issues where UI text gets mixed in at the HTML level
      const tempDiv = document.createElement('div');
      
      // Handle incomplete HTML by wrapping it in a proper structure if needed
      let processedHtml = html;
      
      // Check if the HTML is a partial fragment
      if (!html.trim().startsWith('<!DOCTYPE html>') && !html.trim().startsWith('<html')) {
        Html2MdLogger.debug('Detected HTML fragment, wrapping in proper HTML structure');
        processedHtml = `<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body>${html}</body></html>`;
      }
      
      tempDiv.innerHTML = processedHtml;

      // Remove specific ChatGPT UI elements that commonly cause problems
      const removeSelectors = [
        // Page UI elements
        'title', 'header', 'footer', 'nav', 'aside', 
        // Common ChatGPT UI elements 
        '[role="banner"]', '[role="navigation"]', '[role="complementary"]',
        '.flex-shrink-0', '.self-end', '.text-gray-400', '.text-gray-600',
        '.text-gray-500', '.text-xs', '.text-sm', '.py-2', '.px-3',
        '[data-testid="search-box"]', '[data-testid="send-button"]',
        '[data-testid="model-switcher"]', '[data-testid="chat-sidebar"]',
        '[aria-label="Menu"]', '[data-testid="copy-button"]',
        // Model indicator, buttons, etc.
        'button', '.toast', '.modal', '.cookie-banner', '.alert',
        '.buttons', '.actionbar', '.input-panel', '.toolbar', '.navigation',
        '.pagination', '.search-results', '.menu-dropdown', '.settings',
        '.skip-link', '.chat-history', '.main-header', '.main-footer',
        // More specific ChatGPT UI elements
        '.sticky', '.pointer-events-auto', '.chat-message-actions',
        '.chat-message-edit-buttons'
      ];
      
      removeSelectors.forEach(selector => {
        try {
          const elements = tempDiv.querySelectorAll(selector);
          elements.forEach(el => el.remove());
        } catch (e) { /* Ignore invalid selectors */ }
      });

      // Handle code blocks better at HTML level
      const codeElements = tempDiv.querySelectorAll('pre, code, .code-block, [class*="bg-black"], [class*="whitespace-pre"]');
      codeElements.forEach(codeEl => {
        // Remove any "Copy" or "Edit" buttons inside or near code blocks
        const nearbyButtons = codeEl.querySelectorAll('button');
        nearbyButtons.forEach(btn => btn.remove());
        
        // Make sure code content is preserved properly
        if (codeEl.innerHTML) {
          // Preserve line breaks and spaces in code
          codeEl.innerHTML = codeEl.innerHTML.replace(/<br\s*\/?>/gi, '\n');
        }
      });

      // DOM selectors remove UI without rewriting user-authored text.
      const cleanedHtml = tempDiv.innerHTML.replace(/\n{3,}/g, '\n\n');
      
      // First check if this content is already in our transcript format
      if (cleanedHtml.includes('title: "ChatGPT Conversation Transcript"') && 
          cleanedHtml.includes('format: "transcript-v1.0"') &&
          cleanedHtml.includes('# Conversation Transcript')) {
        
        Html2MdLogger.debug('Content is already in transcript format, cleaning up');
        return TranscriptConverter.cleanupExistingTranscript(cleanedHtml);
      }
      
      // Use the specialized transcript converter with pre-cleaned HTML
      // Check if we have the ChatGPT turndown service available
      let chatGPTMarkdown = '';
      if (typeof chatGPTTurndown !== 'undefined' && chatGPTTurndown) {
        try {
          Html2MdLogger.debug('Using ChatGPT specialized converter first');
          chatGPTMarkdown = chatGPTTurndown.turndown(cleanedHtml);
          Html2MdLogger.debug('ChatGPT converter preview:', chatGPTMarkdown.substring(0, 200) + '...');
        } catch (chatGPTError) {
          Html2MdLogger.error('Error using chatGPT converter:', chatGPTError);
        }
      }
      
      // Then use the transcript converter to create the final structured output
      const result = TranscriptConverter.convert(chatGPTMarkdown || cleanedHtml);
      
      // Log the first 200 characters of the result for debugging
      Html2MdLogger.debug('Conversion result preview:', result.substring(0, 200) + '...');
      
      if (result && result.includes('# Conversation Transcript')) {
        // Make sure conversation structure is correct with additional clean up
        const finalResult = result
          .replace(/^(.*?)(---\s*title)/s, '$2');
        
        return finalResult;
      } else {
        Html2MdLogger.error('Transcript converter returned invalid output');
        // Try to use the regular turndown service to convert the HTML
        try {
          return turndownService.turndown(cleanedHtml);
        } catch (turndownError) {
          Html2MdLogger.error('Regular turndown also failed:', turndownError);
          
          // If that fails too, return a simple fallback
          return `# ChatGPT Conversation

Unable to fully convert the content. Try using the "Convert Selection" option if you're seeing this message.`;
        }
      }
    } catch (error) {
      Html2MdLogger.error('Error using transcript converter:', error);
      Html2MdLogger.error('Error details:', error.message);
      Html2MdLogger.error('Error stack:', error.stack);
      
      // Try to use the simpler ChatGPTCleaner as a fallback
      try {
        Html2MdLogger.debug('Attempting to use ChatGPTCleaner as fallback');
        // Convert with regular turndown first
        const simpleTurndown = turndownService.turndown(html);
        // Then clean it up with the specialized cleaner
        const cleanedResult = ChatGPTCleaner.clean(simpleTurndown);
        
        // Add a subtle note about using fallback
        return `> ℹ️ *Note: Used fallback converter due to an issue with the primary converter.*

${cleanedResult}`;
      } catch (cleanerError) {
        Html2MdLogger.error('Fallback cleaner also failed:', cleanerError);
        
        // Last resort - just use regular turndown
        const fallbackResult = turndownService.turndown(html);
        
        // Add warning about fallback conversion
        return `> ⚠️ **Note**: The ChatGPT specialized converter encountered an error and fell back to standard conversion.
> This may result in less optimal formatting. Please report this issue.

${fallbackResult}`;
      }
    }
  }

  return markdown;
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
function downloadMarkdown(markdown = null, pageTitle = 'page') {
  // If markdown is not provided, use the one from the result container
  if (!markdown) {
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

  return new Promise(resolve => {
    chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: false
    }, downloadId => {
      const error = chrome.runtime.lastError?.message || null;
      if (error) {
        showStatus('Error saving file: ' + error, 'error');
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
  statusMessage.textContent = message;

  // Reset styles
  statusMessage.className = '';
  statusMessage.style.color = '';

  // Add class based on message type
  statusMessage.classList.add(type);

  // Auto-clear status after some time for non-error messages
  if (type !== 'error') {
    const clearDelay = type === 'warning' ? 5000 : 3000;

    // Clear any existing timers
    if (window.statusTimer) {
      clearTimeout(window.statusTimer);
    }

    // Set new timer
    window.statusTimer = setTimeout(() => {
      statusMessage.textContent = '';
      statusMessage.className = '';
    }, clearDelay);
  }
}

// Show or hide the spinner
function showSpinner(show) {
  spinner.style.display = show ? 'block' : 'none';
}
