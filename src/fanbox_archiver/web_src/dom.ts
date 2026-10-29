namespace FanboxUI {
  export type DOMChild = Node | string | number | null | undefined | false | DOMChild[];

  function appendChild(parent: HTMLElement | DocumentFragment, child: DOMChild): void {
    if (Array.isArray(child)) {
      for (const item of child) appendChild(parent, item);
    } else if (child instanceof Node) {
      parent.append(child);
    } else if (child !== null && child !== undefined && child !== false) {
      parent.append(document.createTextNode(String(child)));
    }
  }

  export function h(
    tag: string, attrs: Record<string, unknown> = {}, ...children: DOMChild[]
  ): HTMLElement {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2), value as EventListener);
      } else if (value !== null && value !== undefined && value !== false) {
        node.setAttribute(key, value === true ? "" : String(value));
      }
    }
    for (const child of children) appendChild(node, child);
    return node;
  }
}
