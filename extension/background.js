/**
 * HTML2MD Chrome Extension - Background Script
 * Handles context menu setup, event listeners, and conversion functions
 */

// Constants for menu item IDs and configurations
const MENU_ITEMS = {
  CONVERT_PAGE: "convert-page",
  CONVERT_SELECTION: "convert-selection",
  CAPTURE_LINKS: "capture-links",
  SEPARATOR: "separator",
  OPEN_SETTINGS: "open-settings"
};

const CONVERSION_MODES = {
  FULL_PAGE: "full-page",
  SELECTION: "selection",
  ARTICLE: "article"
};

const OUTPUT_TYPES = {
  DOWNLOAD: "download",
  COPY: "copy",
  SHOW: "show"
};

/**
 * Initialize context menu items when extension is installed
 */
chrome.runtime.onInstalled.addListener(() => {
  // Create context menu items
  chrome.contextMenus.create({
    id: MENU_ITEMS.CONVERT_PAGE,
    title: "Convert page to Markdown",
    contexts: ["page"]
  });

  chrome.contextMenus.create({
    id: MENU_ITEMS.CONVERT_SELECTION,
    title: "Convert selection to Markdown",
    contexts: ["selection"]
  });

  chrome.contextMenus.create({
    id: MENU_ITEMS.CAPTURE_LINKS,
    title: "Capture Links from Page",
    contexts: ["page"]
  });

  chrome.contextMenus.create({
    id: MENU_ITEMS.SEPARATOR,
    type: "separator",
    contexts: ["page", "selection"]
  });

  chrome.contextMenus.create({
    id: MENU_ITEMS.OPEN_SETTINGS,
    title: "Open HTML2MD settings",
    contexts: ["page", "selection"]
  });
});

/**
 * Handle clicks on the extension icon in the toolbar
 */
chrome.action.onClicked.addListener((tab) => {
  if (tab) {
    convertWithOptions({
      mode: CONVERSION_MODES.FULL_PAGE,
      output: OUTPUT_TYPES.DOWNLOAD
    }, tab);
  }
});

/**
 * Handle keyboard shortcuts
 */
chrome.commands.onCommand.addListener((command) => {
  if (command === "convert_selection") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length > 0) {
        convertWithOptions({
          mode: CONVERSION_MODES.SELECTION,
          output: OUTPUT_TYPES.COPY
        }, tabs[0]);
      }
    });
  }
});

/**
 * Handle context menu clicks
 */
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab) return;

  switch (info.menuItemId) {
    case MENU_ITEMS.CONVERT_PAGE:
      convertWithOptions({
        mode: CONVERSION_MODES.FULL_PAGE,
        output: OUTPUT_TYPES.DOWNLOAD
      }, tab);
      break;

    case MENU_ITEMS.CONVERT_SELECTION:
      convertWithOptions({
        mode: CONVERSION_MODES.SELECTION,
        output: OUTPUT_TYPES.COPY
      }, tab);
      break;

    case MENU_ITEMS.CAPTURE_LINKS:
      openPopupToUrlCapture();
      break;

    case MENU_ITEMS.OPEN_SETTINGS:
      chrome.tabs.create({
        url: chrome.runtime.getURL("popup.html?settings=true")
      });
      break;
  }
});

/**
 * Open the popup and navigate to URL capture tab
 */
function openPopupToUrlCapture() {
  chrome.action.openPopup();
  // Need to wait for popup to load before sending message
  setTimeout(() => {
    chrome.runtime.sendMessage({ action: "openUrlCaptureTab" });
  }, 200);
}

/**
 * Convert content with given options
 * @param {Object} options - Conversion options
 * @param {string} options.mode - Conversion mode (full-page, selection, article)
 * @param {string} options.output - Output type (download, copy, show)
 * @param {Object} tab - Chrome tab object
 */
function convertWithOptions(options, tab) {
  if (!tab) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs.length > 0) {
        executeConversion(options, tabs[0]);
      }
    });
  } else {
    executeConversion(options, tab);
  }
}

/**
 * Execute the HTML to Markdown conversion process
 * @param {Object} options - Conversion options
 * @param {Object} tab - Chrome tab object
 */
function executeConversion(options, tab) {
  // First load user settings
  chrome.storage.sync.get('html2mdSettings', (data) => {
    const settings = data.html2mdSettings || {};
    const trimContent = settings.trim !== undefined ? settings.trim : true;

    try {
      // Step 1: Extract HTML content from the page
      extractContentFromTab(tab, options.mode, trimContent)
        .then(htmlContent => {
          // Step 2: Convert HTML to Markdown
          return convertHtmlToMarkdown(tab, htmlContent, trimContent, settings);
        })
        .then(markdown => {
          // Step 3: Handle the output (download, copy, etc.)
          handleOutput(markdown, options.output, tab);
        })
        .catch(error => {
          console.error("Conversion error:", error);
          showErrorNotification(tab, error.message || "An error occurred during conversion");
        });
    } catch (error) {
      console.error("Fatal error in conversion process:", error);
      showErrorNotification(tab, "A fatal error occurred");
    }
  });
}

