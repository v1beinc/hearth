// Hearth / The quiet cabin. Original procedural pixel art, no external assets.
// A 320 x 180 room, bottom-left origin; hosts supply iResolution, iTime, main().
// Compatible with desktop GL and GLSL ES 1.00 (WebGL).
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
uniform float uSteam;
uniform float uWeather;
uniform float uShowcase;
uniform float uLife;
uniform float uDayMode;

// The host's Moscow wall clock keeps daylight independent of animation pause.
// x = daylight, y = warm twilight; mode 1 preserves the original quiet night.
vec2 daylight() {
    if (uDayMode > 3.5) return vec2(0.32, 0.95);
    if (uDayMode > 2.5) return vec2(1.0, 0.0);
    if (uDayMode > 1.5) return vec2(0.40, 0.70);
    if (uDayMode > 0.5) return vec2(0.0);
    float hour = mod(iDate.w, 86400.0) / 3600.0;
    float rise = smoothstep(6.5, 9.0, hour);
    float fall = smoothstep(17.0, 20.0, hour);
    return vec2(rise * (1.0 - fall),
                4.0 * (rise * (1.0 - rise) + fall * (1.0 - fall)));
}

float hash1(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float noise(vec2 p) {
    vec2 a = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash1(a), hash1(a + vec2(1.0, 0.0)), f.x),
               mix(hash1(a + vec2(0.0, 1.0)), hash1(a + 1.0), f.x), f.y);
}
float bayer4(vec2 p) {
    vec2 i = mod(p, 4.0);
    float v = 0.0;
    for (int bit = 0; bit < 2; ++bit) {
        float xb = mod(floor(i.x / exp2(float(bit))), 2.0);
        float yb = mod(floor(i.y / exp2(float(bit))), 2.0);
        v += xb * exp2(3.0 - 2.0 * float(bit))
           + yb * exp2(2.0 - 2.0 * float(bit));
    }
    return v / 16.0 - 0.5;
}
float box(vec2 p, vec4 r) {
    return step(r.x, p.x) * step(r.y, p.y)
         * (1.0 - step(r.z, p.x)) * (1.0 - step(r.w, p.y));
}
void rect(inout vec3 c, vec2 p, vec4 r, vec3 ink) {
    c = mix(c, ink, box(p, r));
}
float disc(vec2 p, vec2 center, float r) {
    return 1.0 - step(r, length(p - center));
}
float stroke(vec2 p, vec2 a, vec2 b, float width) {
    vec2 v = b - a;
    float along = clamp(dot(p - a, v) / max(dot(v, v), 0.001), 0.0, 1.0);
    return 1.0 - step(width, length(p - a - v * along));
}
void clockHands(inout vec3 c, vec2 p, float seconds) {
    vec2 center = vec2(161.5, 125.0);
    // 12 o'clock points up in scene coordinates. The hour hand advances with
    // the minutes; seconds are stepped, like a little mechanical mantel clock.
    float hourAngle = mod(seconds, 43200.0) / 43200.0 * 6.2831853;
    float minuteAngle = mod(seconds, 3600.0) / 3600.0 * 6.2831853;
    float secondAngle = mod(floor(seconds), 60.0) / 60.0 * 6.2831853;
    vec2 hour = vec2(sin(hourAngle), cos(hourAngle));
    vec2 minute = vec2(sin(minuteAngle), cos(minuteAngle));
    vec2 second = vec2(sin(secondAngle), cos(secondAngle));
    for (int i = 0; i < 12; ++i) {
        float angle = float(i) * 0.5235988;
        vec2 direction = vec2(sin(angle), cos(angle));
        c = mix(c, vec3(0.35, 0.265, 0.19),
                stroke(p, center + direction * 6.0, center + direction * 7.0, 0.48));
    }
    c = mix(c, vec3(0.20, 0.14, 0.12), stroke(p, center, center + hour * 3.6, 0.8));
    c = mix(c, vec3(0.20, 0.14, 0.12), stroke(p, center, center + minute * 5.7, 0.6));
    c = mix(c, vec3(0.60, 0.235, 0.14), stroke(p, center - second, center + second * 5.0, 0.34));
    c = mix(c, vec3(0.24, 0.16, 0.115), disc(p, center, 1.0));
}
float coffeeSteam(vec2 p, float t) {
    vec2 q = p - vec2(79.5, 56.0);
    if (q.y <= 0.0 || q.y >= 16.0 || abs(q.x) > 9.0) return 0.0;
    float steam = 0.0;
    for (int i = 0; i < 2; ++i) {
        float k = float(i);
        float sway = sin(q.y * 0.48 - t * 1.8 + k * 2.6) * (0.65 + q.y * 0.075);
        float x = -1.5 + k * 3.0 + sway;
        float width = 0.55 + q.y * 0.035;
        float thread = 1.0 - smoothstep(width * 0.5, width + 0.4, abs(q.x - x));
        float rise = 0.55 + 0.45 * sin(q.y * 0.52 - t * 2.3 + k * 2.2);
        float fade = smoothstep(0.0, 2.0, q.y) * (1.0 - smoothstep(7.0, 16.0, q.y));
        steam = max(steam, thread * rise * fade);
    }
    // Three restrained opacity levels retain the pixel-art feel.
    return floor(steam * 3.0 + 0.5) / 3.0 * 0.42 * clamp(uSteam, 0.0, 1.0);
}
// Restrained grain, continuous streaks, and sparse joints.
vec3 wood(vec2 p, float vertical) {
    p = mix(p, p.yx, vertical);
    float row = floor(p.y / 8.0);
    float seam = step(7.0, mod(p.y, 8.0));
    vec3 c = mix(vec3(0.27, 0.17, 0.14), vec3(0.37, 0.235, 0.17), hash1(vec2(row, 4.0)));
    c *= 0.89 + 0.15 * step(0.68, noise(vec2(p.x * 0.19, floor(p.y) * 2.0)));
    c = mix(c, vec3(0.16, 0.11, 0.11), seam);
    c += vec3(0.033, 0.022, 0.012) * (1.0 - step(1.0, mod(p.y, 8.0)));
    float joint = step(47.0, mod(p.x + mod(row, 3.0) * 17.0, 48.0));
    return mix(c, c * 0.67, joint * 0.5);
}
vec3 stone(vec2 p) {
    float row = floor(p.y / 10.0);
    vec2 q = vec2(p.x + mod(row, 2.0) * 11.0, p.y);
    vec2 id = floor(q / vec2(22.0, 10.0)), f = mod(q, vec2(22.0, 10.0));
    float tone = hash1(id);
    vec3 c = mix(vec3(0.30, 0.31, 0.34), vec3(0.42, 0.415, 0.40), tone);
    c *= 1.0 - 0.46 * min(step(20.0, f.x) + step(8.0, f.y), 1.0);
    c += vec3(0.075) * box(f, vec4(1.0, 6.0, 19.0, 7.0));
    c *= 1.0 - 0.14 * step(0.91, hash1(floor(p)));
    float crack = box(f, vec4(6.0, 3.0, 7.0, 5.0)) + box(f, vec4(7.0, 2.0, 11.0, 3.0));
    c *= 1.0 - 0.28 * crack * step(0.7, tone);
    return mix(vec3(0.34), c, clamp(uWall, 0.0, 1.0));
}
float pine(vec2 p, float x, float base, float height) {
    float y = (p.y - base) / height;
    float width = height * (0.33 * (1.0 - y) + 0.07 * fract(y * 4.0));
    float leaves = step(0.14, y) * (1.0 - step(1.0, y)) * (1.0 - step(width, abs(p.x - x)));
    return max(leaves, box(p, vec4(x - 1.0, base, x + 1.0, base + height * 0.45)));
}
// Weather, rare visitors and the cat use a separate, deterministic scene clock.
// Showcase speeds up their calendar, without speeding up the fire or coffee.
float worldTime(float t) { return t * mix(1.0, 8.0, step(0.5, uShowcase)); }
vec3 weatherState(float t) {
    float slot = floor(t / 180.0), age = mod(t, 180.0);
    float next = 1.0 + floor(hash1(vec2(slot, 87.0)) * 4.0);
    float prev = 1.0 + floor(hash1(vec2(slot - 1.0, 87.0)) * 4.0);
    if (slot < 1.0) { next = 2.0; prev = 2.0; }
    if (uWeather > 0.5) { next = floor(uWeather + 0.5); prev = next; }
    // x = snowfall, y = clouds, z = wind. Soft transitions prevent weather pops.
    vec3 a = vec3(0.0, 0.05, 0.15), b = a;
    if (prev > 1.5) a = vec3(0.35, 0.25, 0.35);
    if (prev > 2.5) a = vec3(1.00, 0.90, 1.00);
    if (prev > 3.5) a = vec3(0.04, 0.88, 0.20);
    if (next > 1.5) b = vec3(0.35, 0.25, 0.35);
    if (next > 2.5) b = vec3(1.00, 0.90, 1.00);
    if (next > 3.5) b = vec3(0.04, 0.88, 0.20);
    return mix(a, b, smoothstep(0.0, 35.0, age));
}
float fullMoon(float t) {
    // Showcase keeps a full moon, so the rare sleigh can be inspected promptly.
    return max(1.0 - step(0.5, mod(floor(t / 600.0), 8.0)), step(0.5, uShowcase));
}
void visitor(inout vec3 c, vec2 p, float t) {
    if (uLife < 0.5) return;
    float slot = floor(t / 180.0);
    float start = 65.0 + hash1(vec2(slot, 71.0)) * 25.0;
    float age = mod(t, 180.0) - start;
    float chance = hash1(vec2(slot, 26.0));
    if (age < 0.0 || age > 22.0) return;
    if (slot > 0.5 && chance < 0.40 && uShowcase < 0.5) return;
    float approach = smoothstep(0.0, 5.0, age) * (1.0 - smoothstep(16.0, 22.0, age));
    float x = mix(103.0, 75.0, approach);
    float kind = mod(slot, 3.0);
    float walking = 1.0 - step(5.0, age) + step(16.0, age);
    vec2 q = floor(p - vec2(x, 87.0 + sin(t * 2.0) * walking * 0.6));
    vec3 green = vec3(0.21, 0.37, 0.235), dark = vec3(0.055, 0.10, 0.10);
    if (kind < 0.5) {
        // Creeper: square mottled head, familiar black face, four short feet.
        rect(c, q, vec4(-4.0, 4.0, 4.0, 15.0), green * 0.8);
        rect(c, q, vec4(-6.0, 14.0, 6.0, 25.0), green);
        float fleck = step(0.68, hash1(floor(q / 2.0)));
        c = mix(c, green * 1.22, fleck * box(q, vec4(-6.0, 14.0, 6.0, 25.0)) * 0.7);
        rect(c, q, vec4(-4.0, 20.0, -1.0, 22.0), dark);
        rect(c, q, vec4(2.0, 20.0, 5.0, 22.0), dark);
        rect(c, q, vec4(0.0, 17.0, 2.0, 20.0), dark);
        rect(c, q, vec4(-2.0, 15.0, 4.0, 18.0), dark);
        rect(c, q, vec4(-5.0, 0.0, -1.0, 5.0), green * 0.65);
        rect(c, q, vec4(1.0, 0.0, 5.0, 5.0), green * 0.65);
    } else if (kind < 1.5) {
        // Skeleton: ivory skull, eye sockets, ribs and thin limbs.
        vec3 bone = vec3(0.53, 0.61, 0.60);
        rect(c, q, vec4(-5.0, 16.0, 5.0, 25.0), bone);
        rect(c, q, vec4(-3.0, 13.0, 3.0, 17.0), bone * 0.8);
        rect(c, q, vec4(-4.0, 20.0, -1.0, 23.0), dark);
        rect(c, q, vec4(1.0, 20.0, 4.0, 23.0), dark);
        rect(c, q, vec4(-2.0, 17.0, 2.0, 18.0), dark);
        rect(c, q, vec4(-1.0, 5.0, 1.0, 14.0), bone * 0.8);
        for (int i = 0; i < 3; ++i) {
            float y = 7.0 + float(i) * 3.0;
            rect(c, q, vec4(-4.0, y, 4.0, y + 1.0), bone * 0.8);
        }
        rect(c, q, vec4(-7.0, 6.0, -5.0, 14.0), bone * 0.65);
        rect(c, q, vec4(5.0, 6.0, 7.0, 14.0), bone * 0.65);
        float stepLeg = floor(sin(t * 3.0) * walking * 1.5);
        rect(c, q, vec4(-3.0 + stepLeg, 0.0, -1.0 + stepLeg, 6.0), bone * 0.6);
        rect(c, q, vec4(1.0 - stepLeg, 0.0, 3.0 - stepLeg, 6.0), bone * 0.6);
    } else {
        // Zombie: muted teal shirt and blue trousers, reaching arms.
        rect(c, q, vec4(-5.0, 5.0, 5.0, 16.0), vec3(0.11, 0.28, 0.30));
        rect(c, q, vec4(-5.0, 16.0, 5.0, 25.0), green);
        rect(c, q, vec4(-3.0, 21.0, -1.0, 23.0), dark);
        rect(c, q, vec4(1.0, 21.0, 3.0, 23.0), dark);
        rect(c, q, vec4(-2.0, 17.0, 3.0, 18.0), green * 0.5);
        rect(c, q, vec4(-8.0, 10.0, -5.0, 15.0), green * 0.8);
        rect(c, q, vec4(5.0, 10.0, 8.0, 15.0), green * 0.8);
        rect(c, q, vec4(-4.0, 0.0, -1.0, 6.0), vec3(0.15, 0.17, 0.27));
        rect(c, q, vec4(1.0, 0.0, 4.0, 6.0), vec3(0.15, 0.17, 0.27));
    }
}
void sleigh(inout vec3 c, vec2 p, float t, float clouds) {
    if (uLife < 0.5) return;
    float cycle = mix(360.0, 120.0, step(0.5, uShowcase));
    float slot = floor(t / cycle), age = mod(t, cycle) - mix(240.0, 30.0, step(0.5, uShowcase));
    if (age < 0.0 || age > 18.0 || fullMoon(t) < 0.5 || clouds > 0.55) return;
    if (uShowcase < 0.5 && hash1(vec2(slot, 98.0)) < 0.82) return;
    vec2 q = floor(p - vec2(mix(8.0, 103.0, age / 18.0), 129.0 + sin(age * 0.4)));
    // Tiny sleigh, red coat and white beard, two reindeer ahead of it.
    rect(c, q, vec4(-8.0, -3.0, 3.0, 0.0), vec3(0.55, 0.15, 0.15));
    rect(c, q, vec4(-8.0, -5.0, 5.0, -4.0), vec3(0.70, 0.55, 0.32));
    rect(c, q, vec4(4.0, -4.0, 6.0, -2.0), vec3(0.70, 0.55, 0.32));
    rect(c, q, vec4(-6.0, 0.0, -1.0, 5.0), vec3(0.78, 0.20, 0.16));
    rect(c, q, vec4(-3.0, 3.0, 0.0, 5.0), vec3(0.86, 0.77, 0.61));
    rect(c, q, vec4(-3.0, 2.0, 1.0, 3.0), vec3(0.90, 0.88, 0.76));
    rect(c, q, vec4(-5.0, 5.0, -1.0, 6.0), vec3(0.89, 0.85, 0.73));
    rect(c, q, vec4(-5.0, 6.0, -2.0, 8.0), vec3(0.72, 0.18, 0.15));
    for (int i = 0; i < 2; ++i) {
        float x = 11.0 + float(i) * 13.0;
        vec3 fur = vec3(0.42, 0.31, 0.24);
        rect(c, q, vec4(x - 3.0, 0.0, x + 3.0, 3.0), fur);
        rect(c, q, vec4(x + 2.0, 2.0, x + 5.0, 6.0), fur);
        rect(c, q, vec4(x + 3.0, 6.0, x + 4.0, 9.0), vec3(0.64, 0.55, 0.40));
        rect(c, q, vec4(x + 1.0, 8.0, x + 6.0, 9.0), vec3(0.64, 0.55, 0.40));
        float leg = floor(sin(age * 2.2 + float(i)));
        rect(c, q, vec4(x - 2.0 + leg, -3.0, x - 1.0 + leg, 1.0), fur);
        rect(c, q, vec4(x + 1.0 - leg, -3.0, x + 2.0 - leg, 1.0), fur);
    }
}
vec3 outside(vec2 p, float t) {
    float world = worldTime(t);
    vec3 weather = weatherState(world);
    vec2 light = daylight();
    float night = 1.0 - smoothstep(0.02, 0.35, light.x);
    float height = clamp((p.y - 85.0) / 58.0, 0.0, 1.0);
    vec3 sky = mix(vec3(0.105, 0.19, 0.30), vec3(0.055, 0.09, 0.19), height);
    vec3 daySky = mix(vec3(0.65, 0.76, 0.78), vec3(0.30, 0.51, 0.69), height);
    vec3 c = mix(sky, daySky, light.x);
    c = mix(c, mix(vec3(0.86, 0.43, 0.27), vec3(0.39, 0.29, 0.43), height), light.y * 0.90);
    vec2 stars = floor(p / 3.0);
    float star = step(0.975, hash1(stars)) * box(mod(p, 3.0), vec4(0.0, 0.0, 1.0, 1.0));
    c += vec3(0.30, 0.36, 0.41) * star * (0.7 + 0.3 * sin(t * 0.5 + stars.x)) * night;
    float moon = disc(p, vec2(73.0, 129.0), 7.0) * night;
    c = mix(c, vec3(0.76, 0.83, 0.78), moon);
    c = mix(c, vec3(0.56, 0.67, 0.69), moon * disc(p, vec2(75.0, 127.0), 2.5));
    // A fictional lunar calendar: a full moon once every eight quiet nights.
    if (fullMoon(world) < 0.5) {
        float phase = mod(floor(world / 600.0), 8.0);
        float offset = mix(-4.0, 4.0, step(4.0, phase));
        c = mix(c, vec3(0.065, 0.105, 0.205), moon * disc(p, vec2(73.0 + offset, 129.0), 6.5));
    }
    float sun = disc(p, vec2(73.0, mix(118.0, 132.0, light.x)), 5.0);
    c = mix(c, vec3(1.0, 0.84, 0.56), sun * smoothstep(0.08, 0.30, light.x));
    float clouds = noise(vec2(p.x * 0.065 + world * 0.004, p.y * 0.13)) * 0.75
                 + noise(vec2(p.x * 0.12 - world * 0.002, p.y * 0.06)) * 0.25;
    float cloudMask = smoothstep(0.40 - weather.y * 0.3, 0.74 - weather.y * 0.4, clouds) * weather.y;
    c = mix(c, mix(vec3(0.16, 0.21, 0.285), vec3(0.60, 0.67, 0.70), light.x), cloudMask);
    if (night > 0.7) sleigh(c, p, world, weather.y);
    // An occasional shooting star, only through a mostly clear sky.
    float starAge = mod(world, 97.0) - 41.0;
    if (starAge > 0.0 && starAge < 1.8 && weather.y < 0.55 && night > 0.7) {
        vec2 head = vec2(42.0 + starAge * 23.0, 140.0 - starAge * 6.0);
        c = mix(c, vec3(0.59, 0.72, 0.78), stroke(p, head - vec2(5.0, -1.4), head, 0.45));
    }
    float ridge = 110.0 + 6.0 * sin(p.x * 0.065) + 3.0 * sin(p.x * 0.18);
    c = mix(c, mix(vec3(0.13, 0.235, 0.30), vec3(0.36, 0.48, 0.51), light.x), 1.0 - step(ridge, p.y));
    for (int i = 0; i < 7; ++i) {
        float k = float(i);
        c = mix(c, mix(vec3(0.075, 0.17, 0.205), vec3(0.19, 0.34, 0.30), light.x), pine(p, 26.0 + k * 12.0, 84.0, 23.0 + hash1(vec2(k, 6.0)) * 13.0));
        c = mix(c, mix(vec3(0.04, 0.105, 0.14), vec3(0.12, 0.25, 0.22), light.x), pine(p, 22.0 + k * 15.0, 79.0, 19.0 + hash1(vec2(k, 9.0)) * 10.0));
    }
    visitor(c, p, world);
    // Three depths of snowfall; a blizzard is dense, fast and wind-driven.
    for (int i = 0; i < 3; ++i) {
        float layer = float(i), grid = 9.0 - layer * 1.5;
        float fall = t * (3.0 + layer * 2.0) * (1.0 + weather.z * 2.5);
        vec2 snow = vec2(p.x + fall * weather.z * 0.85 + layer * 17.0, p.y + fall);
        vec2 id = floor(snow / grid), f = mod(snow, grid);
        float on = step(1.0 - weather.x * (0.35 + layer * 0.12), hash1(id + layer * 12.0));
        float flake = box(f, vec4(2.0, 3.0, 3.0, 4.0 + step(0.8, weather.x))) * on;
        c = mix(c, mix(vec3(0.56, 0.68, 0.77), vec3(0.85, 0.88, 0.86), light.x), flake * (0.45 + layer * 0.22));
    }
    return c;
}
void logEnd(inout vec3 c, vec2 p, vec2 center, float radius) {
    vec2 d = p - center;
    float r = length(d);
    c = mix(c, vec3(0.10, 0.075, 0.075), 1.0 - step(radius + 1.0, r));
    c = mix(c, vec3(0.45, 0.275, 0.16), 1.0 - step(radius, r));
    c = mix(c, vec3(0.27, 0.155, 0.11), step(1.1, mod(r, 2.3)) * (1.0 - step(radius - 1.0, r)));
    c = mix(c, vec3(0.61, 0.385, 0.21), box(d, vec4(-2.0, 2.0, 2.0, 3.0)));
}
float tongue(vec2 p, float x, float height, float width, float phase, float t) {
    float h = p.y / height;
    float sway = sin(t * 3.2 + phase + h * 4.5) * (1.0 + h * 3.0)
               + sin(t * 5.7 - h * 6.0 + phase) * h * clamp(uDetail, 0.0, 1.0) * 2.2;
    float w = width * pow(max(1.0 - h, 0.0), 0.72);
    w += sin(h * 15.0 - t * 4.0 + phase) * h * 1.2;
    return min(w - abs(p.x - x - sway), min(p.y, height - p.y));
}
// Glass effects stay inside each pane and preserve the outdoor silhouettes.
vec3 windowGlass(vec2 p, float t, float intensity, float flicker) {
    vec3 c = outside(p, t);
    vec2 lower = vec2(p.x < 60.0 ? 35.0 : 64.0, p.y < 113.0 ? 88.0 : 117.0);
    vec2 upper = vec2(p.x < 60.0 ? 60.0 : 88.0, p.y < 113.0 ? 113.0 : 141.0);
    vec2 edge = min(p - lower, upper - p);
    float rim = 1.0 - smoothstep(0.3, 2.8, min(edge.x, edge.y));
    float frost = rim * (0.18 + noise(p * 0.7) * 0.27);
    // Small branching crystals at the bottom corners, rather than a solid rim.
    for (int i = 0; i < 2; ++i) {
        float side = float(i);
        vec2 root = vec2(mix(lower.x + 1.0, upper.x - 1.0, side), lower.y + 0.5);
        vec2 tip = root + vec2(mix(2.0, -2.0, side), 4.0);
        float crystal = stroke(p, root, tip, 0.55);
        crystal = max(crystal, stroke(p, root + vec2(0.0, 2.0),
                                     root + vec2(mix(3.0, -3.0, side), 2.5), 0.5));
        frost = max(frost, crystal * 0.48);
    }
    c = mix(c, vec3(0.49, 0.65, 0.71), frost);
    float glint = 1.0 - smoothstep(0.3, 1.3, abs(p.x + p.y * 0.52 - 112.0));
    c = mix(c, vec3(0.46, 0.60, 0.65), glint * 0.065);
    // A diffuse, wavering amber reflection in the pane nearest the fireplace.
    float glow = exp(-length((p - vec2(81.0, 101.0)) / vec2(6.0, 10.0)));
    float ripple = 1.0 - smoothstep(0.5, 2.5,
                        abs(p.x - 80.0 - sin(t * 2.1 + p.y * 0.3)));
    ripple *= smoothstep(92.0, 97.0, p.y) * (1.0 - smoothstep(102.0, 110.0, p.y));
    c += vec3(0.95, 0.37, 0.13) * (glow * 0.095 + ripple * 0.035) * intensity * flicker;
    return c;
}
// Soft silhouettes projected away from a gently moving flame centre.
float castShadow(vec2 p, vec2 light, vec2 object, float width, float reach) {
    vec2 direction = normalize(object - light);
    vec2 q = p - object;
    float along = dot(q, direction);
    float across = abs(q.x * direction.y - q.y * direction.x);
    float penumbra = width + max(along, 0.0) * 0.09;
    return (1.0 - smoothstep(penumbra * 0.45, penumbra + 2.0, across))
         * smoothstep(0.0, 4.0, along) * (1.0 - smoothstep(reach * 0.35, reach, along));
}
void sleepyZ(inout vec3 c, vec2 p, vec2 origin, float opacity) {
    vec2 q = p - origin;
    float shape = max(box(q, vec4(0.0, 0.0, 4.0, 1.0)), box(q, vec4(0.0, 5.0, 4.0, 6.0)));
    shape = max(shape, stroke(q, vec2(0.5, 0.5), vec2(3.5, 5.5), 0.5));
    c = mix(c, vec3(0.77, 0.66, 0.44), shape * opacity);
}
void cat(inout vec3 c, vec2 p, float t) {
    if (uLife < 0.5) return;
    float world = worldTime(t), slot = floor(world / 260.0);
    float age = mod(world, 260.0) - 18.0;
    if (age < 0.0 || age > 156.0) return;
    if (slot > 0.5 && hash1(vec2(slot, 48.0)) < 0.28 && uShowcase < 0.5) return;
    float arrive = smoothstep(0.0, 17.0, age);
    float depart = smoothstep(137.0, 156.0, age);
    float x = mix(342.0, 179.0, arrive) + depart * 163.0;
    // Lower the body, fold the paws and curl the tail over several seconds.
    // The same interpolation runs backwards before departure.
    float rest = smoothstep(17.0, 23.0, age) * (1.0 - smoothstep(130.0, 137.0, age));
    float walk = (1.0 - smoothstep(14.0, 17.0, age)) + smoothstep(137.0, 140.0, age);
    float gait = x * 0.42;
    float bob = sin(gait * 2.0) * 0.35 * walk;
    vec2 ground = p - vec2(floor(x) + 2.0, 14.0);
    float contact = 1.0 - smoothstep(0.5, 1.0, length(ground / vec2(23.0, 2.4)));
    c = mix(c, vec3(0.12, 0.08, 0.09), contact * 0.38);
    vec2 q = p - vec2(floor(x), 14.0 + bob);
    if (depart > 0.0) q.x = -q.x;
    if (abs(q.x) > 35.0 || q.y < -2.0 || q.y > 38.0) return;
    vec3 ink = vec3(0.19, 0.115, 0.105);
    vec3 fur = vec3(0.70, 0.425, 0.235), stripe = vec3(0.42, 0.255, 0.165);
    vec3 cream = vec3(0.85, 0.69, 0.46);
    float breath = 0.5 + 0.5 * sin(t * 1.25);
    float belly = mix(5.0, 6.0 + breath * 1.3, rest);
    vec2 bodyCenter = vec2(3.0, mix(9.0, 6.0, rest));
    float body = disc((q - bodyCenter) / vec2(13.5, belly), vec2(0.0), 1.0);
    // Sleeping tail rests on the rug. Walking tail grows from the rump,
    // rises in a soft curve and curls forward at the tip; only the tip sways.
    float sway = sin(t * 2.0) * 1.2 * (1.0 - rest);
    vec2 tailRoot = mix(vec2(13.0, 10.0), vec2(13.0, 4.0), rest);
    vec2 tailJoint = mix(vec2(17.0, 12.0), vec2(19.0, 3.0), rest);
    vec2 bend = mix(vec2(19.0 + sway * 0.4, 17.0), vec2(24.0, 3.0), rest);
    vec2 top = mix(vec2(20.0 + sway, 22.0), vec2(26.0, 4.0), rest);
    vec2 curl = mix(vec2(18.0 + sway, 25.0), vec2(26.0, 6.0), rest);
    vec2 tip = mix(vec2(16.0 + sway, 24.0), vec2(25.0, 7.0), rest);
    float tail = 0.0, tailOutline = 0.0;
    for (int i = 0; i < 5; ++i) {
        vec2 a = tailRoot, b = tailJoint;
        if (i == 1) { a = tailJoint; b = bend; }
        if (i == 2) { a = bend; b = top; }
        if (i == 3) { a = top; b = curl; }
        if (i == 4) { a = curl; b = tip; }
        tail = max(tail, stroke(q, a, b, 1.5));
        tailOutline = max(tailOutline, stroke(q, a, b, 2.25));
    }
    c = mix(c, ink, tailOutline);
    c = mix(c, fur, tail);
    float tailStripes = mix(step(13.0, q.y) * (1.0 - step(1.0, mod(q.y, 6.0))),
                            step(24.0, q.x), rest);
    c = mix(c, stripe, tail * tailStripes);
    // Four paws follow distance travelled; they stop stepping when she stops.
    float stride = sin(gait) * 2.0 * walk;
    for (int i = 0; i < 4; ++i) {
        float rear = step(1.5, float(i));
        float far = mod(float(i), 2.0);
        float swing = mix(stride, -stride, rear) * mix(1.0, -1.0, far);
        float lift = max(0.0, sin(gait + rear * 3.14159 + far * 3.14159)) * walk * 1.5;
        vec2 hip = vec2(mix(-5.0, 10.0, rear) + far * 2.0, mix(7.0, 4.0, rest));
        vec2 paw = mix(vec2(mix(-6.0, 10.0, rear) + swing + far * 2.0, lift),
                       vec2(mix(-13.0, 7.0, rear) + far * 2.0, 1.0), rest);
        c = mix(c, ink, stroke(q, hip, paw + vec2(0.0, 1.0), 2.0));
        c = mix(c, fur * mix(1.0, 0.76, far), stroke(q, hip, paw + vec2(0.0, 1.0), 1.2));
        rect(c, q, vec4(paw - vec2(1.5, 0.0), paw + vec2(2.5, 2.0)), cream * mix(1.0, 0.79, far));
    }
    c = mix(c, ink, disc((q - bodyCenter) / vec2(14.3, belly + 0.8), vec2(0.0), 1.0));
    vec3 coat = fur * (0.83 + 0.17 * smoothstep(bodyCenter.y - 4.0, bodyCenter.y + 3.0, q.y));
    c = mix(c, coat, body);
    c = mix(c, cream, body * (1.0 - step(4.0, q.y)));
    for (int i = 0; i < 3; ++i) {
        float sx = -2.0 + float(i) * 5.0;
        c = mix(c, stripe, body * box(q, vec4(sx, bodyCenter.y + 2.0, sx + 2.0, 16.0)));
    }
    vec2 head = vec2(-12.0, mix(13.0, 7.0, rest));
    vec2 h = q - head;
    c = mix(c, ink, disc(h / vec2(6.8, 5.8), vec2(0.0), 1.0));
    c = mix(c, fur, disc(h / vec2(6.0, 5.0), vec2(0.0), 1.0));
    float ears = box(h, vec4(-5.0, 3.0, -1.0, 8.0)) * step(h.y - 3.0, 2.0 * (h.x + 5.0));
    ears = max(ears, box(h, vec4(1.0, 3.0, 5.0, 8.0)) * step(h.y - 3.0, 2.0 * (5.0 - h.x)));
    c = mix(c, ink, ears);
    c = mix(c, fur, ears * box(h, vec4(-4.0, 3.0, 4.0, 7.0)));
    rect(c, h, vec4(-4.0, 4.0, -3.0, 6.0), vec3(0.57, 0.31, 0.255));
    rect(c, h, vec4(3.0, 4.0, 4.0, 6.0), vec3(0.57, 0.31, 0.255));
    bool eyesClosed = rest > 0.75 || mod(t + 2.0, 11.0) < 0.17;
    if (eyesClosed) {
        rect(c, h, vec4(-4.0, 0.0, -1.0, 1.0), vec3(0.17, 0.12, 0.105));
        rect(c, h, vec4(2.0, 0.0, 5.0, 1.0), vec3(0.17, 0.12, 0.105));
        rect(c, h, vec4(-5.0, -3.0, -1.0, -1.0), cream);
        float snore = mod(t, 6.5) - 3.5;
        if (snore > 0.0 && rest > 0.95) {
            float alpha = (1.0 - smoothstep(1.3, 3.0, snore)) * 0.7;
            sleepyZ(c, q, vec2(-22.0 - floor(snore), 16.0 + floor(snore * 3.0)), alpha);
            sleepyZ(c, q, vec2(-15.0 + floor(snore), 21.0 + floor(snore * 2.0)), alpha * 0.55);
        }
    } else {
        rect(c, h, vec4(-4.0, 0.0, -2.0, 2.0), vec3(0.16, 0.25, 0.17));
        rect(c, h, vec4(-4.0, 1.0, -3.0, 2.0), vec3(0.78, 0.80, 0.49));
    }
    rect(c, h, vec4(-6.0, -1.0, -4.0, 0.0), vec3(0.43, 0.22, 0.195));
}
vec3 fireColor(float k) {
    vec3 c = vec3(0.63, 0.16, 0.09);
    if (k > 0.14) c = vec3(0.88, 0.265, 0.09);
    if (k > 0.30) c = vec3(1.00, 0.455, 0.105);
    if (k > 0.48) c = vec3(1.00, 0.64, 0.19);
    if (k > 0.68) c = vec3(1.00, 0.82, 0.365);
    if (k > 0.89) c = vec3(1.00, 0.92, 0.61);
    return mix(c * vec3(1.0, 0.72, 0.65), c, 0.45 + 0.55 * clamp(uWarmth, 0.0, 1.0));
}

