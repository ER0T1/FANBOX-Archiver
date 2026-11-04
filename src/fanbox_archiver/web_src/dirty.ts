namespace FanboxUI {
  /** One editable value and the element that is marked when it differs from the saved value. */
  export interface TrackedField {
    node: HTMLElement;
    read(): unknown;
  }

  export interface DirtyTracker {
    isDirty(): boolean;
    /** Re-compare every field now (edits are also noticed automatically). */
    refresh(): void;
  }

  /**
   * Marks changed fields with a visible "已變更" label (not colour alone) and reports whether
   * anything is unsaved. Edits are noticed from input/change/click events inside `root`, which
   * covers checkboxes, numbers, text, custom selects, schedule day buttons and the colour editor.
   */
  export function trackChanges(
    root: HTMLElement, fields: TrackedField[], onChange: (dirty: boolean) => void,
  ): DirtyTracker {
    const serialize = (field: TrackedField): string => JSON.stringify(field.read());
    const saved = fields.map(serialize);
    let dirty = false;
    const refresh = (): void => {
      let any = false;
      fields.forEach((field, index) => {
        const changed = serialize(field) !== saved[index];
        any ||= changed;
        field.node.classList.toggle("is-dirty", changed);
        let badge = field.node.querySelector<HTMLElement>(":scope > .dirty-badge");
        if (changed && !badge) {
          badge = h("span", {class: "dirty-badge"}, t("common.changed"));
          field.node.append(badge);
        } else if (!changed && badge) {
          badge.remove();
        }
      });
      if (any !== dirty) {
        dirty = any;
        onChange(dirty);
      }
    };
    let pending: number | undefined;
    const schedule = (): void => {
      if (pending !== undefined) clearTimeout(pending);
      // After the control's own handlers have updated its value.
      pending = window.setTimeout(() => { pending = undefined; refresh(); }, 0);
    };
    for (const type of ["input", "change", "click"]) root.addEventListener(type, schedule);
    return {isDirty: () => { refresh(); return dirty; }, refresh};
  }
}