/**
 * Extract HTML content from a tab based on specified mode
 * @param {Object} tab - Chrome tab object
 * @param {string} mode - Extraction mode (full-page, selection, article)
 * @param {boolean} trim - Whether to trim content
 * @returns {Promise<string>} - Promise resolving to HTML content
 */
function extractContentFromTab(tab, mode, trim) {
  return new Promise((resolve, reject) => {
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractPageContent,
      args: [mode, trim]
    }, (results) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }

      if (!results || !results[0]) {
        reject(new Error("Failed to extract content"));
        return;
      }

      resolve(results[0].result);
    });
  });
}

/**
 * Convert HTML content to Markdown
 * @param {Object} tab - Chrome tab object
 * @param {string} htmlContent - HTML content to convert
 * @param {boolean} trimContent - Whether to trim content
 * @param {Object} settings - User settings
 * @returns {Promise<string>} - Promise resolving to markdown content
 */
function convertHtmlToMarkdown(tab, htmlContent, trimContent, settings) {
  return new Promise((resolve, reject) => {
    // First inject turndown.js library
    chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["turndown.js"]
    }, () => {
      if (chrome.runtime.lastError) {
        reject(new Error("Failed to load Turndown: " + chrome.runtime.lastError.message));
        return;
      }

      // Then convert HTML to Markdown
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: convertToMarkdown,
        args: [htmlContent, trimContent, settings]
      }, (conversionResults) => {
        if (chrome.runtime.lastError) {
          reject(new Error("Conversion error: " + chrome.runtime.lastError.message));
          return;
        }

        if (!conversionResults || !conversionResults[0]) {
          reject(new Error("Conversion failed"));
          return;
        }

        resolve(conversionResults[0].result);
      });
    });
  });
}

/**
 * Extract content from the page based on mode (injected into the page)
 * @param {string} mode - Extraction mode
 * @param {boolean} trim - Whether to trim content
 * @returns {string} - Extracted HTML content
 */
function extractPageContent(mode, trim) {
  let content = '';
  const currentUrl = window.location.href;

  try {
    // Handle ChatGPT differently
    if (currentUrl.includes('chatgpt.com/c/')) {
      return extractChatGptContent();
    }

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
          // Fallback to full page if no selection
          content = document.documentElement.outerHTML;
        }
        break;

      case 'article':
        // Try to find the main content using common selectors
        const mainSelectors = [
          'article', 'main',
          '[role="main"]',
          '.post-content', '.article-content', '.entry-content',
          '#content', '#main-content', '.main-content',
          '.post', '.article', '.entry'
        ];

        // Find the first matching element
        let article = null;
        for (const selector of mainSelectors) {
          article = document.querySelector(selector);
          if (article) break;
        }

        if (article) {
          content = article.outerHTML;
        } else {
          // If no main content container is found, use the full page
          content = document.documentElement.outerHTML;
        }
        break;
    }

    return content;
  } catch (error) {
    console.error("Error extracting page content:", error);
    return document.documentElement.outerHTML;
  }
}

/**
 * Extract content specifically from ChatGPT conversation page
 * @returns {string} - Extracted HTML content optimized for ChatGPT
 */
function extractChatGptContent() {
  try {
    // Target the main thread container
    const mainThread = document.querySelector('main .group');
    if (!mainThread) return document.documentElement.outerHTML;

    // Create a container for the processed content
    const processedContent = document.createElement('div');

    // Get all the message blocks
    const messageBlocks = document.querySelectorAll('main .group');

    // Process each message block
    messageBlocks.forEach(block => {
      // Determine if it's a user message or assistant message
      const isUserMessage = block.querySelector('.items-end');
      const messageContent = block.querySelector('.markdown');

      if (!messageContent) return;

      // Create a new message element
      const messageElement = document.createElement('div');
      messageElement.className = isUserMessage ? 'user-message' : 'assistant-message';

      // Clone the markdown content to preserve structure
      const contentClone = messageContent.cloneNode(true);

      // Fix code blocks - ChatGPT has unconventional code block structure
      const codeBlocks = contentClone.querySelectorAll('pre');
      codeBlocks.forEach(codeBlock => {
        // Ensure code blocks have proper structure
        const codeElement = codeBlock.querySelector('code');
        if (codeElement) {
          // Standardize the code block format
          const language = (codeElement.className.match(/language-(\w+)/) || [null, ''])[1];
          const codeContent = codeElement.textContent;

          // Replace with a more standard structure
          const newCode = document.createElement('code');
          newCode.className = language ? `language-${language}` : '';
          newCode.textContent = codeContent;

          const newPre = document.createElement('pre');
          newPre.appendChild(newCode);
          codeBlock.parentNode.replaceChild(newPre, codeBlock);
        }
      });

      // Add the processed content to the message
      messageElement.appendChild(contentClone);

      // Add the message to the processed content
      processedContent.appendChild(messageElement);

      // Add separator between messages
      const separator = document.createElement('hr');
      processedContent.appendChild(separator);
    });

    return processedContent.outerHTML;
  } catch (error) {
    console.error("Error extracting ChatGPT content:", error);
    return document.documentElement.outerHTML;
  }
}

