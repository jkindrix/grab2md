const loadingEl = document.getElementById('loading');
const errorMessageEl = document.getElementById('error-message');
const contentSectionEl = document.getElementById('content-section');
const filenameEl = document.getElementById('filename');
const timestampEl = document.getElementById('timestamp');
const markdownContentEl = document.getElementById('markdown-content');
const downloadBtn = document.getElementById('download-btn');
const copyBtn = document.getElementById('copy-btn');
const copyFeedbackEl = document.getElementById('copy-feedback');

let contentData = null;

function getContentId() {
  const params = new URLSearchParams(window.location.search);
  return params.get('contentId');
}

function formatTimestamp(timestamp) {
  return new Date(timestamp).toLocaleString();
}

function showError(message) {
  loadingEl.style.display = 'none';
  errorMessageEl.textContent = message || 'Error loading content';
  errorMessageEl.style.display = 'block';
}

function showContent() {
  loadingEl.style.display = 'none';
  filenameEl.textContent = contentData.filename;
  timestampEl.textContent = `Converted on ${formatTimestamp(contentData.timestamp)}`;
  markdownContentEl.textContent = contentData.markdown;
  contentSectionEl.style.display = 'block';
}

function loadContent() {
  const contentId = getContentId();
  if (!contentId) {
    showError('No content ID provided');
    return;
  }

  chrome.runtime.sendMessage({
    action: 'getStoredContent',
    contentId: contentId
  }, response => {
    if (response && response.success) {
      contentData = response.data;
      showContent();
    } else {
      showError(response?.error || 'Failed to load content');
    }
  });
}

function downloadMarkdown() {
  if (!contentData) return;

  try {
    const blob = new Blob([contentData.markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = contentData.filename;
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 100);
  } catch (error) {
    console.error('Download error:', error);
    showError('Failed to download file');
  }
}

function copyToClipboard() {
  if (!contentData) return;

  navigator.clipboard.writeText(contentData.markdown)
    .then(() => {
      copyFeedbackEl.classList.add('show');
      setTimeout(() => copyFeedbackEl.classList.remove('show'), 2000);
    })
    .catch(error => {
      console.error('Clipboard error:', error);
      showError('Failed to copy to clipboard');
    });
}

downloadBtn.addEventListener('click', downloadMarkdown);
copyBtn.addEventListener('click', copyToClipboard);
document.addEventListener('DOMContentLoaded', loadContent);
