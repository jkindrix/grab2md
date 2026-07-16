/** Production-safe extension logger. Diagnostic output is disabled by default. */

const Html2MdLogger = Object.freeze({
  debug() {},
  warn() {},
  error() {}
});

if (typeof globalThis !== 'undefined') {
  globalThis.Html2MdLogger = Html2MdLogger;
}

if (typeof module !== 'undefined') {
  module.exports = Html2MdLogger;
}