/**
 * Convert HTML to Markdown (injected into the page)
 * @param {string} html - HTML content to convert
 * @param {boolean} trim - Whether to trim content
 * @param {Object} settings - User settings
 * @returns {string} - Converted markdown content
 */
function convertToMarkdown(html, trim, settings) {
  // Make sure TurndownService is available
  if (typeof TurndownService === 'undefined') {
    console.error('TurndownService is not defined');
    return 'Error: TurndownService is not available';
  }

  try {
    // Perform content trimming if enabled
    if (trim) {
      html = trimHtmlContent(html);
    }

    // Initialize TurndownService with settings
    const turndownOptions = {
      headingStyle: (settings?.markdownOptions?.headingStyle) || 'atx',
      bulletListMarker: (settings?.markdownOptions?.bulletMarker) || '-',
      linkStyle: (settings?.markdownOptions?.linkStyle) || 'inlined',
      codeBlockStyle: (settings?.contentOptions?.codeBlocks) ? 'fenced' : 'indented'
    };

    const turndownService = new TurndownService(turndownOptions);

    // Configure Turndown based on settings
    if (settings?.contentOptions?.preserveImages === false) {
      turndownService.remove('img');
    }

    // Add custom rules if needed
    if (settings?.contentOptions?.includeTables === false) {
      turndownService.remove('table');
    }

    // Convert HTML to Markdown
    return turndownService.turndown(html);
  } catch (error) {
    console.error("Error converting to markdown:", error);
    return "Error converting to markdown: " + error.message;
  }
}

/**
 * Trim HTML content by removing unwanted elements
 * @param {string} html - HTML content to trim
 * @returns {string} - Trimmed HTML content
 */
function trimHtmlContent(html) {
  // Create temporary div to manipulate the HTML
  const tempDiv = document.createElement('div');
  tempDiv.innerHTML = html;

  // Elements to remove from the content
  const elementsToRemove = [
    // Scripts, styles, and technical elements
    'script', 'style', 'iframe', 'noscript',

    // Navigation and UI elements
    'nav:not([role="navigation"])',
    'header:not(.article-header):not(.post-header)',
    'footer',

    // Sidebars and complementary content
    '[role="complementary"]',
    '[role="banner"]',
    '.sidebar', '.widget', '.cookie-notice',

    // Comment sections and related posts
    '#comments', '.comments', '.comment-section',
    '.related-posts', '.recommended', '.suggestions',

    // Ads and non-essential elements
    'aside', '.ad', '.advertisement', '.social-share',
    '.navigation', '.pagination', '.share-buttons',
    '.popup', '.modal', '.newsletter', '.subscription'
  ];

  // Remove each element type
  elementsToRemove.forEach(selector => {
    tempDiv.querySelectorAll(selector).forEach(el => {
      el.remove();
    });
  });

  return tempDiv.innerHTML;
}

/**
 * Handle the markdown output based on specified type
 * @param {string} markdown - Markdown content
 * @param {string} outputType - Output type (download, copy, show)
 * @param {Object} tab - Chrome tab object
 */
function handleOutput(markdown, outputType, tab) {
  switch (outputType) {
    case OUTPUT_TYPES.COPY:
      copyToClipboard(tab, markdown);
      break;

    case OUTPUT_TYPES.DOWNLOAD:
      downloadMarkdown(tab, markdown);
      break;

    case OUTPUT_TYPES.SHOW:
      // This is handled by the popup.js
      chrome.runtime.sendMessage({
        action: "showMarkdown",
        markdown: markdown
      });
      break;
  }
}

/**
 * Copy markdown content to clipboard and show notification
 * @param {Object} tab - Chrome tab object
 * @param {string} text - Text to copy
 */
function copyToClipboard(tab, text) {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (text) => {
      navigator.clipboard.writeText(text)
        .then(() => {
          showNotification("Markdown copied to clipboard!", "success");
        })
        .catch(err => {
          showNotification("Failed to copy: " + err, "error");
        });

      /**
       * Show notification in the page
       * @param {string} message - Notification message
       * @param {string} type - Notification type (success, error, warning)
       */
      function showNotification(message, type = "success") {
        // Define colors for different notification types
        const colors = {
          success: "#4caf50",
          error: "#f44336",
          warning: "#ff9800"
        };

        // Create notification element
        const notification = document.createElement("div");
        notification.textContent = message;
        notification.setAttribute("role", "alert");
        notification.style.cssText = `
          position: fixed;
          top: 20px;
          left: 50%;
          transform: translateX(-50%);
          background: ${colors[type] || colors.success};
          color: white;
          padding: 10px 20px;
          border-radius: 5px;
          box-shadow: 0 2px 10px rgba(0,0,0,0.2);
          z-index: 9999;
          font-family: system-ui, sans-serif;
        `;

        document.body.appendChild(notification);

        // Remove after 3 seconds
        setTimeout(() => {
          notification.style.opacity = "0";
          notification.style.transition = "opacity 0.5s";
          setTimeout(() => notification.remove(), 500);
        }, 3000);
      }
    },
    args: [text]
  });
}

