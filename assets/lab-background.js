// Laser-scanning microscope background.
// The pointer is a focused excitation beam scanning a field of faint "cells":
//  - fluorescent labels (cytoplasm) light up and fade slowly: a visible lifetime;
//  - Raman-active nuclei and lipid droplets respond only while illuminated: no lifetime;
//  - a click fires a pump pulse followed by a delayed probe pulse, as in ultrafast spectroscopy.
(() => {
  const canvas = document.querySelector(".lab-canvas");
  const context = canvas && canvas.getContext ? canvas.getContext("2d") : null;

  if (!context || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  const root = document.documentElement;
  const finePointer = window.matchMedia("(pointer: fine)").matches;
  const GRID = 13;
  const BEAM_SIGMA = 40;
  const LIFETIME = { fluor: 1.6, protein: 0.14, lipid: 0.14 };
  const GAIN = { fluor: 16, protein: 24, lipid: 24 };
  const PULSE_SPEED = 620;
  const PULSE_RANGE = 460;
  const PROBE_DELAY = 0.18;

  let width = 0;
  let height = 0;
  let molecules = [];
  let palette = {};
  let pulses = [];
  let lastPointerAt = -Infinity;
  let lastFrame = performance.now();
  let clock = 0;
  let frame = 0;
  const pointer = { x: 0, y: 0 };
  const beam = { x: 0, y: 0 };

  const readPalette = () => {
    const styles = getComputedStyle(root);
    const value = (name) => styles.getPropertyValue(name).trim();
    const dark = root.dataset.theme === "dark";
    palette = {
      fluor: value("--hue-1"),
      protein: value("--hue-2"),
      lipid: value("--hue-3"),
      beam: value("--accent"),
      strength: dark ? 1 : 0.95
    };
  };

  const random = (min, max) => min + Math.random() * (max - min);

  // Point-in-rotated-ellipse test, returning the normalised radius (<1 is inside).
  const ellipseRadius = (x, y, shape) => {
    const dx = x - shape.x;
    const dy = y - shape.y;
    const cos = Math.cos(shape.angle);
    const sin = Math.sin(shape.angle);
    const u = (dx * cos + dy * sin) / shape.rx;
    const v = (-dx * sin + dy * cos) / shape.ry;
    return Math.sqrt(u * u + v * v);
  };

  const buildSample = () => {
    const cells = [];
    const cellCount = Math.max(6, Math.round((width * height) / 60000));

    for (let index = 0; index < cellCount; index += 1) {
      const rx = random(55, 120);
      const cell = {
        x: random(0, width),
        y: random(0, height),
        rx,
        ry: rx * random(0.55, 0.9),
        angle: random(0, Math.PI)
      };
      cell.nucleus = {
        x: cell.x + random(-0.15, 0.15) * rx,
        y: cell.y + random(-0.15, 0.15) * rx,
        rx: rx * random(0.28, 0.36),
        ry: rx * random(0.22, 0.3),
        angle: cell.angle
      };
      cell.droplets = Array.from({ length: Math.round(random(2, 5)) }, () => {
        const theta = random(0, Math.PI * 2);
        const distance = random(0.5, 0.78);
        const radius = random(5, 10);
        return {
          x: cell.x + Math.cos(theta) * cell.rx * distance * 0.9,
          y: cell.y + Math.sin(theta) * cell.ry * distance * 0.9,
          rx: radius,
          ry: radius,
          angle: 0
        };
      });
      cells.push(cell);
    }

    molecules = [];

    for (let y = GRID / 2; y < height; y += GRID) {
      for (let x = GRID / 2; x < width; x += GRID) {
        const px = x + random(-4, 4);
        const py = y + random(-4, 4);
        let type = null;

        for (const cell of cells) {
          if (ellipseRadius(px, py, cell) > 1) {
            continue;
          }

          if (cell.droplets.some((droplet) => ellipseRadius(px, py, droplet) <= 1)) {
            type = "lipid";
          } else if (ellipseRadius(px, py, cell.nucleus) <= 1) {
            type = "protein";
          } else if (Math.random() < 0.6) {
            type = "fluor";
          }
          break;
        }

        if (type) {
          molecules.push({ x: px, y: py, type, level: 0 });
        }
      }
    }
  };

  const resize = () => {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    buildSample();
  };

  // Idle or touch visitors see the beam raster the field on its own.
  const autoScanTarget = (time) => ({
    x: width * (0.5 + 0.44 * Math.sin(time * 0.11)),
    y: height * (0.5 + 0.4 * Math.sin(time * 0.17 + 1.2))
  });

  const excite = (dt) => {
    const twoSigma2 = 2 * BEAM_SIGMA * BEAM_SIGMA;
    const reach2 = (BEAM_SIGMA * 3) ** 2;

    for (const molecule of molecules) {
      molecule.level *= Math.exp(-dt / LIFETIME[molecule.type]);

      const dx = molecule.x - beam.x;
      const dy = molecule.y - beam.y;
      const distance2 = dx * dx + dy * dy;

      if (distance2 < reach2) {
        molecule.level = Math.min(1, molecule.level + Math.exp(-distance2 / twoSigma2) * GAIN[molecule.type] * dt);
      }

      for (const pulse of pulses) {
        const radius = (clock - pulse.start) * PULSE_SPEED;
        if (radius <= 0) {
          continue;
        }
        const fromPulse = Math.hypot(molecule.x - pulse.x, molecule.y - pulse.y);
        if (Math.abs(fromPulse - radius) < 9) {
          molecule.level = Math.max(molecule.level, pulse.probe ? 0.75 : 0.95);
        }
      }
    }
  };

  const drawMolecules = () => {
    const strength = palette.strength;

    for (const molecule of molecules) {
      const level = molecule.level;
      if (level < 0.02) {
        continue;
      }

      context.fillStyle = palette[molecule.type];

      if (molecule.type === "fluor") {
        // Soft, glowing emitters.
        context.globalAlpha = level * 0.24 * strength;
        context.beginPath();
        context.arc(molecule.x, molecule.y, 4 + level * 6, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = level * 0.95 * strength;
        context.beginPath();
        context.arc(molecule.x, molecule.y, 1.2 + level * 1.8, 0, Math.PI * 2);
        context.fill();
      } else {
        // Sharp, spectrally narrow Raman points drawn as small diamonds.
        const size = 1.6 + level * 2.2;
        context.globalAlpha = Math.min(1, level * 1.1) * strength;
        context.beginPath();
        context.moveTo(molecule.x, molecule.y - size);
        context.lineTo(molecule.x + size, molecule.y);
        context.lineTo(molecule.x, molecule.y + size);
        context.lineTo(molecule.x - size, molecule.y);
        context.closePath();
        context.fill();
      }
    }
  };

  const drawBeam = () => {
    const glow = context.createRadialGradient(beam.x, beam.y, 0, beam.x, beam.y, BEAM_SIGMA * 2.6);
    glow.addColorStop(0, palette.beam);
    glow.addColorStop(1, "transparent");
    context.globalAlpha = 0.12 * palette.strength;
    context.fillStyle = glow;
    context.beginPath();
    context.arc(beam.x, beam.y, BEAM_SIGMA * 2.6, 0, Math.PI * 2);
    context.fill();

    // Focus reticle.
    context.globalAlpha = 0.35 * palette.strength;
    context.strokeStyle = palette.beam;
    context.lineWidth = 1;
    context.beginPath();
    context.arc(beam.x, beam.y, 11, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.moveTo(beam.x - 18, beam.y);
    context.lineTo(beam.x - 14, beam.y);
    context.moveTo(beam.x + 14, beam.y);
    context.lineTo(beam.x + 18, beam.y);
    context.moveTo(beam.x, beam.y - 18);
    context.lineTo(beam.x, beam.y - 14);
    context.moveTo(beam.x, beam.y + 14);
    context.lineTo(beam.x, beam.y + 18);
    context.stroke();
  };

  const drawPulses = () => {
    pulses = pulses.filter((pulse) => (clock - pulse.start) * PULSE_SPEED < PULSE_RANGE);

    for (const pulse of pulses) {
      const radius = (clock - pulse.start) * PULSE_SPEED;
      if (radius <= 0) {
        continue;
      }
      context.globalAlpha = (1 - radius / PULSE_RANGE) * 0.45 * palette.strength;
      context.strokeStyle = pulse.probe ? palette.protein : palette.beam;
      context.lineWidth = pulse.probe ? 1 : 1.6;
      context.beginPath();
      context.arc(pulse.x, pulse.y, radius, 0, Math.PI * 2);
      context.stroke();
    }
  };

  const render = (now) => {
    const dt = Math.min((now - lastFrame) / 1000, 0.05);
    lastFrame = now;
    clock += dt;

    const idle = !finePointer || clock - lastPointerAt > 4;
    const target = idle ? autoScanTarget(clock) : pointer;
    const follow = 1 - Math.exp(-dt * (idle ? 3 : 12));
    beam.x += (target.x - beam.x) * follow;
    beam.y += (target.y - beam.y) * follow;

    excite(dt);

    context.clearRect(0, 0, width, height);
    drawMolecules();
    drawPulses();
    drawBeam();
    context.globalAlpha = 1;

    frame = window.requestAnimationFrame(render);
  };

  const firePulsePair = (x, y) => {
    pulses.push({ x, y, start: clock, probe: false });
    pulses.push({ x, y, start: clock + PROBE_DELAY, probe: true });
    pulses = pulses.slice(-8);
  };

  window.addEventListener("pointermove", (event) => {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
    lastPointerAt = clock;
  }, { passive: true });

  window.addEventListener("pointerdown", (event) => {
    if (event.target.closest("a, button, input, textarea, select, summary")) {
      return;
    }
    firePulsePair(event.clientX, event.clientY);
  }, { passive: true });

  let resizeTimer;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(resize, 150);
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      window.cancelAnimationFrame(frame);
    } else {
      lastFrame = performance.now();
      frame = window.requestAnimationFrame(render);
    }
  });

  new MutationObserver(readPalette).observe(root, { attributes: true, attributeFilter: ["data-theme"] });

  // A short explanation for visitors, shown once and then faded away.
  const hint = document.querySelector(".lab-hint");
  if (hint) {
    hint.textContent = finePointer
      ? "Background: a scanning laser. Move to excite fluorescence & Raman signals; click for a pump–probe pulse."
      : "Background: a scanning laser exciting fluorescence & Raman signals. Tap for a pump–probe pulse.";
    hint.hidden = false;
    window.setTimeout(() => hint.classList.add("is-faded"), 9000);
  }

  readPalette();
  resize();
  beam.x = width / 2;
  beam.y = height / 2;
  frame = window.requestAnimationFrame(render);
})();
