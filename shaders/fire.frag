// ============================================================================
// Fireplace — procedural flame core (fragment shader).
//
// This file is the single source of truth for how the fire looks. Every host
// loads THIS file:
//   - Lively Wallpaper (wallpaper behind the desktop icons)
//   - overlay/fireplace_overlay.py (transparent click-through window on top)
//   - tools/preview.html (browser harness used for tuning + verification)
//
// Contract with the host (Shadertoy-compatible, intentionally host-agnostic):
//   - The host PREPENDS  iResolution / iTime / iTimeDelta / iFrame / iMouse.
//   - The host APPENDS  main(), which calls mainImage().
//   - This file declares its own u* tuning uniforms, so a host that wants
//     sliders only needs to read the names out of here.
//   - mainImage() is forward-declared below because GLSL has no two-pass
//     compilation: the host's main() must be able to see it.
//
// Hosts: Lively Wallpaper (behind the desktop icons), overlay/fireplace_overlay.py
// (transparent click-through window), tools/preview.html (tuning harness),
// tools/render_still.py (offscreen stills for tests).
//
// All randomness derives from hashes of the pixel coordinate, never from a
// stateful RNG. Consequence: the same iTime always yields the same frame,
// which is what makes tools/render_still.py + tests/ deterministic.
//
// Tuning uniforms:
//   uIntensity  0.00 .. 1.00  overall flame brightness
//   uSpeed      0.00 .. 2.00  flame rise speed multiplier
//   uWarmth     0.00 .. 1.00  palette temperature (0 = deep red, 1 = white hot)
//   uScale      0.50 .. 2.00  flame size (vertical + horizontal together)
//   uDetail     0.00 .. 1.00  turbulence / domain-warp strength
//   uEmbers     0.00 .. 1.00  rising spark density
//   uRoom       0.00 .. 1.00  warm light cast onto the dark room
// ============================================================================

void mainImage(out vec4 fragColor, in vec2 fragCoord);

uniform float uIntensity;
uniform float uSpeed;
uniform float uWarmth;
uniform float uScale;
uniform float uDetail;
uniform float uEmbers;
uniform float uRoom;

// --- hash / noise / fbm -----------------------------------------------------

float hash1(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}