void mainImage(out vec4 fragColor, in vec2 fragCoord) {
    // Fit the entire room on narrow screens; extend its walls on ultrawide.
    // uPixel is the block size at 1080p. Always upscale by integer screen pixels.
    float fit = min(iResolution.y / 180.0, iResolution.x / 320.0);
    float px = max(1.0, floor(fit * max(uPixel, 1.0) / 6.0 + 0.5));
    vec2 cell = floor(fragCoord / px);
    vec2 p = ((cell + 0.5) * px - iResolution.xy * 0.5) / fit + vec2(160.0, 90.0);
    p = floor(p) + 0.5;
    float fps = max(uFps, 1.0);
    float t = floor(iTime * fps) / fps * max(uSpeed, 0.0);
    float intensity = clamp(uIntensity, 0.0, 2.0);
    float flicker = 0.94 + 0.045 * sin(t * 2.9) + 0.035 * sin(t * 7.3 + 1.0);

    vec3 c = wood(p, 0.0);
    rect(c, p, vec4(-1000.0, 24.0, 1000.0, 29.0), vec3(0.145, 0.10, 0.10));
    if (p.y < 24.0) c = wood(p * vec2(0.8, 0.75), 0.0) * 0.82;
    if (p.x < 17.0 || p.x >= 303.0) c = wood(p, 1.0) * 0.65;
    rect(c, p, vec4(17.0, 28.0, 19.0, 170.0), vec3(0.12, 0.09, 0.10));
    rect(c, p, vec4(301.0, 28.0, 303.0, 170.0), vec3(0.12, 0.09, 0.10));
    rect(c, p, vec4(-1000.0, 168.0, 1000.0, 180.0), wood(p, 0.0) * 0.6);
    rect(c, p, vec4(-1000.0, 167.0, 1000.0, 169.0), vec3(0.12, 0.09, 0.10));

    // Window: timber frame, recessed glass, blue forest beyond.
    rect(c, p, vec4(27.0, 78.0, 98.0, 150.0), vec3(0.12, 0.095, 0.11));
    rect(c, p, vec4(29.0, 82.0, 94.0, 147.0), vec3(0.42, 0.27, 0.19));
    rect(c, p, vec4(33.0, 86.0, 90.0, 143.0), vec3(0.10, 0.09, 0.12));
    rect(c, p, vec4(35.0, 88.0, 88.0, 141.0), vec3(0.08, 0.13, 0.20));
    rect(c, p, vec4(60.0, 86.0, 64.0, 143.0), vec3(0.35, 0.24, 0.18));
    rect(c, p, vec4(34.0, 113.0, 90.0, 117.0), vec3(0.35, 0.24, 0.18));
    rect(c, p, vec4(60.0, 117.0, 61.0, 141.0), vec3(0.51, 0.37, 0.24));
    rect(c, p, vec4(34.0, 116.0, 90.0, 117.0), vec3(0.51, 0.37, 0.24));
    rect(c, p, vec4(26.0, 79.0, 98.0, 83.0), vec3(0.47, 0.31, 0.20));
    rect(c, p, vec4(26.0, 82.0, 98.0, 83.0), vec3(0.64, 0.44, 0.26));

    // Bench, folded blanket, ceramic mug.
    rect(c, p, vec4(30.0, 26.0, 35.0, 47.0), vec3(0.21, 0.13, 0.11));
    rect(c, p, vec4(85.0, 26.0, 90.0, 47.0), vec3(0.21, 0.13, 0.11));
    rect(c, p, vec4(27.0, 44.0, 93.0, 49.0), vec3(0.42, 0.265, 0.16));
    rect(c, p, vec4(27.0, 48.0, 93.0, 50.0), vec3(0.55, 0.355, 0.20));
    rect(c, p, vec4(34.0, 49.0, 65.0, 53.0), vec3(0.33, 0.38, 0.25));
    rect(c, p, vec4(35.0, 38.0, 47.0, 53.0), vec3(0.30, 0.345, 0.225));
    rect(c, p, vec4(38.0, 39.0, 40.0, 53.0), vec3(0.48, 0.49, 0.31));
    rect(c, p, vec4(43.0, 39.0, 45.0, 53.0), vec3(0.48, 0.49, 0.31));
    rect(c, p, vec4(76.0, 50.0, 83.0, 56.0), vec3(0.52, 0.62, 0.60));
    rect(c, p, vec4(82.0, 51.0, 86.0, 55.0), vec3(0.52, 0.62, 0.60));
    rect(c, p, vec4(83.0, 52.0, 85.0, 54.0), vec3(0.25, 0.17, 0.14));
    rect(c, p, vec4(77.0, 55.0, 82.0, 56.0), vec3(0.16, 0.12, 0.12));

    // Woven rug, with a quiet decorative border.
    rect(c, p, vec4(102.0, 6.0, 220.0, 22.0), vec3(0.14, 0.09, 0.11));
    rect(c, p, vec4(105.0, 8.0, 217.0, 21.0), vec3(0.37, 0.19, 0.18));
    rect(c, p, vec4(109.0, 11.0, 213.0, 18.0), vec3(0.47, 0.28, 0.22));
    float weave = step(3.0, mod(p.x, 7.0));
    c = mix(c, vec3(0.59, 0.395, 0.26), weave *
        (box(p, vec4(107.0, 9.0, 215.0, 10.0)) + box(p, vec4(107.0, 19.0, 215.0, 20.0))));

    // Broad stone chimney, timber mantel, recessed stepped arch.
    rect(c, p, vec4(116.0, 28.0, 207.0, 168.0), vec3(0.13, 0.105, 0.12));
    if (box(p, vec4(120.0, 33.0, 202.0, 168.0)) > 0.5) c = stone(p);
    rect(c, p, vec4(117.0, 92.0, 207.0, 100.0), vec3(0.16, 0.105, 0.105));
    rect(c, p, vec4(111.0, 99.0, 211.0, 107.0), wood(p, 0.0) * 0.9);
    rect(c, p, vec4(111.0, 106.0, 211.0, 108.0), vec3(0.62, 0.41, 0.245));
    rect(c, p, vec4(119.0, 94.0, 124.0, 100.0), vec3(0.34, 0.21, 0.14));
    rect(c, p, vec4(197.0, 94.0, 202.0, 100.0), vec3(0.34, 0.21, 0.14));
    float archTop = 92.0 - max(0.0, floor((abs(p.x - 161.0) - 14.0) / 4.0)) * 3.0;
    float opening = box(p, vec4(135.0, 38.0, 187.0, 94.0)) * (1.0 - step(archTop, p.y));
    if (opening > 0.5) {
        c = stone(p * 0.8) * vec3(0.35, 0.22, 0.20);
        c *= 1.0 - clamp((p.y - 43.0) / 45.0, 0.0, 1.0) * 0.58;
        float glow = exp(-length((p - vec2(161.0, 43.0)) / vec2(26.0, 12.0)));
        c += vec3(0.28, 0.055, 0.012) * glow * intensity * flicker;
    }
    rect(c, p, vec4(112.0, 27.0, 211.0, 34.0), vec3(0.29, 0.275, 0.28));
    rect(c, p, vec4(112.0, 33.0, 211.0, 36.0), vec3(0.49, 0.46, 0.41));
    rect(c, p, vec4(135.0, 36.0, 188.0, 40.0), vec3(0.16, 0.105, 0.105));

    // Mantel clock, candle and a green bottle.
    rect(c, p, vec4(150.0, 108.0, 173.0, 128.0), vec3(0.20, 0.135, 0.125));
    c = mix(c, vec3(0.20, 0.135, 0.125), disc(p, vec2(161.5, 127.0), 11.0));
    rect(c, p, vec4(147.0, 108.0, 176.0, 111.0), vec3(0.37, 0.245, 0.15));
    c = mix(c, vec3(0.63, 0.44, 0.24), disc(p, vec2(161.5, 125.0), 9.0));
    c = mix(c, vec3(0.79, 0.735, 0.55), disc(p, vec2(161.5, 125.0), 7.5));
    if (length(p - vec2(161.5, 125.0)) < 9.0) clockHands(c, p, iDate.w);
    vec2 pendulum = vec2(161.5 + sin(t * 2.5) * 2.5, 112.5);
    c = mix(c, vec3(0.54, 0.37, 0.19), stroke(p, vec2(161.5, 117.0), pendulum, 0.45));
    c = mix(c, vec3(0.72, 0.49, 0.235), disc(p, pendulum, 1.6));
    rect(c, p, vec4(125.0, 108.0, 136.0, 110.0), vec3(0.60, 0.38, 0.16));
    rect(c, p, vec4(128.0, 110.0, 133.0, 120.0), vec3(0.84, 0.71, 0.49));
    rect(c, p, vec4(184.0, 108.0, 195.0, 118.0), vec3(0.235, 0.38, 0.32));
    rect(c, p, vec4(187.0, 118.0, 192.0, 122.0), vec3(0.28, 0.44, 0.36));
    rect(c, p, vec4(186.0, 110.0, 188.0, 117.0), vec3(0.42, 0.56, 0.40));

    // Wall shelf with books and a little potted plant.
    rect(c, p, vec4(230.0, 85.0, 292.0, 136.0), vec3(0.15, 0.11, 0.12));
    rect(c, p, vec4(234.0, 89.0, 288.0, 133.0), vec3(0.225, 0.155, 0.135));
    rect(c, p, vec4(231.0, 85.0, 291.0, 89.0), vec3(0.44, 0.28, 0.17));
    rect(c, p, vec4(233.0, 109.0, 289.0, 113.0), vec3(0.44, 0.28, 0.17));
    rect(c, p, vec4(230.0, 135.0, 292.0, 139.0), vec3(0.53, 0.345, 0.21));
    for (int i = 0; i < 7; ++i) {
        float k = float(i), x = 238.0 + k * 6.0;
        float h = 12.0 + floor(hash1(vec2(k, 7.0)) * 8.0);
        vec3 ink = mix(vec3(0.43, 0.21, 0.18), vec3(0.235, 0.37, 0.36), step(0.45, hash1(vec2(k, 5.0))));
        rect(c, p, vec4(x, 113.0, x + 5.0, 113.0 + h), ink);
        rect(c, p, vec4(x + 1.0, 115.0, x + 4.0, 116.0), vec3(0.65, 0.49, 0.29));
        rect(c, p, vec4(x + 1.0, 113.0 + h - 3.0, x + 4.0, 113.0 + h - 2.0), vec3(0.65, 0.49, 0.29));
    }
    rect(c, p, vec4(240.0, 89.0, 260.0, 93.0), vec3(0.44, 0.28, 0.23));
    rect(c, p, vec4(239.0, 93.0, 257.0, 96.0), vec3(0.51, 0.52, 0.39));
    rect(c, p, vec4(263.0, 89.0, 279.0, 100.0), vec3(0.46, 0.25, 0.19));
    rect(c, p, vec4(261.0, 99.0, 281.0, 102.0), vec3(0.62, 0.365, 0.24));
    for (int i = 0; i < 5; ++i) {
        float k = float(i);
        vec2 leaf = vec2(266.0 + k * 3.0, 105.0 + sin(k * 1.8) * 4.0);
        c = mix(c, vec3(0.29, 0.425, 0.255), disc(p * vec2(1.0, 1.6), leaf * vec2(1.0, 1.6), 4.0));
    }
    // Stack of cut wood beside the hearth.
    rect(c, p, vec4(225.0, 26.0, 265.0, 45.0), vec3(0.225, 0.14, 0.12));
    for (int i = 0; i < 3; ++i) {
        float k = float(i);
        logEnd(c, p, vec2(232.0 + k * 12.0, 33.0), 5.0);
        if (i < 2) logEnd(c, p, vec2(238.0 + k * 12.0, 42.0), 5.0);
    }
    rect(c, p, vec4(223.0, 26.0, 267.0, 29.0), vec3(0.35, 0.225, 0.135));

    // Material-aware light, with subtle bands. No per-channel colour truncation.
    vec2 flameCentre = vec2(161.0 + sin(t * 2.1) * 1.2, 56.0 + sin(t * 1.6) * 1.0);
    float direct = exp(-length((p - flameCentre) / vec2(76.0, 67.0)));
    float bounce = exp(-length((p - vec2(162.0, 19.0)) / vec2(95.0, 30.0)));
    float fireLight = (direct * 0.85 + bounce * 0.15) * intensity * flicker;
    float candleLight = exp(-length(p - vec2(130.0, 123.0)) / 20.0) * 0.24;
    float moonLight = exp(-length((p - vec2(61.0, 111.0)) / vec2(38.0, 52.0)));
    float levels = max(uSteps, 2.0);
    float lit = clamp(fireLight + candleLight, 0.0, 1.0);
    lit = floor(lit * levels + bayer4(floor(p)) * clamp(uDither, 0.0, 1.0) * 0.3) / levels;
    lit = max(lit, 0.0);
    float shadow = castShadow(p, flameCentre, vec2(161.5, 129.0), 10.0, 37.0)
                 * smoothstep(138.0, 142.0, p.y) * box(p, vec4(120.0, 138.0, 202.0, 168.0));
    shadow = max(shadow, castShadow(p, flameCentre, vec2(190.0, 116.0), 5.0, 37.0)
                 * smoothstep(122.0, 126.0, p.y)
                 * (1.0 - box(p, vec4(230.0, 85.0, 292.0, 139.0))));
    shadow = max(shadow, castShadow(p, flameCentre, vec2(80.0, 54.0), 3.0, 33.0)
                 * box(p, vec4(32.0, 52.0, 75.0, 70.0)));
    shadow = max(shadow, castShadow(p, flameCentre, vec2(282.0, 138.0), 4.0, 28.0)
                 * step(140.0, p.y));
    lit *= 1.0 - shadow * 0.38;
    vec3 ambient = vec3(0.36, 0.37, 0.46) + clamp(uRoom, 0.0, 1.0) * vec3(0.16, 0.14, 0.13);
    vec2 light = daylight();
    ambient += light.x * vec3(0.12, 0.13, 0.10);
    vec3 windowLight = mix(vec3(0.02, 0.11, 0.19), vec3(0.28, 0.33, 0.30), light.x);
    windowLight += light.y * vec3(0.14, 0.045, 0.01);
    c *= ambient + lit * vec3(1.5, 0.91, 0.43) + moonLight * windowLight;
    // Independent glass exposure preserves the cool-night/warm-fire contrast.
    if (box(p, vec4(35.0, 88.0, 88.0, 141.0)) > 0.5
        && box(p, vec4(60.0, 86.0, 64.0, 143.0)) < 0.5
        && box(p, vec4(34.0, 113.0, 90.0, 117.0)) < 0.5) c = windowGlass(p, t, intensity, flicker);

    if (opening > 0.5) {
        vec2 f = (p - vec2(161.0, 45.0)) / clamp(uScale, 0.5, 2.0);
        float a = tongue(f, -9.0, 26.0 + sin(t * 2.4) * 3.0, 7.5, 1.0, t);
        float b = tongue(f, 0.0, 39.0 + sin(t * 2.1 + 1.0) * 4.0, 9.0, 3.0, t);
        float d = tongue(f, 10.0, 28.0 + sin(t * 3.0 + 2.0) * 3.0, 7.0, 5.0, t);
        float field = max(a, max(b, d));
        if (field > 0.0) {
            float k = clamp(field / 8.0 + (1.0 - f.y / 40.0) * 0.25, 0.0, 1.0);
            c = fireColor(k) * (0.48 + 0.52 * min(intensity, 1.3));
        }
        if (p.y < 46.0 && p.y > 40.0) {
            float coal = hash1(floor(p / vec2(2.0, 1.0)));
            c = mix(vec3(0.29, 0.095, 0.07), vec3(0.93, 0.30, 0.09),
                    step(0.6, coal + sin(t * 2.0 + p.x) * 0.1)) * (0.55 + 0.45 * intensity);
        }
        // Charred wood, diagonal stacked logs, lit upper rims.
        vec2 lp = vec2(p.x, p.y + floor((p.x - 145.0) * 0.16));
        if (box(lp, vec4(140.0, 43.0, 179.0, 49.0)) > 0.5) {
            c = vec3(0.19, 0.105, 0.075) + vec3(0.14, 0.065, 0.02) * step(0.6, noise(lp * vec2(0.3, 2.0)));
            if (lp.y > 47.0) c = vec3(0.73, 0.26, 0.09) * flicker;
        }
        vec2 rp = vec2(p.x, p.y - floor((p.x - 162.0) * 0.13));
        if (box(rp, vec4(151.0, 42.0, 183.0, 47.0)) > 0.5) {
            c = vec3(0.255, 0.135, 0.08);
            if (rp.y > 45.0) c = vec3(0.87, 0.34, 0.105) * flicker;
        }
        for (int i = 0; i < 7; ++i) {
            float k = float(i), age = fract(t * (0.19 + k * 0.008) + hash1(vec2(k, 1.0)));
            vec2 pos = vec2(161.0 + sin(k * 17.0) * 16.0 + sin(age * 8.0 + k) * 3.0, 48.0 + age * 44.0);
            float spark = box(p - floor(pos), vec4(0.0, 0.0, 1.0, 2.0));
            c = mix(c, vec3(1.0, 0.64, 0.25), spark * clamp(uEmbers, 0.0, 1.0) * (1.0 - age));
        }
    }
    cat(c, p, t);
    float candle = tongue(p - vec2(130.5, 121.0), 0.0, 5.5, 1.6, 0.0, t * 0.5);
    c = mix(c, vec3(1.0, 0.80, 0.40), step(0.0, candle) * box(p, vec4(125.0, 120.0, 136.0, 128.0)));
    c = mix(c, vec3(0.68, 0.67, 0.59), coffeeSteam(p, t));
    float vignette = 1.0 - 0.16 * clamp(length((p - vec2(160.0, 90.0)) / vec2(180.0, 120.0)), 0.0, 1.0);
    fragColor = vec4(clamp(c * vignette, 0.0, 1.0), 1.0);
}
