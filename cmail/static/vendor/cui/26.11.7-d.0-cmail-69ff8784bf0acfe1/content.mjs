/* A DOM lifecycle boundary. Renderers are trusted host code, never JSON callbacks. */
export function createContentRegion({root, renderers}) {
  let generation = 0, mounted, controller, disposed = false;
  const release = () => { const old = mounted; mounted = null; old?.dispose?.(); };
  return {
    async show({type, value, context = {}}) {
      if (disposed) return false;
      const render = Object.hasOwn(renderers, type) ? renderers[type] : undefined;
      if (typeof render !== 'function') throw new TypeError('Renderer de conteúdo indisponível.');
      const revision = ++generation; controller?.abort(); release(); controller = new AbortController();
      const slot = root.ownerDocument.createElement('div'); slot.className = 'cui-content-slot ca-content-slot';
      root.replaceChildren(slot); root.setAttribute('aria-busy', 'true');
      try {
        const handle = await render({root: slot, value, context, signal: controller.signal});
        if (revision !== generation) { handle?.dispose?.(); return false; }
        mounted = handle; return true;
      } catch (error) {
        if (revision !== generation) return false;
        slot.textContent = 'Não foi possível apresentar o conteúdo.'; throw error;
      } finally { if (revision === generation) root.removeAttribute('aria-busy'); }
    },
    dispose() {
      if (disposed) return;
      disposed = true; ++generation; controller?.abort();
      try { release(); } finally { root.replaceChildren(); root.removeAttribute('aria-busy'); }
    },
  };
}

/* Official CCR createChatRenderer factory is supplied by the consumer, lazily. */
export function createCcrContent({createChatRenderer, options = {}}) {
  if (typeof createChatRenderer !== 'function') throw new TypeError('Factory CCR obrigatória.');
  let renderer;
  return ({root, value, context}) => {
    renderer ||= createChatRenderer(options);
    const handle = renderer.update(root, value, context);
    return {dispose() { if (handle?.dispose) handle.dispose(); else renderer.dispose(root); }};
  };
}
