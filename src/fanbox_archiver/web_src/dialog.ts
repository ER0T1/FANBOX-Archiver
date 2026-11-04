namespace FanboxUI {
  export interface ConfirmDialogOptions {
    title: string;
    message: string;
    /** The safe choice; focused first and chosen by Esc. */
    cancelLabel: string;
    confirmLabel: string;
    danger?: boolean;
  }

  /**
   * An in-page confirmation in the app's own card style (never `window.confirm`). Resolves true
   * only for the confirm button; Esc, the cancel button or closing resolve false. Focus is trapped
   * by the modal <dialog> and returns to where it was.
   */
  export function confirmDialog(options: ConfirmDialogOptions): Promise<boolean> {
    const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const titleId = `dialog-title-${Math.random().toString(36).slice(2, 9)}`;
    const cancel = h("button", {type: "button", class: "dialog-cancel", value: "cancel"}, options.cancelLabel);
    const confirm = h("button", {type: "button", class: options.danger ? "dialog-confirm danger" : "dialog-confirm primary",
      value: "confirm"}, options.confirmLabel);
    const dialog = h("dialog", {class: "app-dialog", "aria-labelledby": titleId},
      h("h2", {id: titleId}, options.title),
      h("p", {}, options.message),
      h("div", {class: "dialog-actions"}, cancel, confirm)) as HTMLDialogElement;
    document.body.append(dialog);
    return new Promise(resolve => {
      let settled = false;
      const finish = (result: boolean): void => {
        if (settled) return;
        settled = true;
        if (dialog.open) dialog.close();
        dialog.remove();
        returnFocus?.focus();
        resolve(result);
      };
      cancel.addEventListener("click", () => finish(false));
      confirm.addEventListener("click", () => finish(true));
      dialog.addEventListener("cancel", event => { event.preventDefault(); finish(false); });
      dialog.addEventListener("close", () => finish(false));
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
      cancel.focus();
    });
  }
}
