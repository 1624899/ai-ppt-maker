(() => {
  function resolveImageTarget(startNode) {
    if (!(startNode instanceof Element)) {
      return null;
    }
    return startNode.closest("[data-lightbox-src]");
  }

  function bindDialogClose(dialog) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) {
        dialog.close();
      }
    });
  }

  function createImageLightbox(options = {}) {
    const dialog = document.querySelector(options.dialogSelector || "#imageLightbox");
    if (!dialog) {
      return null;
    }

    const image = dialog.querySelector(options.imageSelector || "#imageLightboxPreview");
    const caption = dialog.querySelector(options.captionSelector || "#imageLightboxCaption");
    const closeButton = dialog.querySelector(options.closeSelector || "#imageLightboxClose");

    if (!image || !caption || !closeButton) {
      return null;
    }

    closeButton.addEventListener("click", () => dialog.close());
    bindDialogClose(dialog);

    function open(payload) {
      const src = String(payload?.src || "").trim();
      if (!src) {
        return;
      }

      image.src = src;
      image.alt = String(payload?.alt || payload?.caption || "放大预览");
      caption.textContent = String(payload?.caption || payload?.alt || "");
      dialog.showModal();
    }

    function bindRoot(root = document) {
      root.addEventListener("click", (event) => {
        const trigger = resolveImageTarget(event.target);
        if (!trigger) {
          return;
        }
        open({
          src: trigger.dataset.lightboxSrc,
          alt: trigger.dataset.lightboxAlt,
          caption: trigger.dataset.lightboxCaption,
        });
      });
    }

    return {
      open,
      bindRoot,
    };
  }

  window.createImageLightbox = createImageLightbox;
})();
