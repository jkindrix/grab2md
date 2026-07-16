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
const settingsModal = document.getElementById('settings-modal');
const closeModalBtn = document.querySelector('.close');
const saveSettingsBtn = document.getElementById('save-settings');
const resetDefaultsBtn = document.getElementById('reset-defaults');
const cliLink = document.getElementById('cli-link');

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
  },
  cliPath: ''
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

  document.getElementById('cli-path').value = settings.cliPath || '';

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

  // Settings button (opens modal)
  settingsBtn.addEventListener('click', () => {
    settingsModal.style.display = 'block';
  });

  // Close modal button
  closeModalBtn.addEventListener('click', () => {
    settingsModal.style.display = 'none';
  });

  // Also close when clicking outside the modal
  window.addEventListener('click', (event) => {
    if (event.target === settingsModal) {
      settingsModal.style.display = 'none';
    }
  });

  // Save settings button
  saveSettingsBtn.addEventListener('click', () => {
    updateSettingsFromForm();
    saveSettings();
    settingsModal.style.display = 'none';
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

  // CLI link
  cliLink.addEventListener('click', (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: 'https://github.com/jkindrix/html2md' });
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

  settings.cliPath = document.getElementById('cli-path').value;

  // Reinitialize Turndown with new settings
  initializeTurndown();
}

// Handle the conversion process
function handleConversion() {
  const conversionMode = conversionModeSelect.value;
  const trimContent = trimContentCheckbox.checked;
  const outputAction = outputActionSelect.value;

  // Special handling for element selection mode
  if (conversionMode === 'element') {
    activateElementSelector();
    return;
  }

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

/**
 * Activate element selector mode
 * Injects a content script that allows the user to visually select elements
 */
function activateElementSelector() {
  showStatus('Click on any element to convert it', 'info');

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs[0];

    // Inject element selector script
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      function: injectElementSelector,
      args: []
    })
    .then(() => {
      // Minimize the popup to show the page
      window.close();
    })
    .catch(error => {
      showStatus('Error: ' + error.message, 'error');
    });
  });
}

/**
 * Injects the element selector into the active page
 * This is injected as a content script
 */
