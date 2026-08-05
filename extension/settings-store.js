/** Persistence adapter for popup settings. */

class Grab2MdSettingsStore {
  constructor(
    storage,
    key = 'grab2mdSettings',
    runtimeError = () => globalThis.chrome?.runtime?.lastError?.message || null
  ) {
    this.storage = storage;
    this.key = key;
    this.runtimeError = runtimeError;
  }

  normalize(defaults, saved = {}) {
    const markdown = saved?.markdownOptions && typeof saved.markdownOptions === 'object'
      ? saved.markdownOptions
      : {};
    const content = saved?.contentOptions && typeof saved.contentOptions === 'object'
      ? saved.contentOptions
      : {};

    return {
      ...defaults,
      theme: saved?.theme === 'dark' || saved?.theme === 'light'
        ? saved.theme
        : defaults.theme,
      markdownOptions: {
        ...defaults.markdownOptions,
        headingStyle: markdown.headingStyle === 'setext' || markdown.headingStyle === 'atx'
          ? markdown.headingStyle
          : defaults.markdownOptions.headingStyle,
        bulletMarker: ['-', '*', '+'].includes(markdown.bulletMarker)
          ? markdown.bulletMarker
          : defaults.markdownOptions.bulletMarker
      },
      contentOptions: {
        ...defaults.contentOptions,
        preserveImages: typeof content.preserveImages === 'boolean'
          ? content.preserveImages
          : defaults.contentOptions.preserveImages,
        codeBlocks: typeof content.codeBlocks === 'boolean'
          ? content.codeBlocks
          : defaults.contentOptions.codeBlocks
      }
    };
  }

  load(defaults, callback) {
    const fallback = () => this.normalize(defaults);
    try {
      this.storage.get(this.key, data => {
        const error = this.runtimeError();
        if (error) {
          callback(fallback(), error);
          return;
        }
        const saved = data && typeof data === 'object' ? data[this.key] : {};
        callback(this.normalize(defaults, saved));
      });
    } catch (error) {
      callback(fallback(), error.message || String(error));
    }
  }

  save(settings, callback) {
    try {
      this.storage.set({ [this.key]: settings }, () => {
        callback(this.runtimeError());
      });
    } catch (error) {
      callback(error.message || String(error));
    }
  }
}

globalThis.Grab2MdSettingsStore = Grab2MdSettingsStore;
if (typeof module !== 'undefined') module.exports = { Grab2MdSettingsStore };
