// ============================================================================
// Hearth - pixel-art fireplace, the way Terraria does light.
//
// Art direction, after looking at what the previous version actually rendered:
//
//   * A fireplace is an OPENING in a wall, not a flame pasted on wallpaper.
//     The old version filled the entire screen with a brick grid, which read as
//     a repeating texture: ~20x12 identical bricks, no subject, no dark, no
//     depth. Now the frame is a dark room with a firebox cut into it, and the
//     fire burns INSIDE that hole. The dark void around the flame is what makes
//     the flame read as a fire.
//   * Light must fall off, or there is no firelight - only "everything is
//     orange". The old version kept 94.7% of pixels lit. Now a hard vignette
//     and a steep falloff put the corners in shadow.
//   * Colour comes from a PALETTE RAMP indexed by a quantised shade, never from
//     per-channel rounding. Rounding R, G and B independently is what produced
//     the purple/green speckles all over the old wall: each channel crossed a
//     rounding boundary at a different pixel. One quantised scalar -> one ramp
//     lookup -> coherent hue, always.
//   * The flame is a tongue with a small hot core, not a blown-out white
//     sliver: the old temp curve saturated to 1.0 across the whole width, so
//     the core came out pure white and the flame lost its orange body.
//   * Masonry is chunky and few (roughly 4 blocks across the frame), so it
//     reads as a wall instead of a fine pattern.
//
// The four cheap tricks still doing the pixel-art work:
//
//   1. Quantised time. floor(iTime * uFps) / uFps. The single biggest
//      contributor to "pixel art" versus "smooth noise that got pixelated".
//   2. Quantised shade with ordered dithering on the boundary, so light
//      staircases across the stone instead of gradienting.
//   3. A real scene: masonry, a lintel, an opening, logs.
//   4. A fixed warm ramp. Colours are chosen, not interpolated into mush.
//
// Everything is procedural: no textures, no spritesheets, zero art assets.
//
// Host contract: host PREPENDS iResolution/iTime/iTimeDelta/iFrame/iMouse and
// APPENDS main() calling mainImage(). mainImage is forward-declared because
// GLSL has no two-pass compilation.
//
// Written to compile as GLSL ES 1.00 (WebGL) as well as desktop GL 3.30:
// arithmetic-only Bayer, no array constructors, no bit-wise operators.
//
// Tuning uniforms:
//   uIntensity  0..2    flame brightness and how far its light reaches
//   uSpeed      0..2    animation speed multiplier
//   uWarmth     0..1    colour temperature: 0 = coal red, 1 = white hot
//   uScale      0.5..2  firebox size
//   uDetail     0..1    turbulence / domain-warp strength
//   uEmbers     0..1    rising spark density
//   uRoom       0..1    ambient bounce floor (keeps corners off pure black)
//   uPixel      1..16   pixel size in framebuffer pixels (1 = no upscale)
//   uFps        4..30   animation frame rate for the quantised clock
//   uDither     0..1    dithering strength between palette steps
//   uSteps      2..12   number of palette levels (lower = chunkier)
//   uWall       0..1    masonry contrast
// ============================================================================

void mainImage(out vec4 fragColor, in vec2 fragCoord);

uniform float uIntensity;
uniform float uSpeed;
uniform float uWarmth;
uniform float uScale;
uniform float uDetail;
uniform float uEmbers;
uniform float uRoom;
uniform float uPixel;
uniform float uFps;
uniform float uDither;
uniform float uSteps;
uniform float uWall;

// --- hash / noise / fbm ------------------------------------------------------

float hash1(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

vec2 hash2(vec2 p) {
    p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));
    return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);
}

float gnoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(dot(hash2(i + vec2(0.0, 0.0)), f - vec2(0.0, 0.0)),
                   dot(hash2(i + vec2(1.0, 0.0)), f - vec2(1.0, 0.0)), u.x),
               mix(dot(hash2(i + vec2(0.0, 1.0)), f - vec2(0.0, 1.0)),
                   dot(hash2(i + vec2(1.0, 1.0)), f - vec2(1.0, 1.0)), u.x), u.y);
}