// Gradient noise in [-1, 1]. Quintic-free: smoothstep cubic is fine at this
// scale and cheaper.
float gnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(dot(hash2(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
                   dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
               mix(dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
                   dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x), u.y);
}

// Rotation+scale by 2.0 between octaves. Breaks the axis-aligned grid that
// plain fbm leaves behind.
const mat2 M2 = mat2(1.6, 1.2, -1.2, 1.6);

float fbm(vec2 p) {
    float f = 0.0;
    float a = 0.5;
    for (int i = 0; i < 5; i++) {
        f += a * gnoise(p);
        p = M2 * p;
        a *= 0.5;
    }
    return f;
}

// --- flame field -------------------------------------------------------------

// Scalar noise in roughly [0, 1]. p is already scrolled by the caller.
float flameNoise(vec2 p, float t, float detail) {
    float n = fbm(p);
    vec2 q = vec2(fbm(p + vec2(0.0, 0.0) + 0.15 * t),
                  fbm(p + vec2(5.2, 1.3) - 0.11 * t));
    vec2 r = vec2(fbm(p + 1.9 * q + vec2(1.7, 9.2) + 0.09 * t),
                  fbm(p + 1.9 * q + vec2(8.3, 2.8) - 0.13 * t));
    // detail mixes the warped field toward the plain one: low = smooth laminar
    // flame, high = turbulent.
    float v = mix(n, fbm(p + (1.4 + 2.6 * detail) * r), detail);
    return clamp(v * 0.9 + 0.5, 0.0, 1.0);
}

// Cheap 2-octave field for the ambient glow. The halo must NOT call
    // flameNoise(): that costs 4 fbm evaluations (20 octaves of gradient
    // noise), so paying it twice per pixel doubled the frame cost of the
    // wallpaper. The glow is broad and low-frequency, so two octaves are
    // visually indistinguishable. Measured: 18.9 -> 9.4 ms/frame at 1080p.
    float fbm2(vec2 p) {
        return 0.5 * gnoise(p) + 0.25 * gnoise(M2 * p);
    }

    float glowField(vec2 p, float t) {
        return clamp(0.5 + 1.5 * fbm2(p + vec2(0.0, t * 0.12)), 0.0, 1.0);
    }

// --- palette -----------------------------------------------------------------

// Blackbody-ish ramp: ember -> red -> orange -> yellow -> white.
vec3 firePalette(float x, float warmth) {
    x = clamp(x, 0.0, 1.0);
    vec3 c0 = vec3(0.10, 0.008, 0.000);
    vec3 c1 = vec3(0.72, 0.100, 0.015);
    vec3 c2 = vec3(1.00, 0.420, 0.050);
    vec3 c3 = vec3(1.00, 0.820, 0.360);
    vec3 c4 = vec3(1.00, 0.975, 0.910);

    vec3 c = mix(c0, c1, smoothstep(0.00, 0.28, x));
    c = mix(c, c2, smoothstep(0.24, 0.56, x));
    c = mix(c, c3, smoothstep(0.52, 0.80, x));
    c = mix(c, c4, smoothstep(0.78, 1.00, x));

    // warmth biases the ramp toward the white-hot end and lifts the floor,
    // which reads as "hotter fire" rather than "brighter fire".
    vec3 hot = mix(c, c4, 0.55 * warmth);
    return pow(max(hot, 0.0), vec3(mix(1.35, 0.85, warmth)));
}

// --- embers ------------------------------------------------------------------

float emberField(vec2 p, float t) {
    // Grid frequency sets CELL SIZE in pixels, so the core radius must be
    // chosen against it. The earlier 5.5x3.0 grid made ~14x12px cells and a
    // 0.07-cell radius — a sub-pixel spark that was mathematically present and
    // visually absent (measured contribution: +0.0003 mean brightness).
    // Sizing the spark at ~0.26 cell radius over a finer grid makes it land
    // on a few pixels at 1080p while still reading at small preview sizes.
    vec2 g = vec2(p.x * 18.0, p.y * 13.0 - t * 0.85);
    vec2 gi = floor(g);
    vec2 gf = fract(g);

    float h = hash1(gi);
    float on = step(0.962, h);           // only a few cells carry a spark
    float h2 = hash1(gi + 17.3);
    vec2 pos = vec2(0.15 + 0.70 * h2, 0.10 + 0.75 * fract(h * 7.31));

    // Slightly taller than wide: a rising ember smears vertically.
    float d = length((gf - pos) * vec2(1.0, 1.30));

    float core = smoothstep(0.26, 0.0, d);
    float halo = smoothstep(0.58, 0.12, d) * 0.30;

    // Per-cell twinkle, still a pure function of t
    float twinkle = 0.30 + 0.70 * fract(h * 3.77 + t * 0.9);
    return on * (core + halo) * twinkle;
}

// --- main --------------------------------------------------------------------

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    vec2 res = iResolution.xy;

    // Normalised, y up, origin at the hearth centre.
    vec2 uv = fragCoord / res;
    float aspect = res.x / max(res.y, 1.0);
    // Keep the flame the same visual weight on ultrawide as on 16:9.
    float aspectFix = clamp(aspect / 1.7777, 0.72, 1.0);

    float t = iTime * max(uSpeed, 0.0);

    // Screen-space coordinates: y = 0 at the hearth, 1 at the top of the frame.
    // The flame envelope MUST be anchored here. Deriving it from the scrolled
    // noise coordinates made the taper collapse into a full-height column once
    // t grew past ~1.3 s — caught by the vertical luminance profile in
    // tools/preview.html reading a uniform column of meanR across all bands.
    vec2 sp = vec2((uv.x - 0.5) * aspect * aspectFix, uv.y);

    // Noise coordinates: same layout, scrolled so the fire rises. Only the
    // noise may depend on time; the envelope may not.
    vec2 p = sp * (1.9 * uScale);
    p.y -= t * 0.75;

    // --- flame body ---------------------------------------------------------------

    float n = flameNoise(p, t, clamp(uDetail, 0.0, 1.0));

    // Flicker: low-frequency noise in time. Computed before the threshold
    // because a rising flame momentarily lowers the cutoff, so tongues reach
    // further up during a flare — that coupling is what stops the silhouette
    // from looking like a static shape being recoloured.
    float flick = 0.82 + 0.30 * (0.5 + 0.5 * fbm(vec2(t * 0.55, 3.7)));

    // The flame is a THRESHOLD on the noise field, not noise multiplied by an
    // envelope. Multiplying (body * tongue) was the earlier attempt and it
    // renders a clean symmetric triangle: the envelope forces heat to zero at
    // every boundary, so no separate tongue can ever break away. Thresholding
    // instead lets the noise decide where the edge falls, which is what makes
    // tips detach and the silhouette wander.
    //
    // cutoff rises with height and with distance from the hearth, so the
    // surviving region shrinks upward and inward, but its EDGE is fractal.
    //
    // Widths are explicit fractions of screen half-width (sp.x spans about
    // ±0.89 at 16:9). Dividing by an arbitrary constant instead made lat
    // bottom out below 1 across the whole frame, which dropped the cutoff to
    // ~0 everywhere and rendered one saturated blob filling the screen.
    float hFall = clamp(sp.y / (0.80 * uScale), 0.0, 1.0);
    float halfW = mix(0.40, 0.11, hFall * hFall) * uScale;
    float lat = abs(sp.x) / max(halfW, 1e-3);

    float cutoff = 0.30
                 + 0.52 * hFall
                 + 0.34 * clamp(lat, 0.0, 1.0)
                 - 0.26 * pow(max(flick - 0.82, 0.0) / 0.18, 2.0);

    float soft = 0.28;
    float heat = smoothstep(cutoff, cutoff + soft, n);

    // Keep the root of the fire continuous — a hearth flame has a solid base
    // where the fuel is, not scattered tongues. Confined to the bottom 12%.
    heat = max(heat, (1.0 - smoothstep(0.0, 0.12, sp.y))
                   * 0.75 * smoothstep(0.0, 0.35, n) * clamp(1.0 - lat, 0.0, 1.0));
    heat *= flick;

    // Temperature field: hottest at the core near the logs, cooling upward.
    float core = pow(1.0 - clamp(lat, 0.0, 1.0), 2.2);
    float temp = clamp(heat * (0.72 + 0.85 * core) * uIntensity, 0.0, 1.0);
    temp = pow(temp, 0.85);

    vec3 col = firePalette(temp, clamp(uWarmth, 0.0, 1.0)) * heat;

    // Soft glow around the flame so the tip does not end on a hard edge.
    // Driven by a broad noise average, not the flame mask, so it reads as
    // scattered light in the air rather than a second copy of the flame.
    float glowNoise = glowField(p * 0.55, t * 0.6);
    float halo = pow(clamp(1.0 - lat * 0.75, 0.0, 1.0), 2.5)
               * smoothstep(0.15, 0.75, glowNoise)
               * (1.0 - hFall * 0.55);
    col += firePalette(0.55, uWarmth) * halo * uIntensity * 0.5;

    // --- embers ---
    // Embers drift on the noise timeline but are gated by SCREEN height, same
    // rule as the envelope: no time dependence in the spatial mask.
    //
    // The gate was inverted. smoothstep(1.25, 0.15, sp.y*1.9) returns 1 only
    // BELOW sp.y ~= 0.08, i.e. inside the brightest 8% of the flame, so the
    // sparks were being drawn where they could not be seen. Measured effect
    // was +0.04 mean brightness. Embers must live in the air ABOVE the flame:
    // they fade in just off the hearth and die out well before the top.
    vec2 ep = sp * (1.9 * uScale);
    ep.y -= t * 0.42;
    float emGlow = smoothstep(0.015, 0.10, sp.y)
                 * (1.0 - smoothstep(0.30, 0.72, sp.y));
    float em = emberField(ep, t) * emGlow * clamp(uEmbers, 0.0, 1.0);
    col += vec3(1.0, 0.55, 0.18) * em * 1.15;

    // --- room: dark, with warm light cast from the hearth ---
    // NB: `cast` is a reserved word in GLSL ES — hence castLight. dist() uses the
    // screen-space coordinate so the room light does not scroll with the noise.
    float dist = length(vec2(sp.x, max(sp.y + 0.12, 0.0)));
    float castLight = exp(-dist * 1.55) * (0.55 + 0.45 * flick);
    vec3 bg = vec3(0.016, 0.013, 0.012);
    bg += vec3(1.0, 0.42, 0.12) * castLight * 0.16 * clamp(uRoom, 0.0, 1.0);

    col += bg;

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}