function injectElementSelector() {
  // Exit if the selector is already active
  if (document.querySelector('#html2md-element-selector')) {
    return;
  }

  // Create styles for highlighting and overlays
  const style = document.createElement('style');
  style.id = 'html2md-selector-style';
  style.textContent = `
    .html2md-highlight {
      outline: 2px dashed #4f46e5 !important;
      outline-offset: 2px !important;
      background-color: rgba(99, 102, 241, 0.1) !important;
      transition: all 0.2s ease-in-out !important;
      cursor: pointer !important;
    }

    #html2md-selector-tooltip {
      position: fixed;
      background-color: #4f46e5;
      color: white;
      padding: 6px 10px;
      border-radius: 4px;
      font-size: 14px;
      font-family: system-ui, -apple-system, sans-serif;
      pointer-events: none;
      z-index: 2147483647;
      box-shadow: 0 2px 5px rgba(0,0,0,0.2);
      max-width: 300px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    #html2md-selector-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(0,0,0,0.5);
      z-index: 2147483646;
      display: flex;
      align-items: center;
      justify-content: center;
      opacity: 0;
      visibility: hidden;
      transition: all 0.3s ease;
    }

    #html2md-selector-modal {
      background-color: white;
      border-radius: 8px;
      padding: 20px;
      width: 300px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      font-family: system-ui, -apple-system, sans-serif;
    }

    #html2md-selector-modal h3 {
      margin-top: 0;
      margin-bottom: 15px;
      font-size: 18px;
      color: #333;
    }

    #html2md-selector-modal .html2md-buttons {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 15px;
    }

    #html2md-selector-modal button {
      padding: 8px 12px;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
    }

    #html2md-selector-modal .html2md-primary-button {
      background-color: #4f46e5;
      color: white;
    }

    #html2md-selector-modal .html2md-secondary-button {
      background-color: #e5e7eb;
      color: #374151;
    }
  `;
  document.head.appendChild(style);

  // Create tooltip
  const tooltip = document.createElement('div');
  tooltip.id = 'html2md-selector-tooltip';
  tooltip.style.display = 'none';
  document.body.appendChild(tooltip);

  // Create overlay for confirmation
  const overlay = document.createElement('div');
  overlay.id = 'html2md-selector-overlay';
  overlay.innerHTML = `
    <div id="html2md-selector-modal">
      <h3>Convert Element</h3>
      <p>Convert this element to Markdown?</p>
      <div class="html2md-buttons">
        <button class="html2md-secondary-button" id="html2md-cancel-btn">Cancel</button>
        <button class="html2md-primary-button" id="html2md-convert-btn">Convert</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  // Marker div to identify that selector is active
  const marker = document.createElement('div');
  marker.id = 'html2md-element-selector';
  marker.style.display = 'none';
  document.body.appendChild(marker);

  let currentElement = null;
  let previousElement = null;

  // Handle mousemove to highlight elements
  document.addEventListener('mousemove', function(e) {
    // Skip html2md elements
    if (e.target.id?.startsWith('html2md-') ||
        e.target.closest('#html2md-selector-modal')) {
      return;
    }

    const x = e.clientX;
    const y = e.clientY;
    currentElement = document.elementFromPoint(x, y);

    // Update tooltip position
    tooltip.style.left = `${x + 15}px`;
    tooltip.style.top = `${y + 15}px`;

    // Update tooltip content and highlight
    if (currentElement && currentElement !== previousElement) {
      // Remove highlight from previous element
      if (previousElement) {
        previousElement.classList.remove('html2md-highlight');
      }

      // Add highlight to current element
      currentElement.classList.add('html2md-highlight');
      previousElement = currentElement;

      // Update tooltip
      let elementType = currentElement.tagName.toLowerCase();
      if (currentElement.id) {
        elementType += `#${currentElement.id}`;
      } else if (currentElement.className) {
        const classNames = Array.from(currentElement.classList)
          .filter(c => !c.startsWith('html2md-'))
          .join('.');
        if (classNames) {
          elementType += `.${classNames}`;
        }
      }

      tooltip.textContent = elementType;
      tooltip.style.display = 'block';
    }
  });

  // Handle click to select an element
  document.addEventListener('click', function(e) {
    // Skip html2md elements
    if (e.target.id?.startsWith('html2md-') ||
        e.target.closest('#html2md-selector-modal')) {
      return;
    }

    e.preventDefault();
    e.stopPropagation();

    if (currentElement) {
      // Show confirmation
      overlay.style.opacity = '1';
      overlay.style.visibility = 'visible';

      // Store reference to the selected element
      window.html2mdSelectedElement = currentElement;
    }
  }, true);

  // Handle confirmation buttons
  document.getElementById('html2md-convert-btn').addEventListener('click', function() {
    const selectedElement = window.html2mdSelectedElement;

    if (selectedElement) {
      // Extract HTML content
      const htmlContent = selectedElement.outerHTML;

      // Send to background script for conversion
      chrome.runtime.sendMessage({
        action: 'convertElement',
        html: htmlContent,
        tag: selectedElement.tagName.toLowerCase(),
        title: document.title
      });
    }

    // Clean up
    cleanupSelector();
  });

  document.getElementById('html2md-cancel-btn').addEventListener('click', cleanupSelector);

  // Escape key to cancel
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      cleanupSelector();
    }
  });

  // Function to clean up selector
  function cleanupSelector() {
    // Hide overlay
    overlay.style.opacity = '0';
    overlay.style.visibility = 'hidden';

    // Remove highlight from current element
    if (currentElement) {
      currentElement.classList.remove('html2md-highlight');
    }

    // Hide tooltip
    tooltip.style.display = 'none';

    // Remove event listeners and elements after a short delay
    setTimeout(() => {
      document.head.removeChild(style);
      document.body.removeChild(tooltip);
      document.body.removeChild(overlay);
      document.body.removeChild(marker);

      delete window.html2mdSelectedElement;
    }, 300);
  }
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
    
    console.log('Already in transcript format, skipping conversion');
    
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
    
    console.log('ChatGPT conversation detected, using transcript converter');
    
    try {
      // We need to do some pre-cleaning before handing off to the transcript converter
      // This helps with issues where UI text gets mixed in at the HTML level
      const tempDiv = document.createElement('div');
      
      // Handle incomplete HTML by wrapping it in a proper structure if needed
      let processedHtml = html;
      
      // Check if the HTML is a partial fragment
      if (!html.trim().startsWith('<!DOCTYPE html>') && !html.trim().startsWith('<html')) {
        console.log('Detected HTML fragment, wrapping in proper HTML structure');
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
        
        console.log('Content is already in transcript format, cleaning up');
        return TranscriptConverter.cleanupExistingTranscript(cleanedHtml);
      }
      
      // Use the specialized transcript converter with pre-cleaned HTML
      // Check if we have the ChatGPT turndown service available
      let chatGPTMarkdown = '';
      if (typeof chatGPTTurndown !== 'undefined' && chatGPTTurndown) {
        try {
          console.log('Using ChatGPT specialized converter first');
          chatGPTMarkdown = chatGPTTurndown.turndown(cleanedHtml);
          console.log('ChatGPT converter preview:', chatGPTMarkdown.substring(0, 200) + '...');
        } catch (chatGPTError) {
          console.error('Error using chatGPT converter:', chatGPTError);
        }
      }
      
      // Then use the transcript converter to create the final structured output
      const result = TranscriptConverter.convert(chatGPTMarkdown || cleanedHtml);
      
      // Log the first 200 characters of the result for debugging
      console.log('Conversion result preview:', result.substring(0, 200) + '...');
      
      if (result && result.includes('# Conversation Transcript')) {
        // Make sure conversation structure is correct with additional clean up
        const finalResult = result
          .replace(/^(.*?)(---\s*title)/s, '$2');
        
        return finalResult;
      } else {
        console.error('Transcript converter returned invalid output');
        // Try to use the regular turndown service to convert the HTML
        try {
          return turndownService.turndown(cleanedHtml);
        } catch (turndownError) {
          console.error('Regular turndown also failed:', turndownError);
          
          // If that fails too, return a simple fallback
          return `# ChatGPT Conversation

Unable to fully convert the content. Try using the "Convert Selection" option if you're seeing this message.`;
        }
      }
    } catch (error) {
      console.error('Error using transcript converter:', error);
      console.error('Error details:', error.message);
      console.error('Error stack:', error.stack);
      
      // Try to use the simpler ChatGPTCleaner as a fallback
      try {
        console.log('Attempting to use ChatGPTCleaner as fallback');
        // Convert with regular turndown first
        const simpleTurndown = turndownService.turndown(html);
        // Then clean it up with the specialized cleaner
        const cleanedResult = ChatGPTCleaner.clean(simpleTurndown);
        
        // Add a subtle note about using fallback
        return `> ℹ️ *Note: Used fallback converter due to an issue with the primary converter.*

${cleanedResult}`;
      } catch (cleanerError) {
        console.error('Fallback cleaner also failed:', cleanerError);
        
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
      break;
    case 'download':
      // Download as file
      downloadMarkdown(markdown, pageTitle);
      break;
    case 'copy':
      // Copy to clipboard
      navigator.clipboard.writeText(markdown).then(() => {
        showStatus('Copied to clipboard', 'success');
      }).catch(err => {
        showStatus('Failed to copy: ' + err, 'error');
      });
      break;
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

  chrome.downloads.download({
    url: url,
    filename: filename,
    saveAs: true
  }, (downloadId) => {
    if (chrome.runtime.lastError) {
      showStatus('Error saving file: ' + chrome.runtime.lastError.message, 'error');
    } else {
      showStatus('File saved', 'success');
    }

    // Clean up the object URL
    setTimeout(() => URL.revokeObjectURL(url), 100);
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

/**
 * Handle URL scanning from the current page
 * Scans the page for URLs matching user-defined filters
 */
function handleUrlScan() {
  // Get URL capture settings from form
  const settings = getUrlCaptureSettings();

  // Show scanning status
  showStatus('Scanning page for URLs...', 'processing');
  showSpinner(true);

  // Get the active tab
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (!tabs || tabs.length === 0) {
      showStatus('Error: Could not get active tab', 'error');
      showSpinner(false);
      return;
    }

    const tab = tabs[0];

    // Inject script to scan for URLs
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: scanPageForUrls,
      args: [settings]
    })
    .then(results => {
      if (!results || !results[0] || !results[0].result) {
        throw new Error('Failed to get results from page scan');
      }

      const urls = results[0].result;

      if (urls.length === 0) {
        showStatus('No matching URLs found on the page', 'warning');
        showSpinner(false);
        return;
      }

      // Display the URLs in the UI
      displayUrls(urls);
      showStatus(`Found ${urls.length} URLs`, 'success');
      showSpinner(false);
    })
    .catch(error => {
      console.error('URL scanning error:', error);
      showStatus('Error scanning for URLs: ' + error.message, 'error');
      showSpinner(false);
    });
  });
}