const mat2 M2 = mat2(1.6, 1.2, -1.2, 1.6);

float fbm(vec2 p) {
    float f = 0.0;
    float a = 0.5;
    for (int i = 0; i < 4; i++) {
        f += a * gnoise(p);
        p = M2 * p;
        a *= 0.5;
    }
    return f;
}

// Domain-warped fbm. The warp is what turns smooth blobs into licking tongues.
float flameNoise(vec2 p, float t, float detail) {
    float n = fbm(p);
    vec2 q = vec2(fbm(p + 0.15 * t), fbm(p + vec2(5.2, 1.3) - 0.11 * t));
    vec2 r = vec2(fbm(p + 1.9 * q + vec2(1.7, 9.2) + 0.09 * t),
                  fbm(p + 1.9 * q + vec2(8.3, 2.8) - 0.13 * t));
    return clamp(mix(n, fbm(p + (1.4 + 2.6 * detail) * r), detail) * 0.9 + 0.5,
                 0.0, 1.0);
}

// --- ordered dithering -------------------------------------------------------

// 4x4 Bayer from bits, using arithmetic only.
//
// A lookup table (float m[16] = float[16](...)) or any bit-wise operator (>>,
// &) compiles on the desktop GL 3.30 host but is rejected by WebGL, which is
// GLSL ES 1.00. That broke tools/preview.html while every GPU test stayed
// green. Verified numerically: all 16 levels 0..15 are produced.
float bayer4(vec2 c) {
    vec2 i = mod(c, 4.0);
    float v = 0.0;
    for (int bit = 0; bit < 2; ++bit) {
        float xb = mod(floor(i.x / exp2(float(bit))), 2.0);
        float yb = mod(floor(i.y / exp2(float(bit))), 2.0);
        v += xb * exp2(3.0 - 2.0 * float(bit))
           + yb * exp2(2.0 - 2.0 * float(bit));
    }
    return v / 16.0 - 0.5;
}

// Snap a shade to a step count, dithering across the boundary.
//
// The dither fades out in deep shadow. Dithering exists to break up a
// gradient; where only the two lowest levels are in play there is no gradient
// to break, and the result is 50% pure-black noise that reads as a fault.
float quantSteps(float x, float steps, float ditherAmt, vec2 cell) {
    float t = clamp(x, 0.0, 1.0);
    float strength = smoothstep(0.04, 0.26, t);
    float d = bayer4(cell) * ditherAmt * strength / max(steps, 1.0);
    return floor(t * steps + d) / (steps - 1.0);
}

// --- palette -----------------------------------------------------------------

// Stone ramp, cold in shadow to warm near the fire. Chosen colours in a fixed
// order, so the image can only ever be a palette - never a gradient.
vec3 stoneRamp(float s) {
    s = clamp(s, 0.0, 1.0);
    vec3 c = vec3(0.055, 0.050, 0.080);                 // deep cold shadow
    c = mix(c, vec3(0.105, 0.075, 0.085), smoothstep(0.00, 0.22, s));
    c = mix(c, vec3(0.235, 0.130, 0.110), smoothstep(0.22, 0.44, s));
    c = mix(c, vec3(0.470, 0.235, 0.125), smoothstep(0.44, 0.66, s));
    c = mix(c, vec3(0.760, 0.420, 0.170), smoothstep(0.66, 0.84, s));
    c = mix(c, vec3(0.960, 0.700, 0.330), smoothstep(0.84, 1.00, s));
    return c;
}

// Fire ramp: coal red -> orange -> yellow -> small white core. uWarmth slides
// the whole ramp between a cold coal fire and a hot gas flame.
vec3 fireRamp(float k, float warmth) {
    k = clamp(k, 0.0, 1.0);
    vec3 c = vec3(0.320, 0.040, 0.015);
    c = mix(c, vec3(0.780, 0.190, 0.030), smoothstep(0.00, 0.30, k));
    c = mix(c, vec3(1.000, 0.520, 0.100), smoothstep(0.30, 0.58, k));
    c = mix(c, vec3(1.000, 0.820, 0.420), smoothstep(0.58, 0.82, k));
    c = mix(c, vec3(1.000, 0.980, 0.900), smoothstep(0.82, 1.00, k));
    // Warmth desaturates and lifts the deep end, so uWarmth=1 is less red.
    return mix(c, mix(c, vec3(dot(c, vec3(0.33))) + c * 0.35, 0.45), warmth);
}