/**
 * Download markdown content as a file
 * @param {Object} tab - Chrome tab object
 * @param {string} markdown - Markdown content
 */
function downloadMarkdown(tab, markdown) {
  try {
    console.log("Starting download process...");

    // Clean the filename (remove special chars, limit length)
    let filename = tab.title
      .toLowerCase()
      .replace(/[^\w\s-]/gi, '')  // Remove special characters except hyphens
      .replace(/\s+/g, '-')       // Replace spaces with hyphens
      .replace(/-{2,}/g, '-')     // Replace multiple consecutive hyphens with single hyphen
      .substring(0, 50)           // Limit length
      .trim();                    // Trim leading/trailing spaces or hyphens

    // Ensure we have a valid filename
    filename = filename || 'converted-page';
    filename += '.md';

    console.log("Downloading with filename:", filename);

    // For element selection mode, download more directly
    if (tab.id) {
      // Use direct download method in the page context
      chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (markdownContent, fileName) => {
          console.log("[Direct Download] Starting download in page context", { fileName, contentLength: markdownContent.length });

          try {
            // Method 1: Standard download approach
            const a = document.createElement('a');
            const blob = new Blob([markdownContent], { type: 'text/markdown' });
            const url = URL.createObjectURL(blob);

            a.href = url;
            a.download = fileName;

            // Log before click
            console.log("[Direct Download] Created download link", { href: a.href.substring(0, 50) + "...", download: a.download });

            // Force it to be a downloadable link
            a.setAttribute('download', fileName);
            a.setAttribute('target', '_blank');

            // Add to DOM and click
            document.body.appendChild(a);
            a.click();

            // Log after click
            console.log("[Direct Download] Clicked link");

            // Remove and clean
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 100);

            // Method 2: Fallback using Blob URL navigation
            setTimeout(() => {
              console.log("[Direct Download] Trying fallback method");

              // Create a new blob with text/plain type
              const plainBlob = new Blob([markdownContent], { type: 'text/plain' });
              const plainUrl = URL.createObjectURL(plainBlob);

              // Open in new tab and let user save
              const tab = window.open(plainUrl, '_blank');

              // If tab couldn't be opened (may be blocked), show instructions
              if (!tab) {
                console.log("[Direct Download] Popup blocked, showing save instructions");
                alert("Please allow popups to download the Markdown file, or check your downloads folder.");
              }
            }, 1000);

            return true;
          } catch (error) {
            console.error("[Direct Download] Error in download process:", error);
            return false;
          }
        },
        args: [markdown, filename]
      });
    } else {
      // Use chrome.downloads API for background contexts
      // Create blob and URL
      const blob = new Blob([markdown], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);

      // Trigger download
      chrome.downloads.download({
        url: url,
        filename: filename,
        saveAs: true
      }, (downloadId) => {
        if (chrome.runtime.lastError) {
          console.error("Download error:", chrome.runtime.lastError);
        }

        // Clean up the object URL (after a small delay to ensure download starts)
        setTimeout(() => URL.revokeObjectURL(url), 100);
      });
    }
  } catch (error) {
    console.error("Error downloading markdown:", error);
    if (tab && tab.id) {
      showErrorNotification(tab, "Error downloading file: " + error.message);
    }
  }
}

/**
 * Show error notification
 * @param {Object} tab - Chrome tab object
 * @param {string} errorMessage - Error message to display
 */