/**
 * Get URL capture settings from the form
 * @returns {Object} URL capture settings
 */
function getUrlCaptureSettings() {
  return {
    urlFilter: document.getElementById('url-filter').value || '.*',
    onlyVisibleLinks: document.getElementById('only-visible-links').checked,
    skipMedia: document.getElementById('skip-media').checked,
    maxDepth: parseInt(document.getElementById('capture-depth').value, 10),
    domainOption: document.getElementById('domain-option').value,
    maxPages: parseInt(document.getElementById('max-pages').value, 10),
    trim: trimContentCheckbox.checked
  };
}

/**
 * Scan page for URLs matching specific criteria
 * @param {Object} settings - URL capture settings
 * @returns {Array} Array of URL objects
 */
function scanPageForUrls(settings) {
  const {urlFilter, onlyVisibleLinks, skipMedia, domainOption} = settings;

  /**
   * Check if an element is visible
   * @param {Element} element - DOM element to check
   * @returns {Boolean} True if element is visible
   */
  function isVisible(element) {
    // Fast path for obviously invisible elements
    if (!element.offsetParent && element.offsetWidth === 0 && element.offsetHeight === 0) {
      return false;
    }

    // Check computed style
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
      return false;
    }

    // Check if element is in viewport
    const rect = element.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) {
      return false;
    }

    return true;
  }

  /**
   * Check if a URL is a media file
   * @param {String} url - URL to check
   * @returns {Boolean} True if URL is a media file
   */
  function isMediaUrl(url) {
    const mediaExtensions = [
      // Images
      '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff',
      // Videos
      '.mp4', '.webm', '.ogg', '.mov', '.avi', '.wmv', '.flv', '.mkv',
      // Audio
      '.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a',
      // Documents
      '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp',
      // Archives
      '.zip', '.rar', '.tar', '.gz', '.7z'
    ];

    try {
      // Check if URL ends with one of the media extensions
      const urlObj = new URL(url);
      const path = urlObj.pathname.toLowerCase();
      return mediaExtensions.some(ext => path.endsWith(ext));
    } catch (e) {
      return false;
    }
  }

  /**
   * Check if a URL should be included based on domain options
   * @param {String} url - URL to check
   * @returns {Boolean} True if URL should be included
   */
  function shouldIncludeUrl(url) {
    try {
      const urlObj = new URL(url);
      const pageHostname = window.location.hostname;

      switch (domainOption) {
        case 'current-domain':
          // Only include URLs from the exact same domain
          return urlObj.hostname === pageHostname;

        case 'include-subdomains':
          // Include current domain and subdomains
          const pageDomain = getDomainFromHostname(pageHostname);
          const urlDomain = getDomainFromHostname(urlObj.hostname);
          return pageDomain === urlDomain;

        case 'any-domain':
          // Include all domains
          return true;

        default:
          return true;
      }
    } catch (e) {
      return false;
    }
  }

  /**
   * Extract domain from hostname
   * @param {String} hostname - Hostname to extract domain from
   * @returns {String} Domain name
   */
  function getDomainFromHostname(hostname) {
    const parts = hostname.split('.');
    if (parts.length <= 2) return hostname;

    // Get the last two parts (e.g., example.com from sub.example.com)
    return parts.slice(-2).join('.');
  }

  // Attempt to match URLs using the provided filter
  let urlRegex;
  try {
    urlRegex = new RegExp(urlFilter);
  } catch (e) {
    console.error('Invalid regex pattern:', e);
    urlRegex = /.*/; // Default to match all if invalid
  }

  // Get all links
  const links = document.querySelectorAll('a[href]');

  // Collection for found URLs
  const foundUrls = [];

  // Process each link
  links.forEach(link => {
    try {
      // Skip if link is not visible and onlyVisibleLinks is true
      if (onlyVisibleLinks && !isVisible(link)) return;

      // Get absolute URL
      const href = link.href;

      // Skip non-HTTP(S) links
      if (!href || !href.startsWith('http')) return;

      // Skip media files if skipMedia is true
      if (skipMedia && isMediaUrl(href)) return;

      // Apply domain filtering
      if (!shouldIncludeUrl(href)) return;

      // Apply regex filter
      if (urlRegex.test(href)) {
        // Get the link text or use the URL as fallback
        let linkText = link.textContent.trim();
        if (!linkText) {
          // Try to find any child image alt text to use as link description
          const img = link.querySelector('img[alt]');
          linkText = img && img.alt ? img.alt : href;
        }

        // Add URL with metadata
        foundUrls.push({
          url: href,
          text: linkText,
          isExternal: new URL(href).hostname !== window.location.hostname,
          sourcePage: window.location.href,
          discoveredAt: new Date().toISOString()
        });
      }
    } catch (error) {
      console.warn('Error processing link:', error);
    }
  });

  // Remove duplicates by URL
  const uniqueUrls = [];
  const seen = new Set();

  foundUrls.forEach(item => {
    if (!seen.has(item.url)) {
      seen.add(item.url);
      uniqueUrls.push(item);
    }
  });

  return uniqueUrls;
}