// --- masonry -----------------------------------------------------------------

// Returns .x = tone multiplier, .y = mortar mask.
//
// Chunky on purpose: roughly 4 blocks across the frame and 4 rows. The previous
// version used 13x17 blocks, which at 6px pixels made a wall of ~20x12 tiny
// identical bricks - visually a wallpaper pattern, not a wall.
vec2 masonry(vec2 sp, float t) {
    vec2 g = vec2(sp.x * 2.40 + 0.50, sp.y * 4.20);
    float row = floor(g.y);
    g.x += mod(row, 2.0) * 0.5;                        // half-brick offset
    vec2 cellId = vec2(floor(g.x), row);
    vec2 f = fract(g);

    float h = hash1(cellId * 1.3 + 5.7);
    float tone = 0.84 + 0.16 * h;
    if (h > 0.94) { tone *= 0.70; }                    // a few stained blocks

    // Mortar: thin, and only visible because the light is falling off.
    vec2 e = min(f, 1.0 - f);
    float mortar = 1.0 - smoothstep(0.015, 0.045, min(e.x, e.y));

    // Face texture at pixel scale, so big blocks are not dead flat.
    tone *= 0.95 + 0.10 * hash1(floor(sp * 170.0));

    return vec2(tone, mortar);
}

// --- fire --------------------------------------------------------------------

// Returns .x = flame mask, .y = temperature.
//
// A tongue, not a sliver: solid and wide at the base, carved into separate
// licks near the tip by the noise threshold, with a hot core confined to the
// lower centre. The previous temp curve saturated to 1.0 across the full width,
// which rendered the flame pure white and lost the orange body entirely.
vec2 flameField(vec2 sp, float base, float top, float halfW, float t) {
    float h = (sp.y - base) / max(top - base, 1e-3);
    if (h < 0.0 || h > 1.0) {
        return vec2(0.0, 0.0);
    }

    // Rising turbulence: sampled in space, so nothing depends on screen scroll.
    vec2 q = vec2(sp.x * 7.0, sp.y * 3.2 - t * 1.55);
    float n = flameNoise(q, t * 0.75, uDetail);

    // Envelope: wide at the hearth, pinched at the neck, narrow at the tip.
    float w = halfW * mix(1.0, 0.30, pow(h, 0.80));
    // Taper the tongue toward the tip.
    w *= 1.0 - 0.30 * smoothstep(0.35, 1.0, h);
    // Slow sway, only meaningful up high.
    float sway = 0.055 * h * h * sin(t * 1.25 + h * 2.4) * halfW / 0.17;

    float lat = abs(sp.x - sway) / max(w, 1e-4);

    // Solid at the base, licked apart near the tip. The threshold rises with
    // height but is pulled back down in the first third, because carving the
    // base as hard as the tip punched black holes through the middle of the
    // flame wherever the noise dipped.
    //
    // The top was over-carved: 0.88 meant the upper third lost most of its
    // coverage and read as a gap in the fire rather than as separate licks.
    // 0.62 keeps it broken up without dissolving it.
    float carve = mix(0.10, 0.62, h);
    carve = mix(carve, 0.04, 1.0 - smoothstep(0.0, 0.34, h));

    float v = (1.0 - lat) * (1.0 - 0.70 * h) + (n - carve) * 0.95;
    float heat = smoothstep(0.0, 0.11, v);

    // Fade the last few percent of the tip so licks taper instead of stopping.
    heat *= 1.0 - smoothstep(0.72, 1.0, h);

    float core = heat
               * (1.0 - smoothstep(0.0, 0.62, lat))
               * (1.0 - smoothstep(0.05, 0.55, h));
    float temp = clamp(heat * 0.52 + core * 0.85, 0.0, 1.0);

    return vec2(heat, temp);
}