function showErrorNotification(tab, errorMessage) {
  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (message) => {
      const notification = document.createElement("div");
      notification.textContent = "HTML2MD Error: " + message;
      notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: #f44336;
        color: white;
        padding: 10px 20px;
        border-radius: 5px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.2);
        z-index: 9999;
        font-family: system-ui, sans-serif;
      `;
      document.body.appendChild(notification);
      setTimeout(() => notification.remove(), 5000);
    },
    args: [errorMessage]
  });
}

/**
 * Message handler for extension communication
 */
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "convertUrl") {
    processExternalUrl(request, sender, sendResponse);
    return true; // Return true to indicate asynchronous response
  }

  if (request.action === "batchConvertUrls") {
    processBatchUrls(request.urls, request.options, sender, sendResponse);
    return true; // Return true to indicate asynchronous response
  }

  if (request.action === "convertElement") {
    processSelectedElement(request, sender);
    return false; // No response needed
  }

  if (request.action === "downloadStoredContent") {
    // Download content that was previously stored
    if (request.contentId) {
      downloadStoredContent(request.contentId, sender);
      return false; // No response needed
    }
  }

  if (request.action === "viewStoredContent") {
    // Open the content in a new tab
    if (request.contentId) {
      chrome.tabs.create({
        url: chrome.runtime.getURL("content-viewer.html") + `?contentId=${request.contentId}`,
        active: true
      });
      return false; // No response needed
    }
  }

  if (request.action === "getStoredContent") {
    // Retrieve stored content for the content viewer page
    if (request.contentId) {
      const storageKey = `html2md_content_${request.contentId}`;
      chrome.storage.local.get([storageKey], (result) => {
        if (result[storageKey]) {
          sendResponse({
            success: true,
            data: result[storageKey]
          });
        } else {
          sendResponse({
            success: false,
            error: "Content not found"
          });
        }
      });
      return true; // Return true to indicate asynchronous response
    }
  }
});

/**
 * Process a single external URL for conversion
 * @param {Object} request - Request object containing URL and options
 * @param {Object} sender - Sender information
 * @param {Function} sendResponse - Response callback
 */
function processExternalUrl(request, sender, sendResponse) {
  // Validate URL before attempting to fetch
  try {
    const url = new URL(request.url);
    if (!url.protocol.startsWith('http')) {
      sendResponse({
        success: false,
        error: "Only HTTP and HTTPS URLs are supported"
      });
      return;
    }
  } catch (error) {
    sendResponse({
      success: false,
      error: "Invalid URL: " + error.message
    });
    return;
  }

  // Set up fetch options with timeout
  const fetchOptions = {
    method: 'GET',
    headers: {
      'User-Agent': 'Mozilla/5.0 HTML2MD Extension'
    },
    mode: 'cors',
    // Additional options can be added here
  };

  // Fetch the URL
  fetch(request.url, fetchOptions)
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.text();
    })
    .then(html => {
      // Process the HTML content
      processHtmlFromUrl(html, request, sender, sendResponse);
    })
    .catch(error => {
      console.error(`Error fetching ${request.url}:`, error);
      sendResponse({
        success: false,
        error: error.message
      });
    });
}

/**
 * Process HTML content retrieved from a URL
 * @param {string} html - Raw HTML content
 * @param {Object} request - Original request object
 * @param {Object} sender - Sender information
 * @param {Function} sendResponse - Response callback
 */
function processHtmlFromUrl(html, request, sender, sendResponse) {
  // Load user settings
  chrome.storage.sync.get('html2mdSettings', (data) => {
    try {
      const settings = data.html2mdSettings || {};

      // Extract title from HTML for better filename
      const titleMatch = html.match(/<title>(.*?)<\/title>/i);
      const pageTitle = titleMatch ? titleMatch[1].trim() : request.url.split('/').pop() || 'page';

      // Create a mock tab to pass to the converter
      const mockTab = {
        id: sender.tab?.id || -1,
        title: pageTitle,
        url: request.url
      };

      // Create a temporary DOM element to hold the HTML
      const tempElement = document.createElement('div');
      tempElement.innerHTML = html;

      // Apply content trimming if needed
      if (request.options.trim) {
        applyTrimming(tempElement);
      }

      // Initialize TurndownService with settings
      const turndownService = initializeTurndownService(settings);

      // Convert to markdown
      let markdown = turndownService.turndown(tempElement.innerHTML);

      // Add metadata to the top (URL, title, date)
      markdown = addMarkdownMetadata(markdown, request.url, pageTitle);

      // Handle the output (download, copy, etc.)
      handleOutput(markdown, request.options.output, mockTab);

      // Send success response
      sendResponse({ success: true });
    } catch (error) {
      console.error("Error processing HTML:", error);
      sendResponse({
        success: false,
        error: "Error processing HTML: " + error.message
      });
    }
  });
}

/**
 * Process multiple URLs in batch
 * @param {Array<string>} urls - Array of URLs to process
 * @param {Object} options - Conversion options
 * @param {Object} sender - Sender information
 * @param {Function} sendResponse - Response callback
 */
function processBatchUrls(urls, options, sender, sendResponse) {
  // Initialize progress tracking
  let processed = 0;
  const total = urls.length;
  const results = [];

  // Process each URL sequentially
  function processNext(index) {
    if (index >= urls.length) {
      // All URLs have been processed
      sendResponse({
        success: true,
        processed: processed,
        total: total,
        results: results
      });
      return;
    }

    const url = urls[index];

    // Report progress to popup
    chrome.runtime.sendMessage({
      action: "batchProgress",
      current: index + 1,
      total: total,
      url: url
    });

    // Process the current URL
    fetch(url)
      .then(response => {
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.text();
      })
      .then(html => {
        // Process the HTML content for this URL
        chrome.storage.sync.get('html2mdSettings', (data) => {
          try {
            const settings = data.html2mdSettings || {};

            // Extract title for better filename
            const titleMatch = html.match(/<title>(.*?)<\/title>/i);
            const pageTitle = titleMatch ? titleMatch[1].trim() : url.split('/').pop() || 'page';

            // Create a mock tab
            const mockTab = {
              id: sender.tab?.id || -1,
              title: pageTitle,
              url: url
            };

            // Create a temporary DOM element
            const tempElement = document.createElement('div');
            tempElement.innerHTML = html;

            // Apply content trimming if needed
            if (options.trim) {
              applyTrimming(tempElement);
            }

            // Initialize TurndownService
            const turndownService = initializeTurndownService(settings);

            // Convert to markdown
            let markdown = turndownService.turndown(tempElement.innerHTML);

            // Add metadata
            markdown = addMarkdownMetadata(markdown, url, pageTitle);

            // Handle the output
            handleOutput(markdown, options.output, mockTab);

            // Track success
            processed++;
            results.push({
              url: url,
              success: true,
              title: pageTitle
            });
          } catch (error) {
            console.error(`Error processing ${url}:`, error);
            results.push({
              url: url,
              success: false,
              error: error.message
            });
          }

          // Process the next URL
          processNext(index + 1);
        });
      })
      .catch(error => {
        console.error(`Error fetching ${url}:`, error);
        results.push({
          url: url,
          success: false,
          error: error.message
        });

        // Continue with the next URL
        processNext(index + 1);
      });
  }

  // Start processing with the first URL
  processNext(0);
}

/**
 * Apply content trimming to an HTML element
 * @param {Element} element - DOM element containing HTML to trim
 */
function applyTrimming(element) {
  const elementsToRemove = [
    // Scripts, styles, and technical elements
    'script', 'style', 'iframe', 'noscript',

    // Navigation and UI elements
    'nav:not([role="navigation"])',
    'header:not(.article-header):not(.post-header)',
    'footer',

    // Sidebars and complementary content
    '[role="complementary"]',
    '[role="banner"]',
    '.sidebar', '.widget', '.cookie-notice',

    // Comment sections and related posts
    '#comments', '.comments', '.comment-section',
    '.related-posts', '.recommended', '.suggestions',

    // Ads and non-essential elements
    'aside', '.ad', '.advertisement', '.social-share',
    '.navigation', '.pagination', '.share-buttons',
    '.popup', '.modal', '.newsletter', '.subscription'
  ];

  elementsToRemove.forEach(selector => {
    element.querySelectorAll(selector).forEach(el => {
      el.remove();
    });
  });
}

/**
 * Initialize TurndownService with settings
 * @param {Object} settings - User settings
 * @returns {Object} - Configured TurndownService instance
 */
function initializeTurndownService(settings) {
  const turndownOptions = {
    headingStyle: settings.markdownOptions?.headingStyle || 'atx',
    bulletListMarker: settings.markdownOptions?.bulletMarker || '-',
    linkStyle: settings.markdownOptions?.linkStyle || 'inlined',
    codeBlockStyle: settings.contentOptions?.codeBlocks ? 'fenced' : 'indented'
  };

  const turndownService = new TurndownService(turndownOptions);

  // Configure Turndown based on settings
  if (settings.contentOptions?.preserveImages === false) {
    turndownService.remove('img');
  }

  if (settings.contentOptions?.includeTables === false) {
    turndownService.remove('table');
  }

  return turndownService;
}

/**
 * Add metadata to markdown content
 * @param {string} markdown - Markdown content
 * @param {string} url - Source URL
 * @param {string} title - Page title
 * @returns {string} - Enhanced markdown with metadata
 */
function addMarkdownMetadata(markdown, url, title) {
  const dateString = new Date().toISOString().split('T')[0];

  return `---
title: "${title.replace(/"/g, '\\"')}"
source_url: ${url}
date_accessed: ${dateString}
---