/**
 * Display URLs in the popup
 * @param {Array} urls - Array of URL objects
 */
function displayUrls(urls) {
  // Clear previous results
  urlList.innerHTML = '';

  // Update URL count
  urlCount.textContent = `(${urls.length})`;

  // Group URLs by domain for better organization
  const urlsByDomain = groupUrlsByDomain(urls);

  // Sort domains by count (descending)
  const sortedDomains = Object.keys(urlsByDomain).sort((a, b) => {
    return urlsByDomain[b].length - urlsByDomain[a].length;
  });

  // Create domain headers and URL items
  sortedDomains.forEach(domain => {
    const domainUrls = urlsByDomain[domain];

    // Create domain header
    const domainHeader = document.createElement('div');
    domainHeader.className = 'domain-header';
    domainHeader.innerHTML = `
      <div class="domain-name">${domain} <span class="domain-count">(${domainUrls.length})</span></div>
      <div class="domain-actions">
        <button class="small-button select-domain">Select All</button>
        <button class="small-button deselect-domain">Deselect All</button>
      </div>
    `;

    // Add header click handlers
    const selectDomainBtn = domainHeader.querySelector('.select-domain');
    const deselectDomainBtn = domainHeader.querySelector('.deselect-domain');

    selectDomainBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const checkboxes = domainUrls.map(url => document.getElementById(`url-${urls.indexOf(url)}`));
      checkboxes.forEach(checkbox => checkbox.checked = true);
    });

    deselectDomainBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const checkboxes = domainUrls.map(url => document.getElementById(`url-${urls.indexOf(url)}`));
      checkboxes.forEach(checkbox => checkbox.checked = false);
    });

    urlList.appendChild(domainHeader);

    // Create URL items for this domain
    domainUrls.forEach(urlItem => {
      const index = urls.indexOf(urlItem);
      const listItem = createUrlListItem(urlItem, index);
      urlList.appendChild(listItem);
    });
  });

  // Show results container
  urlResults.classList.remove('hidden');
}

