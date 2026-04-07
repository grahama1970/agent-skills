"""
JavaScript scripts injected into pages via CDP for accessibility tree generation,
element interaction, and page content extraction.
"""

# Accessibility tree generation script (minified from surf-cli content script)
ACCESSIBILITY_TREE_SCRIPT = '''
(function(filter, maxDepth) {
  filter = filter || "interactive";
  maxDepth = maxDepth || 15;

  if (!window.__piElementMap) window.__piElementMap = {};
  if (!window.__piRefs) window.__piRefs = {};

  let globalRefCounter = window.__piRefCounter || 0;

  const VALID_ARIA_ROLES = new Set([
    "alert", "alertdialog", "application", "article", "banner", "blockquote",
    "button", "caption", "cell", "checkbox", "code", "columnheader", "combobox",
    "complementary", "contentinfo", "definition", "deletion", "dialog", "directory",
    "document", "emphasis", "feed", "figure", "form", "generic", "grid", "gridcell",
    "group", "heading", "img", "insertion", "link", "list", "listbox", "listitem",
    "log", "main", "mark", "marquee", "math", "menu", "menubar", "menuitem",
    "menuitemcheckbox", "menuitemradio", "meter", "navigation", "none", "note",
    "option", "paragraph", "presentation", "progressbar", "radio", "radiogroup",
    "region", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox",
    "separator", "slider", "spinbutton", "status", "strong", "subscript",
    "superscript", "switch", "tab", "table", "tablist", "tabpanel", "term",
    "textbox", "time", "timer", "toolbar", "tooltip", "tree", "treegrid", "treeitem"
  ]);

  function isFocusable(element) {
    const tagName = element.tagName.toLowerCase();
    if (["button", "input", "select", "textarea"].includes(tagName)) {
      return !element.disabled;
    }
    if (tagName === "a" && element.hasAttribute("href")) return true;
    if (element.hasAttribute("tabindex")) {
      const tabindex = parseInt(element.getAttribute("tabindex") || "", 10);
      return !isNaN(tabindex) && tabindex >= 0;
    }
    if (element.getAttribute("contenteditable") === "true") return true;
    return false;
  }

  function getExplicitRole(element) {
    const roleAttr = element.getAttribute("role");
    if (!roleAttr) return null;
    const roles = roleAttr.split(/\\s+/).filter(r => r);
    for (const role of roles) {
      if (VALID_ARIA_ROLES.has(role)) return role;
    }
    return null;
  }

  function getImplicitRole(element) {
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type");

    const tagRoles = {
      a: (el) => el.hasAttribute("href") ? "link" : "generic",
      article: "article", aside: "complementary", button: "button",
      datalist: "listbox", dd: "definition", details: "group", dialog: "dialog",
      dt: "term", fieldset: "group", figure: "figure",
      footer: (el) => el.closest("article, aside, main, nav, section") ? "generic" : "contentinfo",
      form: (el) => el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") ? "form" : "generic",
      h1: "heading", h2: "heading", h3: "heading", h4: "heading", h5: "heading", h6: "heading",
      header: (el) => el.closest("article, aside, main, nav, section") ? "generic" : "banner",
      hr: "separator",
      img: (el) => el.getAttribute("alt") === "" ? "presentation" : "img",
      li: "listitem", main: "main", math: "math", menu: "list", meter: "meter",
      nav: "navigation", ol: "list", optgroup: "group", option: "option",
      output: "status", p: "paragraph", progress: "progressbar", search: "search",
      section: (el) => el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") ? "region" : "generic",
      select: (el) => el.hasAttribute("multiple") || (el.size && el.size > 1) ? "listbox" : "combobox",
      table: "table", tbody: "rowgroup", td: "cell", textarea: "textbox",
      tfoot: "rowgroup", th: "columnheader", thead: "rowgroup", time: "time",
      tr: "row", ul: "list",
    };

    if (tag === "input") {
      const inputRoles = {
        button: "button", checkbox: "checkbox", email: "textbox", file: "button",
        image: "button", number: "spinbutton", radio: "radio", range: "slider",
        reset: "button", search: "searchbox", submit: "button", tel: "textbox",
        text: "textbox", url: "textbox",
      };
      return inputRoles[type || ""] || "textbox";
    }

    const roleOrFn = tagRoles[tag];
    if (typeof roleOrFn === "function") return roleOrFn(element);
    return roleOrFn || "generic";
  }

  function getResolvedRole(element) {
    const explicitRole = getExplicitRole(element);
    if (!explicitRole) return getImplicitRole(element);
    if ((explicitRole === "none" || explicitRole === "presentation") && isFocusable(element)) {
      return getImplicitRole(element);
    }
    return explicitRole;
  }

  function getOrAssignRef(element, role, name) {
    const existing = element._piRef;
    if (existing && existing.role === role && existing.name === name) {
      return existing.ref;
    }
    const ref = `e${++globalRefCounter}`;
    element._piRef = { role, name, ref };
    window.__piRefCounter = globalRefCounter;
    return ref;
  }

  function getName(element) {
    const tag = element.tagName.toLowerCase();

    const labelledBy = element.getAttribute('aria-labelledby');
    if (labelledBy) {
      const names = labelledBy.split(/\\s+/).map(id => {
        const el = document.getElementById(id);
        return el?.textContent?.trim() || '';
      }).filter(Boolean);
      if (names.length) {
        const joined = names.join(' ');
        return joined.length > 100 ? joined.substring(0, 100) + '...' : joined;
      }
    }

    if (tag === "select") {
      const selected = element.querySelector("option[selected]") ||
        (element.selectedIndex >= 0 ? element.options[element.selectedIndex] : null);
      if (selected?.textContent?.trim()) return selected.textContent.trim();
    }

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel?.trim()) return ariaLabel.trim();

    const placeholder = element.getAttribute("placeholder");
    if (placeholder?.trim()) return placeholder.trim();

    const title = element.getAttribute("title");
    if (title?.trim()) return title.trim();

    const alt = element.getAttribute("alt");
    if (alt?.trim()) return alt.trim();

    if (element.id) {
      const label = document.querySelector(`label[for="${element.id}"]`);
      if (label?.textContent?.trim()) return label.textContent.trim();
    }

    if (tag === "input") {
      const type = element.getAttribute("type") || "";
      const value = element.getAttribute("value");
      if (type === "submit" && value?.trim()) return value.trim();
      if (element.value && element.value.length < 50 && element.value.trim()) return element.value.trim();
    }

    if (["button", "a", "summary"].includes(tag)) {
      let textContent = "";
      for (const node of element.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) textContent += node.textContent;
      }
      if (textContent.trim()) return textContent.trim();
    }

    if (/^h[1-6]$/.test(tag)) {
      const text = element.textContent;
      if (text?.trim()) {
        const t = text.trim();
        return t.length > 100 ? t.substring(0, 100) + "..." : t;
      }
    }

    if (tag === "img") return "";

    let directText = "";
    for (const node of element.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) directText += node.textContent;
    }
    if (directText?.trim() && directText.trim().length >= 3) {
      const text = directText.trim();
      return text.length > 100 ? text.substring(0, 100) + "..." : text;
    }

    return "";
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      style.opacity !== "0" &&
      element.offsetWidth > 0 &&
      element.offsetHeight > 0
    );
  }

  function isInteractive(element) {
    const tag = element.tagName.toLowerCase();
    return (
      ["a", "button", "input", "select", "textarea", "details", "summary"].includes(tag) ||
      element.hasAttribute("onclick") ||
      element.hasAttribute("tabindex") ||
      element.getAttribute("role") === "button" ||
      element.getAttribute("role") === "link" ||
      element.getAttribute("contenteditable") === "true"
    );
  }

  function isLandmark(element) {
    const tag = element.tagName.toLowerCase();
    return (
      ["h1", "h2", "h3", "h4", "h5", "h6", "nav", "main", "header", "footer", "section", "article", "aside"].includes(tag) ||
      element.hasAttribute("role")
    );
  }

  function hasCursorPointer(element) {
    const style = window.getComputedStyle(element);
    return style.cursor === "pointer";
  }

  function getAriaProps(element) {
    const props = {};
    const checkedAttr = element.getAttribute('aria-checked');
    if (checkedAttr === 'true') props.checked = true;
    else if (checkedAttr === 'false') props.checked = false;
    else if (element instanceof HTMLInputElement && (element.type === 'checkbox' || element.type === 'radio')) {
      props.checked = element.checked;
    }

    if (element.getAttribute('aria-disabled') === 'true' || element.disabled) {
      props.disabled = true;
    }

    const expandedAttr = element.getAttribute('aria-expanded');
    if (expandedAttr === 'true') props.expanded = true;
    else if (expandedAttr === 'false') props.expanded = false;

    const tag = element.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) {
      props.level = parseInt(tag[1], 10);
    }

    return props;
  }

  function formatAriaProps(props) {
    const parts = [];
    if (props.checked !== undefined) {
      parts.push(props.checked ? '[checked]' : '[unchecked]');
    }
    if (props.disabled) parts.push('[disabled]');
    if (props.expanded !== undefined) {
      parts.push(props.expanded ? '[expanded]' : '[collapsed]');
    }
    if (props.level !== undefined) {
      parts.push(`[level=${props.level}]`);
    }
    return parts.join(' ');
  }

  function shouldInclude(element, filter) {
    const tag = element.tagName.toLowerCase();
    if (["script", "style", "meta", "link", "title", "noscript"].includes(tag)) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    if (!isVisible(element)) return false;

    const rect = element.getBoundingClientRect();
    if (!(rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0)) {
      return false;
    }

    if (filter === "interactive") return isInteractive(element);
    if (isInteractive(element)) return true;
    if (isLandmark(element)) return true;
    if (getName(element).length > 0) return true;

    const role = getResolvedRole(element);
    return role !== "generic" && role !== "img";
  }

  function traverse(element, depth, filter, maxDepth) {
    const lines = [];
    const include = shouldInclude(element, filter);

    if (include) {
      const role = getResolvedRole(element);
      const name = getName(element);
      const ariaProps = getAriaProps(element);

      const elemRefId = getOrAssignRef(element, role, name);
      window.__piRefs[elemRefId] = element;
      window.__piElementMap[elemRefId] = { element: element, role, name };

      const indent = "  ".repeat(depth);
      let line = `${indent}${role}`;
      if (name) {
        const escapedName = name.replace(/\\s+/g, " ").replace(/"/g, '\\\\"');
        line += ` "${escapedName}"`;
      }
      line += ` [${elemRefId}]`;

      const propsStr = formatAriaProps(ariaProps);
      if (propsStr) line += ` ${propsStr}`;

      if (hasCursorPointer(element)) {
        line += " [cursor=pointer]";
      }

      const href = element.getAttribute("href");
      if (href) line += ` href="${href}"`;

      lines.push(line);
    }

    if (depth < maxDepth) {
      for (const child of element.children) {
        lines.push(...traverse(child, include ? depth + 1 : depth, filter, maxDepth));
      }
    }

    return lines;
  }

  const lines = traverse(document.body, 0, filter, maxDepth);
  const content = lines.join("\\n");

  return {
    pageContent: content + `\\n\\n[Viewport: ${window.innerWidth}x${window.innerHeight}]`,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    url: window.location.href,
    title: document.title
  };
})
'''

