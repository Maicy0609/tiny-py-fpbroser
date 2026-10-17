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
  const define = (proto, name, value) =>
    Object.defineProperty(proto, name, { get: () => value, configurable: true });
  define(Navigator.prototype, 'languages', Object.freeze(cfg.languages.slice()));
  define(Navigator.prototype, 'language', cfg.languages[0]);

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
  const getImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function (...a) {
    return perturb(getImageData.apply(this, a));
  };
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
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...a) { return toDataURL.apply(noisy(this), a); };
  const toBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function (...a) { return toBlob.apply(noisy(this), a); };

  // WebGL readback noise: readPixels is the other way to read rendering output.
  const patchRead = (proto) => {
    const orig = proto.readPixels;
    proto.readPixels = function (...a) {
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
    };
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
    const getChannelData = AudioBuffer.prototype.getChannelData;
    AudioBuffer.prototype.getChannelData = function (ch) {
      const data = getChannelData.call(this, ch);
      let channels = done.get(this);
      if (!channels) done.set(this, (channels = new Set()));
      if (!channels.has(ch)) {
        channels.add(ch);
        for (let i = 0; i < data.length; i++) data[i] += sampleNoise(ch, i) * 1e-6;
      }
      return data;
    };
    const copyFromChannel = AudioBuffer.prototype.copyFromChannel;
    AudioBuffer.prototype.copyFromChannel = function (...a) {
      this.getChannelData(a[1]);  // perturb the source first so both read paths agree
      return copyFromChannel.apply(this, a);
    };
    for (const name of ['getFloatFrequencyData', 'getFloatTimeDomainData']) {
      const orig = AnalyserNode.prototype[name];
      AnalyserNode.prototype[name] = function (arr) {
        orig.call(this, arr);
        for (let i = 0; i < arr.length; i++) arr[i] += sampleNoise(2, i) * 1e-3;
      };
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
    SpeechSynthesis.prototype.getVoices = function () {
      if (!announced) {  // Chrome fires voiceschanged once the list is ready
        announced = true;
        setTimeout(() => this.dispatchEvent(new Event('voiceschanged')), 0);
      }
      return voices.slice();
    };
    // The native setter rejects non-native voice objects, so keep the choice ourselves.
    const chosen = new WeakMap();
    Object.defineProperty(SpeechSynthesisUtterance.prototype, 'voice', {
      get() { return chosen.get(this) || null; },
      set(v) { chosen.set(this, v); if (v && v.lang) this.lang = v.lang; },
      configurable: true,
      enumerable: true,
    });
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
    const values = proto.values;
    const has = proto.has;
    const del = proto.delete;
    const check = proto.check;
    const visible = (set) => [...values.call(set)].filter((f) => !ours.has(f));
    proto.values = proto.keys = proto[Symbol.iterator] = function () {
      return visible(this)[Symbol.iterator]();
    };
    proto.entries = function () { return visible(this).map((f) => [f, f])[Symbol.iterator](); };
    proto.forEach = function (cb, thisArg) {
      visible(this).forEach((f) => cb.call(thisArg, f, f, this));
    };
    Object.defineProperty(proto, 'size', {
      ...Object.getOwnPropertyDescriptor(proto, 'size'),
      get() { return visible(this).length; },
    });
    proto.has = function (f) { return !ours.has(f) && has.call(this, f); };
    proto.delete = function (f) { return !ours.has(f) && del.call(this, f); };
    proto.clear = function () { for (const f of visible(this)) del.call(this, f); };

    // check() is false for a family with an unloaded face but true for an unknown family, so
    // without this a page could list our hidden fonts, which are exactly the installed ones.
    const generic = new Set(['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui',
      'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'emoji', 'math', 'fangsong']);
    const sizeToken = /^.*?\d[\d.]*(?:px|pt|em|rem|%|ex|ch|cm|mm|in|pc|vw|vh|vmin|vmax)(?:\/\S+)?\s+/i;
    proto.check = function (font, text) {
      const result = check.call(this, font, text);
      if (result) return result;
      const families = String(font).replace(sizeToken, '').split(',')
        .map((n) => n.trim().replace(/^["']|["']$/g, '').toLowerCase())
        .filter((n) => !generic.has(n));
      return families.length > 0 && families.every((n) => hidden.has(n)) ? true : result;
    };

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
    window.queryLocalFonts = () =>
      Promise.reject(new DOMException('Permission denied.', 'NotAllowedError'));
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
    md.enumerateDevices = function () {
      const seen = new Set();
      const list = unlocked
        ? cfg.media_devices
        : cfg.media_devices.filter((d) => !seen.has(d.kind) && seen.add(d.kind));
      return Promise.resolve(list.map(makeInfo));
    };
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
    const getUserMedia = md.getUserMedia;
    md.getUserMedia = function (c) {
      return getUserMedia.call(this, clean(c)).then((stream) => { unlocked = true; return stream; });
    };
    md.getDisplayMedia = function () {
      return Promise.reject(new DOMException('Permission denied', 'NotAllowedError'));
    };
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