/**
 * Group URLs by domain
 * @param {Array} urls - Array of URL objects
 * @returns {Object} Object with domains as keys and URL arrays as values
 */
function groupUrlsByDomain(urls) {
  const groups = {};

  urls.forEach(urlItem => {
    try {
      const domain = new URL(urlItem.url).hostname;
      if (!groups[domain]) {
        groups[domain] = [];
      }
      groups[domain].push(urlItem);
    } catch (e) {
      // Handle malformed URLs
      if (!groups['Other']) groups['Other'] = [];
      groups['Other'].push(urlItem);
    }
  });

  return groups;
}

/**
 * Create a list item for a URL
 * @param {Object} urlItem - URL object with metadata
 * @param {Number} index - Index in the URL array
 * @returns {Element} DOM element for the URL item
 */
function createUrlListItem(urlItem, index) {
  const listItem = document.createElement('div');
  listItem.className = 'url-item';

  // Create checkbox
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.id = `url-${index}`;
  checkbox.value = urlItem.url;
  checkbox.dataset.index = index;
  checkbox.checked = true; // Default to checked

  // Create label with URL info
  const label = document.createElement('label');
  label.htmlFor = `url-${index}`;

  // URL text
  const urlText = document.createElement('span');
  urlText.className = 'url-text';
  urlText.textContent = urlItem.text;

  // URL itself
  const urlLink = document.createElement('span');
  urlLink.className = 'url-link';

  // Truncate URL for display if too long
  let displayUrl = urlItem.url;
  if (displayUrl.length > 50) {
    displayUrl = displayUrl.substring(0, 47) + '...';
  }
  urlLink.textContent = displayUrl;
  urlLink.title = urlItem.url; // Show full URL on hover

  // Add badge for external links
  if (urlItem.isExternal) {
    const badge = document.createElement('span');
    badge.className = 'external-badge';
    badge.textContent = 'external';
    urlLink.appendChild(badge);
  }

  // Add control buttons (preview, copy)
  const controls = document.createElement('div');
  controls.className = 'url-controls';

  // Preview button
  const previewBtn = document.createElement('button');
  previewBtn.className = 'url-control-btn preview-btn';
  previewBtn.title = 'Preview this URL';
  previewBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>';

  previewBtn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    chrome.tabs.create({ url: urlItem.url, active: false });
  });

  controls.appendChild(previewBtn);

  // Assemble the label
  label.appendChild(urlText);
  label.appendChild(urlLink);
  label.appendChild(controls);

  // Add to list item
  listItem.appendChild(checkbox);
  listItem.appendChild(label);

  return listItem;
}

