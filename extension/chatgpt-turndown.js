/**
 * ChatGPT-specific TurndownService extension
 * 
 * This extends the base TurndownService with specialized rules for converting
 * ChatGPT conversations to properly formatted markdown
 */

class ChatGPTTurndownService {
  constructor(options = {}) {
    // Internal reference to base TurndownService
    this.turndownService = new TurndownService({
      headingStyle: options.headingStyle || 'atx',
      bulletListMarker: options.bulletListMarker || '-',
      codeBlockStyle: 'fenced',
      fence: '```',
      emDelimiter: '_',
      strongDelimiter: '**'
    });

    // Initialize with ChatGPT-specific rules
    this.initChatGPTRules();
  }
  
  /**
   * Convert HTML to markdown string
   * @param {string} html - HTML content to convert
   * @returns {string} - Markdown content
   */
  turndown(html) {
    // Do any ChatGPT-specific pre-processing if needed
    return this.turndownService.turndown(html);
  }

  /**
   * Configure the TurndownService with ChatGPT-specific rules
   */
  initChatGPTRules() {
    const turndownService = this.turndownService;

    // Override code block handling for better ChatGPT support
    turndownService.addRule('chatgptCodeBlock', {
      filter: function(node) {
        // Check for specific ChatGPT code block structures
        return (
          // Standard code blocks
          (node.nodeName === 'PRE' && node.firstChild && node.firstChild.nodeName === 'CODE') ||
          // ChatGPT code blocks with specific classes
          (node.nodeName === 'DIV' && (
            node.classList.contains('code-block') || 
            node.classList.contains('whitespace-pre') ||
            node.classList.contains('bg-black') ||
            node.classList.contains('overflow-auto')
          ))
        );
      },
      replacement: function(content, node, options) {
        // Extract language if available
        let language = '';
        
        // Try to find language in classes
        if (node.className && node.className.includes('language-')) {
          const match = node.className.match(/language-(\w+)/);
          if (match) language = match[1];
        }
        
        // Check for language in child nodes
        if (!language && node.firstChild && node.firstChild.className) {
          const match = node.firstChild.className.match(/language-(\w+)/);
          if (match) language = match[1];
        }
        
        // Check data attributes
        if (!language && node.dataset && node.dataset.language) {
          language = node.dataset.language;
        }
        
        // Look for preceding language identifier (common in ChatGPT)
        if (!language) {
          const prevNode = node.previousElementSibling;
          if (prevNode && prevNode.textContent) {
            const langText = prevNode.textContent.trim().toLowerCase();
            if (/^(javascript|python|java|typescript|ruby|go|rust|php|html|css|json|yaml|bash|shell|sql)$/.test(langText)) {
              language = langText;
            }
          }
        }

        // Clean up content 
        content = content.trim();
        
        // Ensure empty lines aren't completely stripped
        content = content.replace(/\n{2,}/g, '\n\n');
        
        // Create proper fenced code block
        return '\n\n```' + language + '\n' + content + '\n```\n\n';
      }
    });

    // Improve handling of chat message headers
    turndownService.addRule('chatHeaders', {
      filter: function(node) {
        // Detect ChatGPT message headers
        return (
          node.nodeName === 'DIV' && 
          (node.classList.contains('user-message') || 
           node.classList.contains('assistant-message') ||
           (node.getAttribute('data-message-author-role') === 'user') ||
           (node.getAttribute('data-message-author-role') === 'assistant'))
        );
      },
      replacement: function(content, node, options) {
        // Determine if user or assistant
        const isUser = node.classList.contains('user-message') || 
                      node.getAttribute('data-message-author-role') === 'user';
        
        // Add appropriate header
        const header = isUser ? '### User:\n\n' : '### Assistant:\n\n';
        
        return '\n\n' + header + content + '\n\n';
      }
    });

    // Remove ChatGPT UI elements that shouldn't be in the output
    turndownService.remove([
      '.copy-button',
      '.regenerate-button',
      '.edit-button',
      '.feedback-button',
      '.chat-controls',
      'nav',
      'header',
      'footer',
      'button',
      '.sidebar',
      '.search-box',
      '.user-menu',
      '.login-container'
    ]);
  }