// --- sparks ------------------------------------------------------------------

// A few discrete rising points, not a field of streaks. The previous version
// scattered long diagonal smears across the whole lower screen, which read as
// rendering artefacts.
float sparks(vec2 p, float t) {
    vec2 g = vec2(p.x * 8.0, p.y * 5.0 - t * 0.85);
    vec2 gi = floor(g);
    vec2 gf = fract(g);
    float h = hash1(gi);
    float on = step(0.88, h);
    vec2 pos = vec2(0.15 + 0.70 * hash1(gi + 3.1),
                    0.20 + 0.60 * fract(h * 7.31));
    float d = length((gf - pos) * vec2(1.0, 1.35));
    float core = smoothstep(0.15, 0.0, d);
    float twinkle = 0.30 + 0.70 * fract(h * 3.77 + t * 1.35);
    return on * core * twinkle;
}

// --- main --------------------------------------------------------------------

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    float scale = max(uPixel, 1.0);

    // Snap to the pixel grid FIRST, so every lookup below shares one coordinate
    // per pixel and light edges, mortar and dither stay on one grid.
    vec2 cell = floor(fragCoord / scale);
    vec2 pix = (cell + 0.5) * scale;

    vec2 res = iResolution.xy;
    float aspect = res.x / max(res.y, 1.0);
    float intensity = clamp(uIntensity, 0.0, 2.0);
    float room = clamp(uRoom, 0.0, 1.0);

    // Quantised clock: animation advances in visible steps, not smoothly.
    float t = floor(iTime * max(uFps, 1.0)) / max(uFps, 1.0);
    t *= max(uSpeed, 0.0);

    vec2 uv = pix / res;
    float aspectFix = clamp(aspect / 1.7777, 0.72, 1.0);
    vec2 sp = vec2((uv.x - 0.5) * aspect * aspectFix, uv.y);

    // --- the firebox, cut into the wall -------------------------------------
    // Sized in sp units (sp.x spans about -0.89..0.89 at 16:9), not fractions
    // of the screen, so it holds its proportions across aspect ratios.
    float sz = clamp(uScale, 0.5, 2.0);
    float openHalf = 0.195 * sz;
    float openBot  = 0.135;
    float openTop  = 0.520 * sz;

    float inOpenX = 1.0 - smoothstep(openHalf - 0.006, openHalf, abs(sp.x));
    float inOpenY = step(openBot, sp.y) * (1.0 - step(openTop, sp.y));
    float inOpening = inOpenX * inOpenY;

    // --- light --------------------------------------------------------------
    // From the mouth of the firebox, not from the flame: the opening is the
    // aperture, and it is what actually appears to glow.
    vec2 src = vec2(0.0, mix(openBot, openTop, 0.42));
    float dist = length((sp - src) * vec2(1.0, 0.82));

    float reach = 0.40 * intensity;
    float falloff = 1.0 / (1.0 + pow(dist / max(reach, 0.05), 1.85));

    // Hard vignette. Without it the whole frame stays lit and the fire reads as
    // an orange wallpaper rather than as a light source.
    float vig = length((uv - 0.5) * vec2(aspect, 1.0)) / 0.62;
    float shade = falloff * (1.0 - 0.72 * smoothstep(0.55, 1.35, vig));

    // Flicker modulates the room, not just the flame.
    float flicker = 0.82 + 0.30 * (0.5 + 0.5 * fbm(vec2(t * 0.55, 11.0)));
    shade *= flicker;

    // --- masonry ------------------------------------------------------------
    vec2 w = masonry(sp, t);
    // Tone and mortar are folded in BEFORE quantisation, so texture rides the
    // palette instead of multiplying it into off-palette colours.
    shade *= mix(1.0, w.x, clamp(uWall, 0.0, 1.0));
    shade *= mix(1.0, 0.58, w.y * clamp(uWall, 0.0, 1.0));

    // Lintel across the top of the opening, catching the most light.
    float lintel = step(openTop - 0.055, sp.y) * (1.0 - step(openTop, sp.y))
                 * (1.0 - smoothstep(openHalf + 0.075, openHalf + 0.10, abs(sp.x)));
    shade *= mix(1.0, 1.14, lintel);

    // Ambient bounce: a floor, so unlit corners land on the lowest palette step
    // instead of pure black.
    shade += 0.055 * room;

    // --- flame --------------------------------------------------------------
    // The logs sit BELOW the flame's visible base, not across it. They used to
    // be at y=0.187 and 0.233 while the flame ran from 0.187 upward, so the
    // bars covered exactly the hottest part of the fire and the flame appeared
    // to hover above them rather than burn out of them. The flame now starts a
    // little above the logs, so the base glows and the logs sit under it.
    float logY = openBot + 0.026 * sz;
    vec2 f = flameField(sp, logY + 0.012 * sz, openTop - 0.028 * sz,
                        openHalf * 0.82, t);

    // Inside the opening the glow is the firebox itself.
    //
    // The coal bed matters: with `shade = 0.10` where there is no flame, the
    // quantiser mapped that to the lowest palette step, i.e. pure black, so
    // every dip in the noise became a black hole punched through the flame.
    // A real firebox is never empty black: there are always embers under the
    // fire giving a low red floor.
    float bed = 1.0 - smoothstep(0.0, 0.34, sp.y - openBot);
    float coal = 0.16 + 0.42 * bed;
    // Slow breathing so the bed is not a dead constant.
    coal *= 0.85 + 0.30 * fbm(vec2(sp.x * 9.0, sp.y * 6.0 - t * 0.55));
    shade = mix(shade, coal + 0.90 * f.y * f.y * flicker, inOpening);

    float steps = max(uSteps, 2.0);
    float sq = quantSteps(clamp(shade, 0.0, 1.0), steps, uDither, cell);
    vec3 col = stoneRamp(sq);

    // --- fire body ----------------------------------------------------------
    // The flame mask is quantised too, otherwise its edge stays smooth and
    // fights the pixel grid everywhere else.
    float mq = quantSteps(f.x, steps * 1.4, uDither * 0.55, cell);
    float tq = quantSteps(f.y, steps * 1.4, uDither * 0.55, cell);
    col = mix(col, fireRamp(tq, clamp(uWarmth, 0.0, 1.0)), mq);

    // --- logs ---------------------------------------------------------------
    // Two bars lying in a stack at the bottom of the firebox, drawn OVER the
    // flame so the fire burns out from between them. Both sit below the
    // flame's hot base; the second is offset sideways so the stack reads as
    // two logs rather than one thick bar.
    float d1 = 1.0 - smoothstep(0.0, 0.020,
        max(abs(sp.x - 0.012) - openHalf * 0.82, abs(sp.y - logY) - 0.016));
    float d2 = 1.0 - smoothstep(0.0, 0.020,
        max(abs(sp.x + 0.014) - openHalf * 0.62, abs(sp.y - logY - 0.024) - 0.014));
    float log = max(d1, d2) * inOpening;

    // Charred wood, with a lit rim where the fire is closest.
    vec3 wood = vec3(0.115, 0.070, 0.052);
    wood = mix(wood, vec3(0.520, 0.235, 0.090), f.y * 0.55);
    wood = floor(wood * steps + 0.5) / steps;
    col = mix(col, wood, log);

    // --- sparks -------------------------------------------------------------
    // Confined to a narrow column above the firebox.
    float emWin = step(openTop, sp.y)
                * (1.0 - smoothstep(openTop + 0.30, openTop + 0.46, sp.y))
                * (1.0 - smoothstep(0.04, 0.22, abs(sp.x)));
    float em = sparks(sp * 1.35, t) * emWin * clamp(uEmbers, 0.0, 1.0);
    em = floor(em * steps + 0.5) / steps;
    col = mix(col, vec3(1.00, 0.62, 0.22), em * 0.9);

    fragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}