/**
 * Handle capturing selected URLs
 * Processes selected URLs with batch conversion
 */
function handleCaptureSelected() {
  // Get selected URLs
  const selectedCheckboxes = document.querySelectorAll('.url-item input[type="checkbox"]:checked');
  const urls = Array.from(selectedCheckboxes).map(checkbox => checkbox.value);

  if (urls.length === 0) {
    showStatus('No URLs selected', 'warning');
    return;
  }

  // Hide URL results and show progress
  urlResults.classList.add('hidden');
  captureProgress.classList.remove('hidden');

  // Get conversion options
  const options = {
    trim: trimContentCheckbox.checked,
    output: 'download'
  };

  // Start batch processing
  chrome.runtime.sendMessage({
    action: 'batchConvertUrls',
    urls: urls,
    options: options
  }, handleBatchResponse);

  // Initialize progress tracking
  window.captureInProgress = true;
  updateProgress(0, urls.length);

  // Listen for progress updates
  chrome.runtime.onMessage.addListener(progressListener);
}

/**
 * Handle batch processing response
 * @param {Object} response - Response object from background script
 */
function handleBatchResponse(response) {
  // Clean up listener
  chrome.runtime.onMessage.removeListener(progressListener);
  window.captureInProgress = false;

  // Hide progress container
  captureProgress.classList.add('hidden');

  if (response && response.success) {
    showStatus(`Converted ${response.processed} of ${response.total} URLs`, 'success');

    // Show failures if any
    const failures = response.results.filter(r => !r.success);
    if (failures.length > 0) {
      console.warn('Failed to convert these URLs:', failures);

      // Maybe display failures to user
      if (failures.length > 0) {
        const failureMsg = `${failures.length} URL${failures.length > 1 ? 's' : ''} failed to convert. Check console for details.`;
        setTimeout(() => showStatus(failureMsg, 'warning'), 3000);
      }
    }
  } else {
    showStatus('Error processing batch conversion', 'error');
  }
}

/**
 * Progress update listener for batch processing
 * @param {Object} message - Message from background script
 */
function progressListener(message) {
  if (message.action === 'batchProgress' && window.captureInProgress) {
    updateProgress(message.current, message.total);

    // Update status text with current URL
    let currentUrl = message.url;
    if (currentUrl && currentUrl.length > 40) {
      currentUrl = currentUrl.substring(0, 37) + '...';
    }

    progressStatus.textContent = `Processing ${message.current}/${message.total}: ${currentUrl || ''}`;
  }
}

/**
 * Update progress bar
 * @param {Number} current - Current progress
 * @param {Number} total - Total items
 */
function updateProgress(current, total) {
  const percentage = Math.min(100, Math.round((current / total) * 100));
  progressBar.style.width = `${percentage}%`;
  progressBar.setAttribute('aria-valuenow', percentage);
  progressStatus.textContent = `Processing ${current}/${total}`;
}

/**
 * Stop URL capture process
 * Cancels the current batch operation
 */
function stopCapture() {
  window.captureInProgress = false;
  chrome.runtime.onMessage.removeListener(progressListener);

  captureProgress.classList.add('hidden');
  showStatus('Capture process stopped', 'warning');

  // Notify background script to stop processing (if implemented)
  chrome.runtime.sendMessage({ action: 'stopBatchProcess' });
}
