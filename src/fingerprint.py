"""Fingerprint construction: init script, media devices, speech voices and fonts."""

import json
import random
import re
import secrets
from typing import Any

from config import (
    CAMERA_LABELS,
    LOCALE_FONTS,
    MIC_LABELS,
    SPEAKER_LABELS,
    SPEECH_VOICES,
    STYLE_WORDS,
    WINDOWS_FONTS,
)

# Injected into every page/frame before any page script runs.
INIT_JS = r"""(() => {
  const cfg = __CFG__;

  // --- native-code disguise ---------------------------------------------------
  // Every API patched below is a JavaScript function, and a detector only has to
  // call toString() on it to read our source instead of "[native code]". Each
  // replacement therefore reports the native string, name and length of the
  // function it replaced. This defeats the direct check; a detector that brings
  // its own clean toString from a realm this script never ran in can still see
  // the source, so every property stays on the prototype and the patch runs in
  // every frame alike.
  // The native string lives on the function itself under a registry symbol, so a
  // patched copy of this script in another realm still recognises our functions.
  const nativeKey = Symbol.for('fpbroser.nativeString');
  const nativeToString = Function.prototype.toString;
  const disguiseToString = function toString() {
    const fake = this[nativeKey];
    return fake !== undefined ? fake : nativeToString.call(this);
  };
  Object.defineProperty(disguiseToString, nativeKey, {
    value: nativeToString.call(Function.prototype.toString), configurable: true,
  });
  Function.prototype.toString = disguiseToString;

  const disguise = (patched, original) => {
    Object.defineProperty(patched, nativeKey, {
      value: nativeToString.call(original), configurable: true,
    });
    Object.defineProperty(patched, 'name', { value: original.name, configurable: true });
    Object.defineProperty(patched, 'length', { value: original.length, configurable: true });
  };
  const patchMethod = (proto, name, make) => {
    const original = proto[name];
    const patched = make(original);
    disguise(patched, original);
    proto[name] = patched;
  };
  const patchAccessor = (proto, name, make) => {
    const original = Object.getOwnPropertyDescriptor(proto, name);
    const patched = make(original && original.get, original && original.set);
    if (patched.get && original && original.get) disguise(patched.get, original.get);
    if (patched.set && original && original.set) disguise(patched.set, original.set);
    Object.defineProperty(proto, name, { ...patched, configurable: true });
  };

  patchAccessor(Navigator.prototype, 'languages', () => ({
    get: () => Object.freeze(cfg.languages.slice()),
  }));
  patchAccessor(Navigator.prototype, 'language', () => ({
    get: () => cfg.languages[0],
  }));

  const prng = (seed) => () => {
    seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const perturb = (img) => {
    const d = img.data;
    if (!d.length) return img;
    const rnd = prng(cfg.canvas_seed);
    for (let n = 0; n < 16; n++) d[Math.floor(rnd() * (d.length >> 2)) * 4 + (n % 3)] ^= 1;
    return img;
  };
  const getImageData = CanvasRenderingContext2D.prototype.getImageData;  // pristine, for noisy()
  patchMethod(CanvasRenderingContext2D.prototype, 'getImageData', (orig) =>
    function (...a) { return perturb(orig.apply(this, a)); });
  const noisy = (canvas) => {
    const c = document.createElement('canvas');
    c.width = canvas.width;
    c.height = canvas.height;
    const x = c.getContext('2d');
    if (!x || !c.width || !c.height) return canvas;
    x.drawImage(canvas, 0, 0);
    x.putImageData(perturb(getImageData.call(x, 0, 0, c.width, c.height)), 0, 0);
    return c;
  };
  patchMethod(HTMLCanvasElement.prototype, 'toDataURL', (orig) =>
    function (...a) { return orig.apply(noisy(this), a); });
  patchMethod(HTMLCanvasElement.prototype, 'toBlob', (orig) =>
    function (...a) { return orig.apply(noisy(this), a); });

  // WebGL readback noise: readPixels is the other way to read rendering output.
  const patchRead = (proto) => {
    patchMethod(proto, 'readPixels', (orig) =>
      function (...a) {
        const result = orig.apply(this, a);
        const px = a[6];
        if (px instanceof Uint8Array || px instanceof Uint8ClampedArray) {
          const rnd = prng(cfg.canvas_seed ^ 0x5bd1e995);
          for (let n = 0; n < 16 && px.length; n++) {
            let pos = Math.floor(rnd() * px.length);
            if (px.length % 4 === 0 && pos % 4 === 3) pos -= 1;  // leave alpha alone
            px[pos] ^= 1;
          }
        }
        return result;
      });
  };
  patchRead(WebGLRenderingContext.prototype);
  if (window.WebGL2RenderingContext) patchRead(WebGL2RenderingContext.prototype);

  // AudioContext noise: far below audibility, fixed per profile, applied once per channel.
  if (window.AudioBuffer && window.AnalyserNode) {
    const sampleNoise = (ch, i) => {
      let h = Math.imul((i ^ cfg.audio_seed) + ch * 0x9E3779B1, 0x85EBCA6B);
      h ^= h >>> 13;
      h = Math.imul(h, 0xC2B2AE35);
      h ^= h >>> 16;
      return (h >>> 0) / 4294967296 - 0.5;
    };
    const done = new WeakMap();  // AudioBuffer -> channels already perturbed
    patchMethod(AudioBuffer.prototype, 'getChannelData', (orig) =>
      function (ch) {
        const data = orig.call(this, ch);
        let channels = done.get(this);
        if (!channels) done.set(this, (channels = new Set()));
        if (!channels.has(ch)) {
          channels.add(ch);
          for (let i = 0; i < data.length; i++) data[i] += sampleNoise(ch, i) * 1e-6;
        }
        return data;
      });
    patchMethod(AudioBuffer.prototype, 'copyFromChannel', (orig) =>
      function (...a) {
        this.getChannelData(a[1]);  // perturb the source first so both read paths agree
        return orig.apply(this, a);
      });
    for (const name of ['getFloatFrequencyData', 'getFloatTimeDomainData']) {
      patchMethod(AnalyserNode.prototype, name, (orig) =>
        function (arr) {
          orig.call(this, arr);
          for (let i = 0; i < arr.length; i++) arr[i] += sampleNoise(2, i) * 1e-3;
        });
    }
  }

  // Speech voices: report the voices a stock Windows install has for the profile locale,
  // not whatever is really installed.
  if (window.speechSynthesis && window.SpeechSynthesisVoice) {
    const makeVoice = (v, i) => {
      const o = Object.create(SpeechSynthesisVoice.prototype);
      const props = { name: v.name, lang: v.lang, voiceURI: v.name, localService: true, default: i === 0 };
      for (const k in props) Object.defineProperty(o, k, { value: props[k], enumerable: true });
      return o;
    };
    const voices = cfg.speech_voices.map(makeVoice);
    let announced = false;
    patchMethod(SpeechSynthesis.prototype, 'getVoices', () =>
      function () {
        if (!announced) {  // Chrome fires voiceschanged once the list is ready
          announced = true;
          setTimeout(() => this.dispatchEvent(new Event('voiceschanged')), 0);
        }
        return voices.slice();
      });
    // The native setter rejects non-native voice objects, so keep the choice ourselves.
    const chosen = new WeakMap();
    patchAccessor(SpeechSynthesisUtterance.prototype, 'voice', () => ({
      get() { return chosen.get(this) || null; },
      set(v) { chosen.set(this, v); if (v && v.lang) this.lang = v.lang; },
    }));
  }

  // Font set: hide installed fonts that a stock Windows install of this locale would not have.
  // An @font-face family shadows the system font of the same name. Its source never loads, so
  // text falls through to the next family exactly as if the font were not installed.
  if (document.fonts && window.FontFace && window.FontFaceSet) {
    const hidden = new Set((cfg.hidden_fonts || []).map((n) => n.toLowerCase()));
    const ours = new Set();
    for (const name of cfg.hidden_fonts || []) {
      try {
        const face = new FontFace('"' + name.replace(/["\\]/g, '\\$&') + '"', 'local("fp-no-such-font")');
        document.fonts.add(face);
        ours.add(face);
      } catch (e) {}
    }

    // Keep the shadow faces out of sight: iteration, size, has/delete/clear, events and check().
    const proto = FontFaceSet.prototype;
    const values = proto.values;  // the pristine original, used by visible() below
    const visible = (set) => [...values.call(set)].filter((f) => !ours.has(f));
    patchMethod(proto, 'values', () =>
      function () { return visible(this)[Symbol.iterator](); });
    patchMethod(proto, 'keys', () =>
      function () { return visible(this)[Symbol.iterator](); });
    patchMethod(proto, Symbol.iterator, () =>
      function () { return visible(this)[Symbol.iterator](); });
    patchMethod(proto, 'entries', () =>
      function () { return visible(this).map((f) => [f, f])[Symbol.iterator](); });
    patchMethod(proto, 'forEach', () =>
      function (cb, thisArg) { visible(this).forEach((f) => cb.call(thisArg, f, f, this)); });
    patchAccessor(proto, 'size', () => ({
      get() { return visible(this).length; },
    }));
    patchMethod(proto, 'has', (orig) =>
      function (f) { return !ours.has(f) && orig.call(this, f); });
    patchMethod(proto, 'delete', (orig) =>
      function (f) { return !ours.has(f) && orig.call(this, f); });
    patchMethod(proto, 'clear', (orig) =>
      function () { for (const f of visible(this)) orig.call(this, f); });

    // check() is false for a family with an unloaded face but true for an unknown family, so
    // without this a page could list our hidden fonts, which are exactly the installed ones.
    const generic = new Set(['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui',
      'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'emoji', 'math', 'fangsong']);
    const sizeToken = /^.*?\d[\d.]*(?:px|pt|em|rem|%|ex|ch|cm|mm|in|pc|vw|vh|vmin|vmax)(?:\/\S+)?\s+/i;
    patchMethod(proto, 'check', (orig) =>
      function (font, text) {
        const result = orig.call(this, font, text);
        if (result) return result;
        const families = String(font).replace(sizeToken, '').split(',')
          .map((n) => n.trim().replace(/^["']|["']$/g, '').toLowerCase())
          .filter((n) => !generic.has(n));
        return families.length > 0 && families.every((n) => hidden.has(n)) ? true : result;
      });

    // Loading events caused only by our faces never reach page listeners.
    for (const type of ['loading', 'loadingdone', 'loadingerror']) {
      document.fonts.addEventListener(type, (e) => {
        if (e.fontfaces && e.fontfaces.length && e.fontfaces.every((f) => ours.has(f))) {
          e.stopImmediatePropagation();
        }
      });
    }
  }
  if (window.queryLocalFonts) {
    patchMethod(window, 'queryLocalFonts', () =>
      () => Promise.reject(new DOMException('Permission denied.', 'NotAllowedError')));
  }

  // Fake media devices: enumerateDevices never reveals real hardware. Capture streams come
  // from Chrome's built-in fake device (--use-fake-device-for-media-stream), never a real one.
  if (window.MediaDevices && navigator.mediaDevices) {
    const md = MediaDevices.prototype;
    let unlocked = false;  // like Chrome, ids and labels stay empty until a capture succeeded
    const makeInfo = (d) => {
      const o = Object.create(MediaDeviceInfo.prototype);
      const v = {
        deviceId: unlocked ? d.device_id : '',
        kind: d.kind,
        label: unlocked ? d.label : '',
        groupId: unlocked ? d.group_id : '',
      };
      for (const k in v) Object.defineProperty(o, k, { value: v[k], enumerable: true });
      Object.defineProperty(o, 'toJSON', { value: () => ({ ...v }) });
      return o;
    };
    patchMethod(md, 'enumerateDevices', () =>
      function () {
        const seen = new Set();
        const list = unlocked
          ? cfg.media_devices
          : cfg.media_devices.filter((d) => !seen.has(d.kind) && seen.add(d.kind));
        return Promise.resolve(list.map(makeInfo));
      });
    const clean = (c) => {
      if (!c || typeof c !== 'object') return c;
      const out = { ...c };
      for (const k of ['audio', 'video']) {
        if (out[k] && typeof out[k] === 'object') {
          const { deviceId, groupId, ...rest } = out[k];  // fake ids are unknown to Chrome
          out[k] = rest;
        }
      }
      return out;
    };
    patchMethod(md, 'getUserMedia', (orig) =>
      function (c) {
        return orig.call(this, clean(c)).then((stream) => { unlocked = true; return stream; });
      });
    patchMethod(md, 'getDisplayMedia', () =>
      function () {
        return Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
      });
  }
})();
"""