# [${title}](${url})

${markdown}`;
}

/**
 * Process a selected HTML element for conversion
 * @param {Object} request - Request containing the HTML content
 * @param {Object} sender - Sender information
 */
function processSelectedElement(request, sender) {
  console.log("Processing selected element:", request);

  // The background script can't directly use TurndownService
  // So we'll inject a script to do the conversion in the context of the page

  if (!sender.tab || !sender.tab.id) {
    console.error("No tab information available");
    return;
  }

  // Inject the conversion script into the page
  chrome.scripting.executeScript({
    target: { tabId: sender.tab.id },
    files: ["turndown.js"]
  }, () => {
    if (chrome.runtime.lastError) {
      console.error("Error injecting turndown.js:", chrome.runtime.lastError);
      showErrorNotification(sender.tab, "Failed to load conversion library");
      return;
    }

    // Now convert the element in the page context
    chrome.scripting.executeScript({
      target: { tabId: sender.tab.id },
      func: convertElementInPage,
      args: [request.html, request.tag, request.title]
    }, (results) => {
      if (chrome.runtime.lastError || !results || !results[0]) {
        console.error("Error in conversion script:", chrome.runtime.lastError);
        showErrorNotification(sender.tab, "Error during conversion");
        return;
      }

      const markdown = results[0].result;
      if (!markdown) {
        showErrorNotification(sender.tab, "Failed to generate markdown");
        return;
      }

      // Create a friendly filename from the element type and page title
      const elementType = request.tag || 'element';
      const sanitizedTitle = request.title
        .toLowerCase()
        .replace(/[^\w\s-]/gi, '')
        .replace(/\s+/g, '-')
        .substring(0, 30) || 'page';

      const filename = `${elementType}-from-${sanitizedTitle}.md`;

      console.log("Element conversion successful:", {
        elementType: elementType,
        titleLength: request.title.length,
        markdownLength: markdown.length,
        filename: filename
      });

      // Create a unique ID for this markdown content to reference later
      const contentId = Date.now().toString();

      // Store the markdown content in extension storage for later retrieval
      chrome.storage.local.set({
        [`html2md_content_${contentId}`]: {
          markdown: markdown,
          filename: filename,
          timestamp: Date.now()
        }
      }, () => {
        console.log(`Markdown content stored with ID: ${contentId}`);

        // Show success notification with access to the stored content
        showSuccessNotification(sender.tab.id, contentId);

        // Try multiple download methods
        tryMultipleDownloadMethods(sender.tab.id, markdown, filename, contentId);
      });
    });
  });
}

/**
 * Try multiple methods to download the markdown file
 * @param {number} tabId - ID of the tab
 * @param {string} markdown - Markdown content to download
 * @param {string} filename - Filename for the download
 * @param {string} contentId - ID for retrieving content from storage
 */
function tryMultipleDownloadMethods(tabId, markdown, filename, contentId) {
  console.log("Attempting multiple download methods...");

  // Method 1: Try using chrome.downloads API directly
  try {
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);

    chrome.downloads.download({
      url: url,
      filename: filename,
      saveAs: false // Don't prompt for location to increase chances of success
    }, (downloadId) => {
      if (chrome.runtime.lastError) {
        console.error("Method 1 download error:", chrome.runtime.lastError);
        // Fall through to next method on failure
      } else {
        console.log("Method 1 download successful with ID:", downloadId);
      }

      // Clean up the object URL
      setTimeout(() => URL.revokeObjectURL(url), 100);
    });
  } catch (error) {
    console.error("Method 1 error:", error);
    // Continue to next method on failure
  }

  // Method 2: Try in-page download after a short delay
  setTimeout(() => {
    chrome.scripting.executeScript({
      target: { tabId: tabId },
      func: (markdownContent, fileName, contentId) => {
        console.log("[Method 2] Starting in-page download", {
          fileName,
          contentLength: markdownContent.length,
          contentId
        });

        try {
          // Create download link
          const a = document.createElement('a');
          const blob = new Blob([markdownContent], { type: 'text/markdown' });
          const url = URL.createObjectURL(blob);

          a.href = url;
          a.download = fileName;

          // Log before click
          console.log("[Method 2] Created download link", {
            href: a.href.substring(0, 50) + "...",
            download: a.download
          });

          // Force it to be a downloadable link
          a.setAttribute('download', fileName);

          // Add to DOM and click
          document.body.appendChild(a);
          a.click();

          // Log after click
          console.log("[Method 2] Clicked download link");

          // Remove and clean
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(url), 100);

          return true;
        } catch (error) {
          console.error("[Method 2] Error:", error);
          return false;
        }
      },
      args: [markdown, filename, contentId]
    });
  }, 500);

  // Method 3: Create a dedicated content page for viewing and downloading
  setTimeout(() => {
    try {
      chrome.tabs.create({
        url: chrome.runtime.getURL("content-viewer.html") + `?contentId=${contentId}`,
        active: false
      }, (tab) => {
        if (chrome.runtime.lastError) {
          console.error("Error opening content viewer tab:", chrome.runtime.lastError);
        } else {
          console.log("Content viewer tab created with ID:", tab.id);
        }
      });
    } catch (error) {
      console.error("Error creating content viewer tab:", error);
    }
  }, 1000);
}

/**
 * Download stored markdown content
 * @param {string} contentId - ID for retrieving content from storage
 * @param {Object} sender - Sender information
 */
function downloadStoredContent(contentId, sender) {
  const storageKey = `html2md_content_${contentId}`;

  chrome.storage.local.get([storageKey], (result) => {
    if (result[storageKey]) {
      const { markdown, filename } = result[storageKey];

      console.log("Downloading stored content:", {
        contentId,
        filename,
        contentLength: markdown.length
      });

      // Try multiple download methods
      if (sender.tab && sender.tab.id) {
        // If sender has a tab, try in-page download first
        chrome.scripting.executeScript({
          target: { tabId: sender.tab.id },
          func: (markdownContent, fileName) => {
            try {
              const a = document.createElement('a');
              const blob = new Blob([markdownContent], { type: 'text/markdown' });
              const url = URL.createObjectURL(blob);

              a.href = url;
              a.download = fileName;
              a.setAttribute('download', fileName);

              document.body.appendChild(a);
              a.click();
              document.body.removeChild(a);

              setTimeout(() => URL.revokeObjectURL(url), 100);
              return true;
            } catch (error) {
              console.error("In-page download error:", error);
              return false;
            }
          },
          args: [markdown, filename]
        });
      }

      // Also try chrome.downloads API as a fallback
      try {
        const blob = new Blob([markdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);

        chrome.downloads.download({
          url: url,
          filename: filename,
          saveAs: true // Let user choose location
        }, (downloadId) => {
          if (chrome.runtime.lastError) {
            console.error("Download error:", chrome.runtime.lastError);
          } else {
            console.log("Download successful with ID:", downloadId);
          }

          setTimeout(() => URL.revokeObjectURL(url), 100);
        });
      } catch (error) {
        console.error("Chrome download API error:", error);
      }

    } else {
      console.error("Content not found with ID:", contentId);

      // Show error notification if we have a tab
      if (sender.tab && sender.tab.id) {
        showErrorNotification(sender.tab, "Content not found or expired");
      }
    }
  });
}

/**
 * Convert HTML element to Markdown in the page context
 * @param {string} html - HTML content
 * @param {string} elementType - Type of the element (tag name)
 * @param {string} pageTitle - Title of the page
 * @returns {string} - Markdown with metadata
 */
function convertElementInPage(html, elementType, pageTitle) {
  try {
    // Make sure TurndownService is available
    if (typeof TurndownService !== 'function') {
      console.error('TurndownService is not available');
      return null;
    }

    // Initialize TurndownService
    const turndownService = new TurndownService({
      headingStyle: 'atx',
      bulletListMarker: '-',
      codeBlockStyle: 'fenced'
    });

    // Create a temporary DOM element
    const tempElement = document.createElement('div');
    tempElement.innerHTML = html;

    // Some debugs for troubleshooting
    console.log("Converting element:", {
      type: elementType,
      htmlLength: html.length,
      nodeType: tempElement.firstChild?.nodeType,
      childNodes: tempElement.childNodes.length
    });

    // Convert to markdown - use the string directly as fallback
    let markdown;
    try {
      markdown = turndownService.turndown(tempElement.innerHTML || html);
    } catch (conversionError) {
      console.error("Error in turndown conversion, trying alternative method:", conversionError);
      // Try direct conversion in case the element needs special handling
      markdown = turndownService.turndown(html);
    }

    // Add context metadata
    return `---
