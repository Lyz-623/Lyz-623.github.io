(() => {
  const section = document.querySelector('.visitor-section');
  if (!section) return;

  const mapId = section.dataset.mapId.trim();
  const shell = section.querySelector('.visitor-map-shell');
  const message = section.querySelector('.visitor-map-message');
  const status = section.querySelector('.visitor-status');
  const button = section.querySelector('.visitor-load');
  const widget = section.querySelector('.visitor-widget');
  const privacy = section.querySelector('.visitor-privacy');
  const statsLink = section.querySelector('.visitor-stats-link');

  // An unconfigured map never loads a third-party tracker or displays invented counts.
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(mapId)) return;

  const setStatsLink = (value) => {
    try {
      const url = new URL(value);
      if (['https:', 'http:'].includes(url.protocol) && url.hostname === 'mapmyvisitors.com'
        && /^\/web\/[a-z0-9]+\/?$/i.test(url.pathname)) {
        url.protocol = 'https:';
        statsLink.href = url.href;
        statsLink.hidden = false;
      }
    } catch {}
  };
  setStatsLink(section.dataset.statsUrl);

  privacy.hidden = false;
  button.hidden = false;
  shell.dataset.visitorState = 'consent';
  status.textContent = 'Visitor map and cumulative visits';

  let started = false;
  const fitMap = () => {
    const map = widget.querySelector('.mapmyvisitors-map');
    if (!map) return;
    const width = Number.parseFloat(map.style.width);
    const height = Number.parseFloat(map.style.height);
    if (!(width > 0 && height > 0)) return;
    // Scale the provider's fixed-size map and marker overlay together.
    const scale = widget.clientWidth / width;
    map.style.transform = `scale(${scale})`;
    map.style.marginBottom = `${height * (scale - 1)}px`;
  };
  const resizeObserver = new ResizeObserver(fitMap);
  resizeObserver.observe(widget);

  const start = () => {
    if (started) return;
    started = true;
    button.hidden = true;
    widget.hidden = false;
    status.textContent = 'Loading visitor statistics...';
    shell.dataset.visitorState = 'loading';

    const script = document.createElement('script');
    script.id = 'mapmyvisitors';
    script.async = true;
    const params = new URLSearchParams({
      d: mapId, cl: 'd8e1de', co: 'f6f8f7', ct: '356d75',
      cmo: '356d75', cmn: '88a6bf', w: 'a', t: 'tt'
    });
    script.src = `https://mapmyvisitors.com/map.js?${params}`;

    let timer;
    const fail = () => {
      observer.disconnect();
      window.clearTimeout(timer);
      widget.hidden = true;
      message.hidden = false;
      shell.dataset.visitorState = 'unavailable';
      status.textContent = 'Visitor statistics are temporarily unavailable.';
    };

    const observer = new MutationObserver(() => {
      const counter = widget.querySelector('.mapmyvisitors-visitors');
      const loading = widget.querySelector('.mapmyvisitors-loading');
      if (counter?.textContent.trim() && !loading) {
        observer.disconnect();
        window.clearTimeout(timer);
        message.hidden = true;
        shell.dataset.visitorState = 'ready';
        fitMap();
        setStatsLink(widget.querySelector('#mapmyvisitors-widget')?.href);
      }
    });
    observer.observe(widget, { childList: true, subtree: true, characterData: true });
    script.addEventListener('error', fail, { once: true });
    timer = window.setTimeout(fail, 15000);
    widget.append(script);
  };

  // Explicit opt-in is kept for this tab only; changing themes does not reload the tracker.
  button.addEventListener('click', () => {
    try { window.sessionStorage.setItem('yunze-visitor-statistics', 'enabled'); } catch {}
    start();
  }, { once: true });

  try {
    if (window.sessionStorage.getItem('yunze-visitor-statistics') === 'enabled') start();
  } catch {}
})();
