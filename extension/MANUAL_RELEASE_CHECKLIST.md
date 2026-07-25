# Extension manual release checklist

Copy this checklist into dated release evidence before a Chrome Web Store
submission. The committed template is not a completed test record and does not
claim accessibility conformance.

## Test record

- Extension version:
- Commit:
- Date:
- Reviewer:
- Chrome version:
- Operating system:
- Display scaling / zoom:
- Assistive technology used, if any:

## Interaction and accessibility

- [ ] Every popup control is reachable in a logical order using only the
      keyboard.
- [ ] Keyboard focus is always visible, including in light and dark themes.
- [ ] Control names, labels, groups, and disabled states are exposed clearly.
- [ ] Conversion progress, completion, empty-selection, and failure states are
      announced without relying only on color or motion.
- [ ] Preview content can be reached, read, selected, and scrolled without
      trapping keyboard focus.
- [ ] Repeated activation while conversion is running cannot overlap work or
      corrupt the final state.

## Functional modes

- [ ] Full-page mode preserves the intended authored document scope.
- [ ] Selection mode converts exactly the selected range and reports an empty
      selection honestly.
- [ ] Main-article mode either converts the selected article or reports that no
      confident article was found.
- [ ] Clipboard completion and clipboard denial are both visible.
- [ ] Download completion, filename sanitization, and download failure are
      visible.
- [ ] Settings persist through `chrome.storage.sync` and reset to documented
      defaults.
- [ ] The installed manifest requests no persistent host permissions; access
      remains limited to the user-invoked active tab.

## Evidence and decision

- Screenshots or recording location:
- Defects opened:
- Known limitations accepted:
- Result: PASS / FAIL
- Web Store submission authorized by:

A `PASS` records only the browsers, operating systems, interactions, and
assistive technology named above. It is not formal conformance evidence.
