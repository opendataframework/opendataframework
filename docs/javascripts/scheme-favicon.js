// Swaps the favicon with the docs site's light/dark toggle: light.svg for
// mkdocs-material's "default" scheme, dark.svg for "slate". The header logo
// switches in CSS (overrides/partials/logo.html), but a <link rel="icon">
// can't, so this mirrors `data-md-color-scheme` on <body> into its href,
// resolved against the current one so it works from nested pages too.
(function () {
  const link = document.querySelector('link[rel="icon"]');
  if (!link) return;

  const sync = () => {
    const scheme = document.body.getAttribute("data-md-color-scheme");
    const name = scheme === "slate" ? "dark.svg" : "light.svg";
    link.href = new URL(name, link.href).href;
  };

  sync();
  new MutationObserver(sync).observe(document.body, {
    attributes: true,
    attributeFilter: ["data-md-color-scheme"],
  });
})();