GET_ELEMENT_COORDS_SCRIPT = '''
(function(ref) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  const rect = element.getBoundingClientRect();
  return {
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top + rect.height / 2),
    width: rect.width,
    height: rect.height
  };
})
'''

CLICK_ELEMENT_SCRIPT = '''
(function(ref) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  element.click();
  return { success: true };
})
'''

CLICK_SELECTOR_SCRIPT = '''
(function(selector) {
  const element = document.querySelector(selector);
  if (!element) {
    return { error: `No element matches selector: ${selector}` };
  }
  element.click();
  const rect = element.getBoundingClientRect();
  return {
    success: true,
    selector: selector,
    tag: element.tagName.toLowerCase(),
    text: (element.textContent || '').trim().substring(0, 80),
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top + rect.height / 2)
  };
})
'''

GET_SELECTOR_COORDS_SCRIPT = '''
(function(selector) {
  const element = document.querySelector(selector);
  if (!element) {
    return { error: `No element matches selector: ${selector}` };
  }
  const rect = element.getBoundingClientRect();
  return {
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top + rect.height / 2),
    width: rect.width,
    height: rect.height
  };
})
'''

TYPE_IN_ELEMENT_SCRIPT = '''
(function(ref, value) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  element.focus();
  if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (element.contentEditable === 'true') {
    element.textContent = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }
  return { success: true };
})
'''

GET_PAGE_TEXT_SCRIPT = '''
(function() {
  const article = document.querySelector("article");
  const main = document.querySelector("main");
  const content = article || main || document.body;
  const text = content.textContent?.replace(/\\s+/g, " ").trim().substring(0, 50000) || "";
  return { text, title: document.title, url: window.location.href };
})()
'''
