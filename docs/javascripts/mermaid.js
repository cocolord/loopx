const renderMermaid = async () => {
  const nodes = document.querySelectorAll(".mermaid:not([data-processed])");
  if (nodes.length === 0) return;

  const { default: mermaid } = await import(
    "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"
  );
  mermaid.initialize({ startOnLoad: false, theme: "dark" });
  await mermaid.run({ nodes });
};

if (typeof document$ === "undefined") {
  document.addEventListener("DOMContentLoaded", renderMermaid);
} else {
  document$.subscribe(renderMermaid);
}