element_type: ${elementType || 'element'}
source_page: ${window.location.href}
date_extracted: ${new Date().toISOString().split('T')[0]}
---

# Selected ${(elementType || 'element').charAt(0).toUpperCase() + (elementType || 'element').slice(1)} from ${pageTitle || document.title}

${markdown}`;
  } catch (error) {
    console.error('Error in convertElementInPage:', error);
    return null;
  }
}

/**
 * Show success notification for element conversion
 * @param {number} tabId - ID of the tab to show notification in
 * @param {string} contentId - ID for retrieving content from storage
 */
function showSuccessNotification(tabId, contentId) {
  if (!tabId) return;

  chrome.scripting.executeScript({
    target: { tabId: tabId },
    func: (contentId) => {
      // Create notification element
      const notification = document.createElement('div');
      notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background-color: #4caf50;
        color: white;
        padding: 12px 20px;
        border-radius: 6px;
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 14px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        z-index: 2147483647;
        display: flex;
        align-items: center;
        gap: 10px;
      `;

      // Add the success message with a manual download button
      notification.innerHTML = `
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10-4.477 10-10 10zm-1-8.414l-3.293-3.293-1.414 1.414L11 16.414l7.707-7.707-1.414-1.414L11 14.586z" fill="white"/>
        </svg>
        <div>
          <div>Element successfully converted to Markdown!</div>
          <div style="display: flex; gap: 8px; margin-top: 8px;">
            <button id="manual-download-btn" style="
              background-color: white;
              color: #4caf50;
              border: none;
              border-radius: 4px;
              padding: 4px 10px;
              cursor: pointer;
              font-weight: bold;
              font-size: 12px;
            ">Download</button>
            <button id="view-content-btn" style="
              background-color: white;
              color: #2196f3;
              border: none;
              border-radius: 4px;
              padding: 4px 10px;
              cursor: pointer;
              font-weight: bold;
              font-size: 12px;
            ">View Content</button>
          </div>
        </div>
      `;

      document.body.appendChild(notification);

      // Store the content ID in a data attribute for the buttons to use
      notification.dataset.contentId = contentId;

      // Add click handler for the manual download button
      notification.querySelector('#manual-download-btn').addEventListener('click', () => {
        chrome.runtime.sendMessage({
          action: "downloadStoredContent",
          contentId: contentId
        });
      });

      // Add click handler for the view content button
      notification.querySelector('#view-content-btn').addEventListener('click', () => {
        chrome.runtime.sendMessage({
          action: "viewStoredContent",
          contentId: contentId
        });
      });

      // Keep the notification visible for longer to allow for manual download
      setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.5s ease';

        setTimeout(() => {
          notification.remove();
        }, 500);
      }, 15000); // Keep for 15 seconds
    },
    args: [contentId]
  });
}
