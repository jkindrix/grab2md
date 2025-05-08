/**
 * ChatGPT Markdown Cleaner
 * 
 * A simpler, more focused solution for cleaning ChatGPT-generated markdown
 */

class ChatGPTCleaner {
  /**
   * Post-process markdown to fix common ChatGPT conversion issues
   * @param {string} markdown - Raw markdown from the converter
   * @returns {string} - Cleaned markdown
   */
  static clean(markdown) {
    // 1. Remove UI elements and artifacts
    markdown = this.removeUIElements(markdown);
    
    // 2. Fix headings and dialog structure
    markdown = this.fixChatStructure(markdown);
    
    // 3. Fix code blocks
    markdown = this.fixCodeBlocks(markdown);
    
    // 4. Clean up whitespace and structure
    markdown = this.cleanupWhitespace(markdown);
    
    return markdown;
  }
  
  /**
   * Remove UI elements and artifacts from the markdown
   */
  static removeUIElements(markdown) {
    // Comprehensive list of UI elements to remove
    const uiElements = [
      'Skip to content', 'Chat history', 'Open sidebar', 'Share', 'Search',
      'Deep research', 'Saved memory full', 'undefined', 'Answer in chat instead',
      'ChatGPT can make mistakes', 'OpenAI doesn\'t use', 'workspace data',
      'CopyEdit', 'Copy Edit', 'Copy code', 'Chat', 'GPT', 'OpenAI',
      '4o', 'Assistant can make mistakes', 'Information cutoff', 
      'Justin\'s Workspace', 'search', 'Deep research', 'Create image',
      'Clear conversations', 'Settings', 'Log out', 'API mode', 'Help',
      'My plan', 'New chat', 'Previous conversations', 'Limited knowledge',
      'may produce inaccurate information', 'trained on data', 'regenerate response',
      'model', 'GPT-4', 'GPT-3.5', 'GPT-4o'
    ];
    
    let cleaned = markdown;
    
    // Remove all UI element strings
    uiElements.forEach(element => {
      cleaned = cleaned.replace(new RegExp(element, 'gi'), '');
    });
    
    return cleaned
      // Remove single-word tokens that are likely UI elements
      .replace(/\b4o\b/g, '')
      .replace(/\?\s*$/gm, '')
      // Remove any lines that are just a single short word (likely UI elements)
      .replace(/^\s*\b\w{1,8}\b\s*$/gm, '')
      // Remove any lines starting with "undefined"
      .replace(/^\s*undefined.*$/gm, '')
      // Remove lines with just icons or emoji (common in UI)
      .replace(/^\s*[👍👎🔄📋✉️📝⚙️🔍]+\s*$/gm, '');
  }
  