def build_media_devices() -> list[dict[str, str]]:
    """Random but stable (persisted) device list shaped like Chrome on Windows."""
    audio_group = secrets.token_hex(32)
    devices: list[dict[str, str]] = []
    for kind, label in (
        ("audioinput", random.choice(MIC_LABELS)),
        ("audiooutput", random.choice(SPEAKER_LABELS)),
    ):
        for device_id, prefix in (("default", "Default - "), ("communications", "Communications - ")):
            devices.append(
                {"kind": kind, "label": prefix + label, "device_id": device_id, "group_id": audio_group}
            )
        devices.append(
            {"kind": kind, "label": label, "device_id": secrets.token_hex(32), "group_id": audio_group}
        )
    devices.append(
        {
            "kind": "videoinput",
            "label": random.choice(CAMERA_LABELS),
            "device_id": secrets.token_hex(32),
            "group_id": secrets.token_hex(32),
        }
    )
    return devices


def build_speech_voices(locale: str) -> list[dict[str, str]]:
    return [
        {"name": name, "lang": lang}
        for lang in dict.fromkeys([locale, "en-US"])
        for name in SPEECH_VOICES.get(lang, [])
    ]



def font_names(registry_name: str) -> list[str]:
    """'Arial Bold Italic (TrueType)' -> ['Arial Bold Italic', 'Arial Bold', 'Arial'].

    Font collections are written as 'A & B (TrueType)' and yield the names of every member.
    """
    names: list[str] = []
    for part in re.sub(r"\s*\([^)]*\)\s*$", "", registry_name).split(" & "):
        words = part.split()
        while words:
            names.append(" ".join(words))
            if words[-1].lower() not in STYLE_WORDS:
                break
            words.pop()
    return names


def font_allowed(name: str, allowed: set[str]) -> bool:
    words = name.lower().split()
    while words:
        if " ".join(words) in allowed:
            return True
        if words[-1] not in STYLE_WORDS:
            return False
        words.pop()
    return False


def installed_fonts() -> list[str]:
    """Names of every font registered in Windows (system-wide and per-user)."""
    import winreg

    names: set[str] = set()
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                names.update(font_names(winreg.EnumValue(key, i)[0]))
    return sorted(names)


def hidden_fonts(locale: str) -> list[str]:
    allowed = {name.lower() for name in WINDOWS_FONTS + LOCALE_FONTS.get(locale, ())}
    return [name for name in installed_fonts() if not font_allowed(name, allowed)]


def build_init_script(profile: dict[str, Any], hidden: list[str]) -> str:
    cfg = {
        **profile["fingerprint"],
        "languages": profile["browser"]["languages"],
        "hidden_fonts": hidden,
    }
    return INIT_JS.replace("__CFG__", json.dumps(cfg))