  /**
   * Preprocess HTML to standardize ChatGPT structure
   */
  preprocessHTML(html) {
    // Create temporary element to manipulate HTML
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    
    // Remove unwanted UI elements
    const elementsToRemove = [
      // Navigation/UI
      'nav', 'header', 'footer', 'button',
      // ChatGPT specific UI
      '[data-testid="send-button"]',
      '[data-testid="clipboard-button"]',
      '[role="navigation"]',
      '.sticky',
      '.pointer-events-auto',
      '.chat-message-actions',
      '.chat-message-edit-buttons',
      // Common elements
      'script', 'style', 'link', 'meta'
    ];
    
    // Remove elements
    elementsToRemove.forEach(selector => {
      try {
        const elements = tempDiv.querySelectorAll(selector);
        elements.forEach(el => el.remove());
      } catch (e) {
        // Ignore errors for invalid selectors
      }
    });
    
    // Fix code blocks
    this.preprocessCodeBlocks(tempDiv);
    
    // Return cleaned HTML
    return tempDiv.innerHTML;
  }
  
  /**
   * Preprocess code blocks to standardize them
   */
  preprocessCodeBlocks(container) {
    // Find all potential code blocks with different ChatGPT structures
    const codeSelectors = [
      // Find pre/code blocks
      'pre code',
      // ChatGPT code blocks by class pattern
      '.code-block',
      '[class*="bg-black"]',
      '[class*="whitespace-pre"]',
      // Handle potential copy button divs
      '[class*="code"] + button',
      'button + [class*="code"]'
    ];
    
    // Process each type of code block
    codeSelectors.forEach(selector => {
      try {
        const elements = container.querySelectorAll(selector);
        elements.forEach(el => {
          // Get the actual code element or parent
          const codeEl = el.nodeName === 'CODE' ? el : el.querySelector('code');
          const parentEl = el.nodeName === 'CODE' ? el.parentNode : el;
          
          if (codeEl) {
            // Clean up code element content
            // Remove backticks that might cause fencing issues
            codeEl.innerHTML = codeEl.innerHTML.replace(/`{3,}/g, '```');
            
            // Fix newlines to ensure proper rendering
            codeEl.innerHTML = codeEl.innerHTML.replace(/<br\s*\/?>/gi, '\n');
          }
          
          // Look for language identifier
          // Check previous siblings for language hints
          const prevEl = parentEl.previousElementSibling;
          if (prevEl && /^(javascript|python|typescript|java|cpp|c\+\+|ruby|php|go|rust|html|css|json|yaml|bash|shell|sql)$/i.test(prevEl.textContent.trim())) {
            // Add data-language attribute to help Turndown
            parentEl.setAttribute('data-language', prevEl.textContent.trim().toLowerCase());
            
            // If the previous element was just a language tag, remove it to avoid duplication
            if (prevEl.textContent.trim().length < 20) {
              prevEl.setAttribute('data-language-marker', 'true');
            }
          }
        });
        
        // Remove language markers that have been processed
        container.querySelectorAll('[data-language-marker="true"]').forEach(el => el.remove());
      } catch (e) {
        // Ignore invalid selectors
      }
    });
  }

  /**
   * Post-process markdown to fix common issues with ChatGPT output
   */
  postprocessMarkdown(markdown) {
    // Fix nested code blocks
    markdown = this.fixNestedCodeBlocks(markdown);
    
    // Clean up language tags that appear as content
    markdown = this.fixLanguageTags(markdown);
    
    // Fix excessive backticks
    markdown = this.normalizeBackticks(markdown);
    
    // Fix chat headers
    markdown = this.fixChatHeaders(markdown);
    
    // Remove UI elements text that might have slipped through
    markdown = this.removeUIText(markdown);
    
    // Fix extra blank lines
    markdown = markdown.replace(/\n{3,}/g, '\n\n');
    
    return markdown.trim();
  }
  
  /**
   * Fix nested code blocks problem
   */
  fixNestedCodeBlocks(markdown) {
    // First pass - identify all code blocks
    const codeBlockRegex = /```([a-z]*)\n([\s\S]*?)```/g;
    const codeBlocks = [];
    let match;
    
    // Collect all code blocks
    while ((match = codeBlockRegex.exec(markdown)) !== null) {
      codeBlocks.push({
        language: match[1],
        content: match[2],
        full: match[0],
        start: match.index,
        end: match.index + match[0].length
      });
    }
    
    // Identify nested blocks
    for (let i = 0; i < codeBlocks.length; i++) {
      for (let j = 0; j < codeBlocks.length; j++) {
        if (i !== j && 
            codeBlocks[j].start > codeBlocks[i].start && 
            codeBlocks[j].end < codeBlocks[i].end) {
          // j is nested inside i - mark it
          codeBlocks[j].nested = true;
          
          // Replace backticks in the nested block to avoid fencing issues
          const nestedContent = codeBlocks[j].full.replace(/```/g, '`​`​`'); // Using zero-width space to break backtick sequence
          markdown = markdown.substring(0, codeBlocks[j].start) + 
                    nestedContent + 
                    markdown.substring(codeBlocks[j].end);
        }
      }
    }
    
    return markdown;
  }
  
  /**
   * Fix language tags that appear as text before code blocks
   */
  fixLanguageTags(markdown) {
    // Detect common language tags that should be attached to code fences
    return markdown.replace(/^(javascript|python|java|typescript|ruby|go|rust|php|html|css|json|yaml|bash|shell|sql|markdown)\s*\n+```\s*\n/gmi, 
                          '```$1\n');
  }
  
  /**
   * Normalize backticks to ensure proper code fencing
   */
  normalizeBackticks(markdown) {
    // Replace excessive backticks (more than 3) with exactly 3
    markdown = markdown.replace(/^`{4,}(.*)$/gm, '```$1');
    
    // Replace tildes with backticks for consistency
    markdown = markdown.replace(/^~{3,}(.*)$/gm, '```$1');
    
    // Fix incomplete code blocks (missing closing fence)
    markdown = markdown.replace(/(```[^\n]*\n[\s\S]+?)(\n\s*##)(?!`)/g, '$1\n```$2');
    
    // Fix adjacent code blocks
    markdown = markdown.replace(/```\s*```/g, '```\n\n```');
    
    // Remove stray backticks at beginning/end of document
    markdown = markdown.replace(/^(`{3,}|~{3,})\s*\n+/m, '');
    markdown = markdown.replace(/\n+\s*(`{3,}|~{3,})$/m, '');
    
    return markdown;
  }
  
  /**
   * Fix chat message headers
   */
  fixChatHeaders(markdown) {
    // Normalize user/assistant headers
    markdown = markdown.replace(/#+\s*You said:/g, '### User:');
    markdown = markdown.replace(/#+\s*ChatGPT said:/g, '### Assistant:');
    
    // Ensure headers have proper spacing
    markdown = markdown.replace(/(### User:)\s*/g, '$1\n\n');
    markdown = markdown.replace(/(### Assistant:)\s*/g, '$1\n\n');
    
    return markdown;
  }
  
  /**
   * Remove common UI text that might be included 
   */
  removeUIText(markdown) {
    return markdown
      // Common ChatGPT UI elements
      .replace(/\bSkip to content\b/g, '')
      .replace(/\bOpen sidebar\b/g, '')
      .replace(/\bChatGPT \d+o?\b/g, '')
      .replace(/\bShare\b/g, '')
      .replace(/\bSearch\b/g, '')
      .replace(/\bDeep research\b/g, '')
      .replace(/\bCreate image\b/g, '')
      .replace(/\bChatGPT can make mistakes\.[^\n]*/g, '')
      .replace(/\bCopy\s*Edit\b/g, '')
      .replace(/\b4o\b/g, '')
      .replace(/\bSearch\b/g, '')
      .replace(/\bDeep research\b/g, '')
      // Common buttons
      .replace(/\bRegenerate\b/g, '')
      .replace(/\bContinue\b/g, '')
      // Remove extra space after cleaning
      .replace(/\s{2,}/g, ' ')
      // Fix extra line breaks
      .replace(/\n{3,}/g, '\n\n');
  }
  
  /**
   * Main conversion method - from HTML to markdown with ChatGPT optimizations
   */
  turndown(html) {
    // 1. Preprocess HTML for ChatGPT
    const processedHtml = this.preprocessHTML(html);
    
    // 2. Convert to markdown using TurndownService
    let markdown = this.turndownService.turndown(processedHtml);
    
    // 3. Post-process to fix common issues
    markdown = this.postprocessMarkdown(markdown);
    
    return markdown;
  }
  
  /**
   * Detect if content is from ChatGPT
   */
  static detectChatGPT(html) {
    return (
      // URL patterns
      html.includes('chatgpt.com') ||
      html.includes('chat.openai.com') ||
      // UI elements
      html.includes('data-message-author-role="user"') ||
      html.includes('data-message-author-role="assistant"') ||
      html.includes('user-message') ||
      html.includes('assistant-message') ||
      // Content patterns
      html.includes('You said:') ||
      html.includes('ChatGPT said:') ||
      // Specific div structures
      html.includes('conversation-turn') ||
      html.includes('chat-message') ||
      html.includes('markdown prose')
    );
  }
}