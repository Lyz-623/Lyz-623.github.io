// Reads the cumulative pageview total recorded by MapMyVisitors and shows it in the footer.
// The provider's map is rendered off-screen; only the number is displayed.
(() => {
  const pill = document.querySelector(".footer-visits");
  const mapId = pill && pill.dataset.mapId ? pill.dataset.mapId.trim() : "";

  if (!/^[A-Za-z0-9_-]{16,128}$/.test(mapId)) {
    return;
  }

  const host = document.createElement("div");
  host.className = "visit-count-host";
  host.setAttribute("aria-hidden", "true");
  document.body.append(host);

  const observer = new MutationObserver(() => {
    const counter = host.querySelector(".mapmyvisitors-visitors");
    const digits = counter ? counter.textContent.replace(/[^\d]/g, "") : "";

    if (digits && !host.querySelector(".mapmyvisitors-loading")) {
      observer.disconnect();
      window.clearTimeout(timer);
      pill.querySelector("[data-visit-count]").textContent = Number(digits).toLocaleString("en");
      pill.hidden = false;
    }
  });

  const timer = window.setTimeout(() => observer.disconnect(), 15000);
  observer.observe(host, { childList: true, subtree: true, characterData: true });

  const script = document.createElement("script");
  script.id = "mapmyvisitors";
  script.async = true;
  script.src = `https://mapmyvisitors.com/map.js?${new URLSearchParams({ d: mapId, cl: "d8e1de", co: "f6f8f7", ct: "356d75", w: "a", t: "tt" })}`;
  host.append(script);
})();
