// Broadband light ripples drawn behind the page with WebGL.
// Each click launches a short white-light pulse as a cylindrical wave:
//  - eight wavelength bands (410-690 nm) are summed incoherently, each in its spectral colour;
//  - each band interferes coherently with the same band of other ripples;
//  - normal dispersion makes red travel slightly faster than blue, so a ring spreads into a rainbow;
//  - amplitude falls off as 1/sqrt(r) and the pulse slowly fades.
(() => {
  const canvas = document.querySelector(".ripple-canvas");

  if (!canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  const gl = canvas.getContext("webgl", { premultipliedAlpha: true, alpha: true, antialias: false });

  if (!gl) {
    return;
  }

  const MAX_SOURCES = 8;
  const BANDS = 8;
  const LIFETIME = 9;
  const RENDER_SCALE = 0.75;

  // Approximate visible-spectrum colour for a wavelength in nanometres.
  const spectralRgb = (nm) => {
    let r = 0;
    let g = 0;
    let b = 0;

    if (nm < 440) {
      r = (440 - nm) / 60;
      b = 1;
    } else if (nm < 490) {
      g = (nm - 440) / 50;
      b = 1;
    } else if (nm < 510) {
      g = 1;
      b = (510 - nm) / 20;
    } else if (nm < 580) {
      r = (nm - 510) / 70;
      g = 1;
    } else if (nm < 645) {
      r = 1;
      g = (645 - nm) / 65;
    } else {
      r = 1;
    }

    // Dim the ends of the spectrum, where the eye is less sensitive.
    const edge = nm < 420 ? 0.3 + 0.7 * (nm - 380) / 40 : nm > 650 ? 0.3 + 0.7 * (700 - nm) / 50 : 1;
    return [r * edge, g * edge, b * edge];
  };

  const wavelengths = [];
  const colours = [];
  const groupSpeeds = [];

  for (let index = 0; index < BANDS; index += 1) {
    const nm = 410 + (280 * index) / (BANDS - 1);
    wavelengths.push(9 + ((nm - 400) / 300) * 9);
    colours.push(spectralRgb(nm));
    groupSpeeds.push(70 * (1 + 0.14 * (nm - 550) / 140));
  }

  // Balance the bands so their sum is neutral white.
  const totals = [0, 1, 2].map((channel) => colours.reduce((sum, colour) => sum + colour[channel], 0));
  const flatColours = colours.flatMap((colour) => colour.map((value, channel) => (value / totals[channel]) * 2.4));

  const vertexSource = `
    attribute vec2 a_position;
    void main() { gl_Position = vec4(a_position, 0.0, 1.0); }
  `;

  const fragmentSource = `
    precision highp float;
    uniform vec2 u_resolution;
    uniform float u_pixel;
    uniform float u_time;
    uniform vec3 u_sources[${MAX_SOURCES}];
    uniform int u_count;
    uniform float u_lambda[${BANDS}];
    uniform float u_speed[${BANDS}];
    uniform vec3 u_colour[${BANDS}];

    void main() {
      vec2 point = vec2(gl_FragCoord.x, u_resolution.y - gl_FragCoord.y) * u_pixel;
      vec3 colour = vec3(0.0);

      for (int band = 0; band < ${BANDS}; band++) {
        float field = 0.0;

        for (int index = 0; index < ${MAX_SOURCES}; index++) {
          if (index >= u_count) {
            break;
          }

          vec3 source = u_sources[index];
          float age = u_time - source.z;

          if (age <= 0.0) {
            continue;
          }

          float radius = distance(point, source.xy);
          float front = u_speed[band] * age;
          float width = 14.0 + 5.0 * age;
          float envelope = exp(-pow((radius - front) / width, 2.0));
          float amplitude = envelope * inversesqrt(1.0 + radius / 90.0) * exp(-age / 4.5);
          float phase = 6.2831853 * (radius - 1.12 * front) / u_lambda[band];
          field += amplitude * cos(phase);
        }

        colour += u_colour[band] * field * field;
      }

      colour = 1.0 - exp(-colour * 3.6);
      float alpha = max(colour.r, max(colour.g, colour.b));
      gl_FragColor = vec4(colour, alpha);
    }
  `;

  const compile = (type, source) => {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    return gl.getShaderParameter(shader, gl.COMPILE_STATUS) ? shader : null;
  };

  const vertexShader = compile(gl.VERTEX_SHADER, vertexSource);
  const fragmentShader = compile(gl.FRAGMENT_SHADER, fragmentSource);

  if (!vertexShader || !fragmentShader) {
    return;
  }

  const program = gl.createProgram();
  gl.attachShader(program, vertexShader);
  gl.attachShader(program, fragmentShader);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    return;
  }

  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "a_position");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);

  const uniform = (name) => gl.getUniformLocation(program, name);
  const locations = {
    resolution: uniform("u_resolution"),
    pixel: uniform("u_pixel"),
    time: uniform("u_time"),
    sources: uniform("u_sources"),
    count: uniform("u_count")
  };

  gl.uniform1fv(uniform("u_lambda"), wavelengths);
  gl.uniform1fv(uniform("u_speed"), groupSpeeds);
  gl.uniform3fv(uniform("u_colour"), flatColours);

  let sources = [];
  let frame = 0;
  const start = performance.now();
  const now = () => (performance.now() - start) / 1000;

  const resize = () => {
    canvas.width = Math.max(1, Math.round(window.innerWidth * RENDER_SCALE));
    canvas.height = Math.max(1, Math.round(window.innerHeight * RENDER_SCALE));
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(locations.resolution, canvas.width, canvas.height);
    gl.uniform1f(locations.pixel, 1 / RENDER_SCALE);
    draw();
  };

  const draw = () => {
    const time = now();
    sources = sources.filter((source) => time - source[2] < LIFETIME);
    const packed = new Float32Array(MAX_SOURCES * 3);
    sources.forEach((source, index) => packed.set(source, index * 3));

    gl.uniform1f(locations.time, time);
    gl.uniform3fv(locations.sources, packed);
    gl.uniform1i(locations.count, sources.length);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    if (sources.length) {
      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }
  };

  // Animate only while ripples are alive, then rest.
  const loop = () => {
    draw();
    frame = sources.length && !document.hidden ? window.requestAnimationFrame(loop) : 0;
  };

  const launch = (x, y) => {
    sources.push([x, y, now()]);
    sources = sources.slice(-MAX_SOURCES);

    if (!frame) {
      frame = window.requestAnimationFrame(loop);
    }
  };

  window.addEventListener("pointerdown", (event) => {
    if (event.button > 0 || event.target.closest("a, button, input, textarea, select, summary, label")) {
      return;
    }
    launch(event.clientX, event.clientY);
  }, { passive: true });

  let resizeTimer;
  window.addEventListener("resize", () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(resize, 120);
  });

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && sources.length && !frame) {
      frame = window.requestAnimationFrame(loop);
    }
  });

  resize();

  // One gentle ripple on arrival hints that the background responds to clicks.
  window.setTimeout(() => launch(window.innerWidth * 0.72, window.innerHeight * 0.38), 700);
})();