  /**
   * Fix the chat structure to use proper markdown headings
   */
  static fixChatStructure(markdown) {
    // Fix user messages
    markdown = markdown.replace(/#+\s*You said:/gi, '## User:');
    
    // Fix assistant messages
    markdown = markdown.replace(/#+\s*ChatGPT said:/gi, '## Assistant:');
    
    // Add a title if none exists
    if (!markdown.trim().startsWith('# ')) {
      markdown = '# Chat Transcript\n\n' + markdown;
    }
    
    return markdown;
  }
  
  /**
   * Fix code blocks to use proper fencing and language identifiers
   */
  static fixCodeBlocks(markdown) {
    let fixed = markdown;
    
    // Comprehensive language identifier list
    const languageIds = [
      'javascript', 'js', 'typescript', 'ts', 'python', 'py', 'java', 
      'cpp', 'c#', 'csharp', 'ruby', 'rb', 'php', 'go', 'golang', 
      'rust', 'html', 'css', 'json', 'yaml', 'yml', 'bash', 'shell', 'sh', 
      'sql', 'markdown', 'md', 'text', 'txt', 'c++'
    ];
    
    // Fix language identifiers before code blocks - multiple patterns
    languageIds.forEach(lang => {
      // Simple language identifier on its own line
      const langPattern = new RegExp(`^\\s*${lang}\\s*$\\s*^\\s*\`\`\``, 'gim');
      fixed = fixed.replace(langPattern, '```' + lang.toLowerCase() + '\n');
      
      // Language with colon (e.g., "javascript:")
      const langColonPattern = new RegExp(`^\\s*${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
      fixed = fixed.replace(langColonPattern, '```' + lang.toLowerCase() + '\n');
      
      // "In {language}:" pattern
      const langInPattern = new RegExp(`^\\s*In\\s+${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
      fixed = fixed.replace(langInPattern, '```' + lang.toLowerCase() + '\n');
      
      // "Using {language}:" pattern
      const langUsingPattern = new RegExp(`^\\s*Using\\s+${lang}:\\s*$\\s*^\\s*\`\`\``, 'gim');
      fixed = fixed.replace(langUsingPattern, '```' + lang.toLowerCase() + '\n');
    });
    
    // Fix code blocks with single backticks
    const singleBacktickRegex = /`([^`]+)`/gm;
    fixed = fixed.replace(singleBacktickRegex, (match, code) => {
      // Only convert to triple backtick if it contains newlines (multiline code)
      if (code.includes('\n')) {
        // Detect language
        let language = '';
        if (code.match(/^\s*[{[]/) || code.includes('":')) language = 'json';
        else if (code.includes('function') || code.includes('var ') || code.includes('const ')) language = 'javascript';
        else if (code.match(/^\s*(def|import|class)/) || code.includes('print(')) language = 'python';
        else if (code.includes('<html') || code.includes('<div') || code.includes('<')) language = 'html';
        else if (code.includes('package ') || code.includes('public class')) language = 'java';
        
        return '```' + language + '\n' + code.trim() + '\n```';
      }
      return match; // Keep inline code as is
    });
    
    // Fix nested code blocks (code blocks inside code blocks)
    const codeBlockRegex = /```([a-z]*)([\s\S]*?)```/g;
    const processedBlocks = new Set();
    
    let match;
    while ((match = codeBlockRegex.exec(fixed)) !== null) {
      const fullMatch = match[0];
      const language = match[1];
      const content = match[2];
      
      // Skip blocks we've already processed
      if (processedBlocks.has(match.index)) continue;
      
      // Check if this block contains other code blocks
      if (content.includes('```')) {
        // Replace inner code blocks with escaped versions
        const fixedContent = content.replace(/```/g, '`\u200B`\u200B`'); // Using zero-width space
        const fixedBlock = '```' + language + fixedContent + '```';
        
        // Replace in the original markdown
        fixed = fixed.substring(0, match.index) + 
                fixedBlock + 
                fixed.substring(match.index + fullMatch.length);
        
        // Reset regex to start over since we modified the string
        codeBlockRegex.lastIndex = 0;
      }
      
      processedBlocks.add(match.index);
    }
    
    // Format specific code block types properly
    // JSON
    fixed = fixed.replace(/```(\s*json\s*\n\s*)({[^`]*})/gi, (match, lang, content) => {
      try {
        // Try to format the JSON if it's valid
        const formattedJson = JSON.stringify(JSON.parse(content.replace(/\s+/g, ' ')), null, 2);
        return '```json\n' + formattedJson + '\n';
      } catch (e) {
        return match; // Keep as is if parsing fails
      }
    });
    
    // Fix common code block issues
    fixed = fixed
      // Remove "Copy"/"Edit" strings that appear in code blocks
      .replace(/\bCopy\s*code\b/g, '')
      .replace(/\bCopyEdit\b/g, '')
      .replace(/\bCopy\s*Edit\b/g, '')
      // Ensure proper spacing around code blocks
      .replace(/(\S)\s*\n\s*```(\w*)/g, '$1\n\n```$2')
      .replace(/```\s*\n([^\n`])/g, '```\n\n$1')
      // Fix broken/mangled code blocks
      .replace(/```\s*```/g, '```\n\n```')
      .replace(/```(\w+)\s*```/g, '```$1\n\n```')
      // Ensure code fence properly starts on its own line
      .replace(/([^\n])```/g, '$1\n```')
      // Fix empty code blocks
      .replace(/```(\w*)\n\s*\n*\s*```/g, '');
    
    return fixed;
  }
  
  /**
   * Clean up whitespace and other formatting issues
   */
  static cleanupWhitespace(markdown) {
    let cleaned = markdown;
    
    // Fix excessive whitespace - systematic approach
    cleaned = cleaned
      // Remove excess blank lines (more than 2 consecutive newlines)
      .replace(/\n{3,}/g, '\n\n')
      // Ensure proper spacing around headings
      .replace(/^(#+[^#\n]*)\n([^#\n])/gm, '$1\n\n$2')
      // Fix list items (remove blank lines between items but preserve indentation)
      .replace(/(\n\s*[-*+].*\n)\s*\n(\s*[-*+])/g, '$1$2')
      // Fix numbered list items too
      .replace(/(\n\s*\d+\..*\n)\s*\n(\s*\d+\.)/g, '$1$2')
      // Fix extra spaces at end of lines
      .replace(/[ \t]+$/gm, '')
      // Remove trailing whitespace at end of file
      .replace(/\s+$/, '');
    
    // Fix message headers (##### to ** format)
    cleaned = cleaned
      .replace(/^#+\s*You said:/gim, '**User**:')
      .replace(/^#+\s*ChatGPT said:/gim, '**Assistant**:')
      .replace(/^#+\s*User:/gim, '**User**:')
      .replace(/^#+\s*Assistant:/gim, '**Assistant**:')
      .replace(/^#+\s*Human:/gim, '**User**:')
      .replace(/^#+\s*AI:/gim, '**Assistant**:');
    
    // Ensure proper spacing after message headers
    cleaned = cleaned
      .replace(/(\*\*(?:User|Assistant)\*\*:)(?!\n)/g, '$1\n')
      .replace(/(\*\*(?:User|Assistant)\*\*:)\n(?!\n)/g, '$1\n\n');
    
    // Fix WikiLinks
    cleaned = cleaned.replace(/\[\[(.*?)\]\]/g, (match, content) => {
      if (content.includes('|')) {
        const [label, target] = content.split('|');
        return `[${label.trim()}](${target.trim()})`;
      } else if (content.includes(' ')) {
        const target = content.trim().replace(/\s+/g, '-').toLowerCase();
        return `[${content.trim()}](${target})`;
      }
      return content;
    });
    
    // Final trim
    return cleaned.trim();
  }
  
  /**
   * Detect if the HTML is from ChatGPT
   */
  static isChatGPT(html) {
    return (
      html.includes('chatgpt.com') ||
      html.includes('chat.openai.com') ||
      html.includes('You said:') ||
      html.includes('ChatGPT said:') ||
      html.includes('user-message') ||
      html.includes('assistant-message')
    );
  }
}

// Export for use in other scripts
if (typeof module !== 'undefined') {
  module.exports = ChatGPTCleaner;
}